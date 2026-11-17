I reviewed pinned.patch (base cca9dee702 to head b1613e320a) myself, using the criteria from `superpowers:requesting-code-review`. That skill normally hands the review to a separate reviewer agent; you said not to spawn agents, so I didn't. There was no spec, so I judged the patch against its commit message, "fix data race in GetWebAssets". I wrote nothing to the repo and ran no builds or tests.

## Patch scope
One file: `pkg/api/webassets/webassets.go`, lines 11 and 35-49. The patch puts a `sync.RWMutex` around the package-level `entryPointAssetsCache`. Reads take a read lock and copy the pointer, and a cache miss rebuilds the value under the write lock, released with `defer`.

## Verdict
**Ready to merge? Yes.** The race in the commit message is fixed, and I found no Critical or Important issues.

- **Before the patch:** concurrent requests read and wrote the global pointer at line 69 with no synchronization. This was a real race.
- **After the patch:** every read and write of `entryPointAssetsCache` is under the mutex.
- **The returned value is not mutated after it is shared.** `SetContentDeliveryURL` (`pkg/api/dtos/index.go:51`) runs on `result` before it is assigned at line 69, so before it is visible to other requests. I checked all three callers and none writes to the returned value:
  - `pkg/api/frontendsettings.go:62` reads fields to build a hash.
  - `pkg/api/index.go:82` passes it into `IndexViewData`.
  - `pkg/middleware/recovery.go:141` passes it into a template struct.
- **No deadlock or double-lock path.** The function never calls itself and nothing re-enters it while the lock is held. A panic inside the function still releases the lock through `defer`.

## Critical
None.

## Important
None.

## Minor
1. **No re-check after taking the write lock** (`webassets.go:48-49`). Reasoned, not run. When the cache is empty (cold start, or after a failed load), N concurrent requests each wait for the write lock and then each re-read and re-parse `assets-manifest.json`, one after another. They all produce the same result, so this is wasted work, not a correctness bug. Fix: after `Lock()`, add `if cfg.Env != setting.Dev && entryPointAssetsCache != nil { return entryPointAssetsCache, nil }`.

2. **Uncached paths are now serialized** (`webassets.go:48-70`). Reasoned.
   - In `cfg.Env == setting.Dev`, every call takes the exclusive lock and reads the file. Before, these calls ran in parallel (racily). Now every dev request that renders the index or frontend settings is serialized on file I/O.
   - In production, a missing or broken manifest leaves the cache nil after each failed load, so every request retries the failed read under the exclusive lock.
   - The lock would also be held across an HTTP call in `readWebAssetsFromCDN`, but that path is currently dead (`cdn := ""` at line 54).
   - Acceptable as is, but worth knowing.

3. **No regression test** (`pkg/api/webassets/webassets_test.go` is unchanged). A test that calls `GetWebAssets` from several goroutines under `go test -race` would show the fix and guard it. It would need a temp `StaticRootPath/build/assets-manifest.json`, copied from `testdata/sample-assets-manifest.json`. I didn't run it, per your instructions.

4. **Global state stays, against a documented standard.** `contribute/backend/services.md:5` says Grafana encourages "explicit initialization instead of global variables". The patch keeps the global and adds `// TODO: get rid of global state` at line 37. The global existed before this patch and the TODO acknowledges it, so it isn't a regression. A side effect: the cache leaks between tests in the package because nothing resets it.

## Strengths
- It is the smallest correct fix.
- The read path takes only a read lock, so the cached production path stays cheap.
- `defer Unlock` covers every return path, including errors.

## Considered and set aside
- `sync.Once` or `atomic.Pointer` instead of the mutex. `Once` can't support the dev-mode reload or retrying after an error, and `atomic.Pointer` would need the same structure. This is style, not a finding.
- Error handling that sets the cache to nil on a failed load. It behaves exactly as before the patch.

## Files not reviewed
None. The patch touches one file and I reviewed all of it.

I compiled nothing and ran no tests or race detector, so every finding above is reasoned from the code. The main risk is the dev-mode serialization in Minor 2, which shows up as latency, not wrong output.
