## OCR delegate review: grafana__grafana__90939 (cca9dee702..b1613e320a)

I ran OCR with `ocr delegate preview --from cca9dee702 --to b1613e320a` (range mode, merge_base cca9dee702). It found one reviewable file out of one: `pkg/api/webassets/webassets.go` [modified] +13/-3. I loaded the Go rule group with `ocr delegate rule` and reviewed the file against it, reading the surrounding source for context.

This was report only. I edited nothing and applied no fixes, even though the skill's default is to fix High and Medium issues automatically. I wrote nothing to the scratch dir. There is no spec, so I have no spec gaps to report.

### Verdict
The fix is correct and has no Critical or Important issues. Before the patch, `entryPointAssetsCache` was read and written by concurrent HTTP handlers with no synchronization. After the patch:
- reads take `RLock` (webassets.go:41-43);
- the write path takes `Lock` with a deferred unlock (webassets.go:48-49);
- the write at webassets.go:69 and the return at :70 both happen under the exclusive lock.

The cached `*dtos.EntryPointAssets` is shared by every caller once returned, so I checked whether any caller mutates it:
- `pkg/api/index.go:82` only assigns it to `IndexViewData.Assets`;
- `pkg/api/frontendsettings.go:62` only reads fields to compute a hash;
- `pkg/middleware/recovery.go:141` only passes it to a template.

`SetContentDeliveryURL` is the only mutator, and it is called only on a freshly built result inside the lock (webassets.go:64) or inside the CDN helper, which is never reached (webassets.go:99). The shared pointer is therefore read-only after publication, so the fix holds.

### Findings
1. **webassets.go:48-49: Minor.** After taking the write lock, the code does not check the cache again.
   - **What happens:** on a cold cache in production, every request that saw `ret == nil` waits for the lock and then rebuilds the manifest one after another. Each one re-opens and re-parses `assets-manifest.json` and replaces the cache with a new pointer.
   - **Impact:** the result is still correct and race-free. The only cost is repeated file reads on startup or on a cache that is still nil.
   - **Why:** reasoned from the code; there is no failing test, because behaviour is correct.
   - **Fix:** after `Lock()`, add `if cfg.Env != setting.Dev && entryPointAssetsCache != nil { return entryPointAssetsCache, nil }`.
2. **webassets.go:45-49: Minor.** In `setting.Dev`, every call skips the cached value and holds the exclusive lock while it reads the file.
   - **Impact:** index, frontend-settings and recovery-page requests are now served one at a time in dev. This is dev only, so it has no production impact.
   - **Why:** reasoned from the code.
3. **pkg/api/webassets/webassets_test.go: Minor.** The patch adds no test for the concurrency fix.
   - **Suggested test:** a test that calls `GetWebAssets` from several goroutines against `testdata` under `go test -race`. It would fail at base and pass at head.
   - **Status:** I did not run it, as instructed.

### Coverage
- total_files: 1, reviewed_files: 1, skipped_files: 0, coverage_rate: 100%.
- I skipped no files from the patch.

The CDN branch is dead code (`cdn := ""`), so I did not analyse it in depth. Holding the lock across an HTTP call there is not a real risk until that branch is enabled. The error path at webassets.go:69 stores a nil result into the cache; the patch did not change that, so I did not report it.
