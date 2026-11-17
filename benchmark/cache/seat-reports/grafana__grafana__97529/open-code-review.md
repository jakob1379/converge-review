I reviewed this for correctness with the `open-code-review:delegate-review` skill. Base was 871af07203 and the head was HEAD. I found two Important issues and three Minor ones, and nothing Critical. Every finding is reasoned from the source. I could not show any of them failing, because builds and tests were not allowed. OCR's rules for Go were applied.

## Findings

**1. pkg/storage/unified/resource/search.go:216 (with pkg/storage/unified/search/bleve.go:144-154) — Important — the new log call can crash the process with a concurrent map read and write.**
- **Claim:** `s.search.TotalDocs()` loops over `b.cache` (bleve.go:146) without holding `cacheMu`. Writes to the map happen under `cacheMu.Lock()` (bleve.go:137-139), but a lock only helps if the reader takes it too. In Go, an unlocked loop over a map while another goroutine writes it is a fatal runtime error, and `recover` cannot catch it.
- **Evidence:** In the patched `init`, the event goroutine starts at search.go:207-211, before the new `TotalDocs()` call at :216. A write event for a namespace and resource that has no index yet goes `handleEvent` → `getOrCreateIndex` → `build` → `BuildIndex`, which writes `b.cache[key]`. That write can overlap the loop at :216.
- **Same race on a second path:** `BleveIndexMetrics.Collect` (resource/bleve_index_metrics.go:96) calls `TotalDocs()` on every Prometheus scrape. Because this patch drops the function-wide lock, the up to 10 init workers (`index_workers` default 10) now build indexes and write the cache in parallel during startup. Before the patch they were serialized.
- **Fix:** take `b.cacheMu.RLock()` in `TotalDocs`.
- **Test to show it:** a test in `pkg/storage/unified/search` that calls `BuildIndex` for N distinct keys in goroutines while another goroutine loops on `TotalDocs()`, run with `go test -race ./pkg/storage/unified/search/ -run TestTotalDocsRace`. The race detector should flag the read at bleve.go:146 against the write at :138. Not run.

**2. pkg/server/module_server_test.go:35-38 — Important — the patch turns off the only postgres coverage of the storage-server startup path that this change modifies.**
- **Claim:** The skip text says the test "works locally" but fails in Drone. It was added together with this change, which moves `lifecycle.Init` (DB init and ping), the full search index build and the watcher start into the constructor. `sql/service.go:start()` calls that constructor before the gRPC server starts.
- **Evidence:** The branch history shows the test being chased first: `29db0d39b0 wait 1 second before querying metrics`, `1095580dce try with big timeout`, then `6f4d70876a skips postgres integration test`, then `45e0089891 put delay back to 500 ms`. That pattern points to a startup timing or blocking problem caused by the eager init, not a CI flake.
- **Impact:** Skipping the test hides it. The regression is unverified on postgres.

**3. pkg/storage/unified/resource/server.go:320-340 (from the removals throughout the handlers) — Minor — requests after `Stop` are no longer refused.**
- **Claim:** `Stop` still sets `s.initErr` to "service is stopping" or "service is stopped". Before the patch, every RPC called `s.Init(ctx)`, which returned that stored error once the `sync.Once` had run, so calls after `Stop` were rejected. With every `Init` call removed from the handlers, nothing reads `initErr` after construction.
- **Effect:** After `Stop`, Create, Update, Delete, Read, List and blob calls still go to the backend. The backend's poller is cancelled (sql/backend.go:118) but the DB is still open. Writes succeed but no watch events are published for them. Watch now returns `io.EOF` because the broadcaster has terminated.
- **Fix:** either gate the handlers on a stopped flag or delete the dead `initErr` writes in `Stop`.

**4. pkg/storage/unified/resource/server.go:258-262 — Minor — the init-failure path leaks the context and goroutines.**
- **Claim:** When `s.Init(ctx)` fails, `NewResourceServer` returns without calling `s.cancel()`.
- **Leak:** If `search.init` succeeded and `initWatcher` then failed, the search goroutine started at search.go:204-212 also leaks. It is subscribed with `context.Background()` and loops forever.
- **Duplicate logging:** the error is logged twice, once inside `Init` (server.go:313-315) and again at :260.

**5. pkg/storage/unified/search/bleve.go:85-139 (removing the global lock) — Minor, risk made worse by this patch — two builds of the same key can still race, and now more easily.**
- **Claim:** Builds for one key are no longer serialized. `getOrCreateIndex` (search.go:288-306) is check-then-act with no per-key guard, so a `Search` request and `handleEvent` can both see `nil` and both build. Whichever finishes last overwrites `b.cache[key]`, and documents that `handleEvent` wrote to the discarded index are lost.
- **Not new:** the old lock serialized the two builds but never re-checked the cache, so the lost write existed before. Both paths pass size 10, and 10 is not above the default threshold of 10, so both indexes are in memory. The patch makes overlap more likely; it did not create the problem.
- **Data race, also more frequent now:** in `searchSupport.init` (search.go:189-190), goroutines write the shared `err` and `totalBatchesIndexed` with no synchronization. That code was there before, but parallel builds now overlap far more. `go test -race` on any init with 2 or more stats rows should report it.

### Checked and not flagged
- The `ctx, span := ...Start(...)` changes at search.go:173 and :310 and sql/backend.go:126 are correct: they pass the span context down to child calls.
- Moving `initWatcher` after `search.init` does not affect search, because search subscribes to `storage.WatchWriteEvents` itself.
- `builderCache.get` is safe under the new parallel builds.

### Outside the diff, may matter to the caller
- `cfg.IndexPath` defaults to `""` and `index_file_threshold` defaults to 10. So any resource with more than 10 items gets a file index under a path relative to the working directory, created with `bleve.New`. From memory of bleve v2 (not checked, no module cache here), `bleve.New` returns `ErrorIndexPathExists` when the directory already exists.
- If that holds, the second start of a process fails. Before this patch the error was returned lazily on every request. With eager init it now fails `NewResourceServer`, which means a startup failure.

## Unreviewed files
None. All 5 files in the patch were reviewed: `resource/search.go`, `resource/server.go`, `search/bleve.go`, `sql/backend.go` and `pkg/server/module_server_test.go`. OCR excluded the last one by its default path rules, and I reviewed it anyway because the task covers the whole patch.

Coverage: 5 of 5 files reviewed, 0 skipped, 100%.

Not done: no builds, tests or race runs (benchmark mode). The bleve `ErrorIndexPathExists` behaviour comes from memory, not from reading v2.4.3 source.
