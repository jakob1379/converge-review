## Review: unified-storage-dont-lazy-init (correctness seat)

I loaded `superpowers:requesting-code-review` and did the review myself; I dispatched nobody. Nothing was built or run (benchmark mode), so every claim below comes from reading the code, with the evidence given.

There is no spec. I took the intent to be the branch name: initialize the resource server and search index eagerly in the constructor and remove the lazy `Init` call from each handler.

**What the patch does right:**
- The `ctx, span :=` changes (search.go:173, search.go:310, sql/backend.go:126) now pass the trace context on to child spans.
- Replacing the grafana-cli `logger` with `s.log` is correct.
- Narrowing the bleve lock to just the cache write is safe in itself. The old wide lock never stopped duplicate builds for the same key anyway, because the `GetIndex` check happens outside the lock.

### Findings

**1. pkg/server/module_server_test.go:35-38: Important.** The new postgres skip hides a test bug that this patch exposed. It does not fix the bug.
- The test hardcodes `db_host` to `"localhost"` for postgres (module_server_test.go:76).
- Drone runs postgres at `POSTGRES_HOST: postgres` (.drone.yml:1155; `scripts/drone/steps/lib.star:1071`). The mysql branch of the same helper already parses the host because "cant use localhost as hostname in drone tests" (line 81).
- Before the patch, `sql/service.go:start` → `NewResourceServer` never opened a DB connection (lazy init), so the wrong host was never used.
- After the patch, `NewResourceServer` calls `Init` → `backend.Init` → `dbProvider.Init` → migrations and ping against `localhost`. That fails in Drone, so the storage-server module fails to start.
- The branch history matches: commits "try with big timeout… Wont fail locally" and "skips postgres integration test. Only fails in drone."
- Fix: take the host from `POSTGRES_HOST` (as `pkg/services/sqlstore/sqlutil/sqlutil.go:138` does) and remove the skip.
- Failing check: with the skip removed, `GRAFANA_TEST_DB=postgres POSTGRES_HOST=postgres go test ./pkg/server -run TestIntegrationWillRunInstrumentationServerWhenTargetHasNoHttpServer` on a host where postgres is not on localhost.

**2. pkg/storage/unified/resource/server.go:258-262: Important.** Eager `Init` now runs inside the wire graph for every Grafana process, so a resource-DB or search failure stops Grafana from booting. Before, it only broke unified-storage requests.
- `ProvideUnifiedStorageClient` (`pkg/storage/unified/client.go:100`, the default/legacy storage type) calls `sql.NewResourceServer`. `apiserver.ProvideService` always takes that client (`pkg/services/apiserver/service.go:147`).
- So every boot now runs `MigrateResourceStore` (with migration locking) against the main DB and pings it.
- It also starts a poller that runs forever, querying `listLatestRVs` every 100 ms (`defaultPollingInterval`, sql/backend.go:28). A second poller starts when `unifiedStorageSearch` is on.
- All of this runs on `context.Background()` with no deadline, so a hanging DB hangs startup.
- This may be intended, but the patch neither guards nor documents the larger blast radius. Reasoned; no test.

**3. pkg/storage/unified/search/bleve.go:98 (reached through server.go:258): Important.** With search enabled, Grafana fails to start on every restart after the first.
- The default `index_file_threshold` is 10 and `index_path` defaults to `""`, a path relative to the working directory (`setting_unified_storage.go:41-44`).
- Any (namespace, resource) with more than 10 objects gets an on-disk index from `bleve.New(dir, …)`.
- bleve v2's `indexMeta.Save` opens `index_meta.json` with `O_EXCL` and returns `ErrorIndexPathExists` when the directory already exists. Nothing deletes or reopens the directory (the RV check is still a TODO).
- Before the patch, the cached `initErr` broke unified-storage requests. Now `NewResourceServer` returns the error, so `ProvideUnifiedStorageClient` fails and Grafana does not start.
- This is pre-existing logic that the patch turns into a boot failure. Reasoned from bleve v2.4.3 behaviour; nothing was run.

**4. pkg/storage/unified/resource/search.go:216: Minor.** The new `s.search.TotalDocs()` call can race with a cache write.
- `TotalDocs` iterates `b.cache` without `cacheMu` (bleve.go:144-154).
- The watch goroutine started at search.go:207 can call `handleEvent` → `getOrCreateIndex` → `BuildIndex`, which writes the map (bleve.go:137-139).
- A concurrent map iteration and write is a fatal Go runtime error that cannot be recovered.
- The window is small: the poller's first tick is 100 ms away. The metrics collector (`bleve_index_metrics.go:96`) already has the same race. Fix: take `RLock` in `TotalDocs`. Reasoned.

**5. pkg/storage/unified/resource/search.go:189-190: Minor.** The patch makes an existing data race more likely.
- Each errgroup worker writes the shared outer `err` (`_, _, err = s.build(...)`) and `totalBatchesIndexed++` without synchronization.
- Before, the full-function `cacheMu` lock in `BuildIndex` serialized most of the work. Now up to `index_workers` (default 10) builds really run in parallel.
- `go test -race` on a multi-namespace init would likely report it. Use a local `err :=` and an atomic counter. Reasoned.

**6. pkg/storage/unified/resource/server.go:258-262: Minor.** The failure path leaks resources and logs twice.
- When `Init` fails, the constructor returns without calling `cancel()` or `lifecycle.Stop`.
- If `initWatcher` fails after `search.init` has succeeded, the search watch goroutine and its sql poller (which stops only on `b.done`) keep running.
- The error is logged at server.go:314 and again at :260.

**7. pkg/storage/unified/resource/server.go:320-341: Minor.** `Stop` still sets `s.initErr = "service is stopping/stopped"`, but no handler checks it any more. Before, every RPC returned that error after Stop; now RPCs run against a cancelled broadcaster and a stopped backend. `Stop` is not part of the `ResourceServer` interface and has no external callers today, so the impact is low. The `initErr` writes are now dead code.

**8. No test for the new contract: Minor.** No test checks that `NewResourceServer` returns an error when `lifecycle.Init`, search init or the watcher fails, or that handlers work without a lazy `Init`. Also, `apistore/watcher_test.go:148` still calls `Init` itself before constructing the server; that is harmless but now redundant.

### Set aside (declined to judge)
- Building the full search index synchronously at startup with no time limit is the stated design ("any failure will block startup"), so I did not count it as a defect.
- After `Stop`, `v := <-events` on a closed channel in `initWatcher` and `search.init` gets nil and would panic with a nil dereference. This existed before and the patch does not touch it.
- Events written between `GetResourceStats` and `WatchWriteEvents` in `search.init` are missed by the index. Pre-existing.
- `handleEvent` uses `IndexMetrics` without a nil check. Pre-existing.

**Verdict:** merge with fixes. Fix #1 (fix the test host instead of skipping), and fix #3 or deliberately accept that search-enabled instances cannot restart. #2 needs a conscious decision on the boot-time impact for all deployments.

### Unreviewed files
None. I reviewed all 5 files in the patch: `pkg/server/module_server_test.go`, `pkg/storage/unified/resource/search.go`, `pkg/storage/unified/resource/server.go`, `pkg/storage/unified/search/bleve.go` and `pkg/storage/unified/sql/backend.go`.

I did not run tests or `-race`, and the bleve `ErrorIndexPathExists` behaviour comes from what I know of v2.4.3; its source is not in the module cache here.
