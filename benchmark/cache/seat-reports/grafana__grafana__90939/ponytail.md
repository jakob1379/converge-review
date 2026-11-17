Review via ponytail:ponytail-review, over-engineering lens only. No spec, so there were no spec gaps to check.

What this change does: It puts a lock (`sync.RWMutex`) around the package-level cache of the frontend asset manifest in `GetWebAssets`. This fixes a data race between concurrent HTTP requests. The callers are `pkg/api/index.go:82`, `pkg/api/frontendsettings.go:62` and `pkg/middleware/recovery.go:141`. The fix is small and in the right place: one shared function, no new layers, and no caller changes.

Load assumed: a Grafana server, where `GetWebAssets` runs on every index-page request and every frontend-settings request. The hot path is the cache hit.

**Nice to have**

1. **The lock is heavier than the work it actually does** (`pkg/api/webassets/webassets.go:35-49`, Minor)
   - **What this is:** The function reads the cache under a read lock. On a miss, it takes the write lock and holds it while it reads the manifest file.
   - **Problem:** It never checks the cache again after taking the write lock. If N requests miss at the same time on a cold cache (or in Dev mode), they queue up and each one re-reads `assets-manifest.json`. So the write lock only puts the duplicate reads in a line. It does not remove them. In practice it protects only the one write at line 69, which costs two lock objects and five lines of lock calls.
   - **Fix:** Pick one of two smaller forms.
     - (a) Use the standard library's `atomic.Pointer[dtos.EntryPointAssets]` (Go 1.22 per go.mod). Read with `if p := cache.Load(); cfg.Env != setting.Dev && p != nil { return p, nil }` and write with `cache.Store(result); return result, err`. This drops the mutex variable and all the Lock/Unlock lines, and it behaves the same as the patch.
     - (b) Keep the RWMutex but add `if cfg.Env != setting.Dev && entryPointAssetsCache != nil { return entryPointAssetsCache, nil }` right after `Lock()`. Then the write lock actually prevents the duplicate reads.
   - **If we skip it:** Nothing breaks. On a cold start there are a few extra file reads, and there is a lock that looks like it removes duplicate reads but does not.
   - **Evidence:** This is reasoned from lines 41-49 and 69-70. No test was run, and I wrote no failing command because this is not a correctness bug. No file in `pkg/` uses `atomic.Pointer[` yet, so (a) is stdlib but would be new to the codebase. Option (b) keeps the codebase's existing pattern.

Verdict: Ship. Finding 1 is optional.
Lean: -3 lines possible with option (a). Option (b) adds 3 lines but makes the lock do something.

Not reviewed: none. The patch touches one file, `pkg/api/webassets/webassets.go`, and I reviewed it with its three callers.
Not checked: following my brief, I did not run `go test -race`. I did not look at correctness, security or test coverage beyond the lens. The patch adds no test that reproduces the race; `pkg/api/webassets/webassets_test.go` exists but is unchanged.
