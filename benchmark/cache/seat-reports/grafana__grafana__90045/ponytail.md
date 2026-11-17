What this change does: It turns DualWriter mode 3 from a stub into a real implementation. Every call goes to unified storage first and is timed; for writes, legacy storage is then written in a background goroutine with a 10s timeout. It also adds `List` (it used to return `nil, nil`), drops the `updateWrapper`/Get-before-Update dance, adds mode-3 unit tests, and adds playlist integration subtests for mode 3.

Seat: over-engineering only (code, abstraction or duplication that does not need to exist). Load assumed: a Grafana API server serving many concurrent requests. I ran nothing because the brief said no builds or tests. Every claim below comes from reading the code.

**Should fix**

1. **Copy-pasted timing code has already gone wrong in 4 places** (`pkg/apiserver/rest/dualwriter_mode3.go:45`, `:106`, `:129`, `:166`). Severity: Important.
   - **What this is:** Each write method records the storage duration twice: once inside `if err != nil` and once after it. Each background goroutine then records the legacy duration. That makes about 10 near-identical `record*Duration(...)` lines, all edited by hand.
   - **Problem:** The copies drifted:
     - `:45` (Create) and `:129` (Update) log a *storage* failure as `recordLegacyDuration`.
     - `:106` (Delete) passes `name` where it should pass `options.Kind`.
     - `:166` (DeleteCollection) logs the *legacy* call as `recordStorageDuration`.
     - Separately, `:97` sets `ctx = klog.NewContext(ctx, d.Log)` and not `log`, so Delete's context logger loses the name, kind and method values.
   - **Fix:** Do what `Get` and `List` in the same file already do. Make one `d.recordStorageDuration(err != nil, mode3Str, options.Kind, method, startStorage)` call right after the storage call, before the `if err != nil`, and delete the second call inside each error branch. Correct the goroutine at `:166` to `recordLegacyDuration`. That is -4 lines and removes three of the four mistakes outright. (`dualwriter_mode1.go:155` has the same `name` slip, which is where it was copied from.)
   - **If we skip it:** The `dual_writer_legacy_duration_seconds` and `dual_writer_storage_duration_seconds` metrics count failures against the wrong store and get an unbounded `name` label value for deletes. The mode-3 rollout dashboards will be lying.
   - **Evidence:** Reasoned. A test that should fail on the patched code: create a `prometheus.NewRegistry()`, call `NewDualWriter(Mode3, ls, us, reg)`, make storage `Create` return an error, then use `testutil.CollectAndCount` on `dual_writer_legacy_duration_seconds`. The count should be 0 but will be 1.

2. **A per-test metrics registry hides the shared one** (`pkg/apiserver/rest/dualwriter_mode3_test.go:119`, plus the import at `:8`). Severity: Minor.
   - **What this is:** `TestMode3_Get` declares `p := prometheus.NewRegistry()`. The other five mode-3 tests use the package-level `p` from `dualwriter_mode1_test.go:27`.
   - **Problem:** This patch deletes exactly this line from `dualwriter_mode1_test.go:138` as redundant, and then adds it back in the new file. It is the only use of the `prometheus` import in this file.
   - **Fix:** Delete line 119 and the `prometheus` import. That is -2 lines.
   - **If we skip it:** Nothing breaks. It is noise that contradicts the cleanup in the same patch.

**Nice to have**

3. **Legacy mock setups that never take effect** (`pkg/apiserver/rest/dualwriter_mode3_test.go`, the Create success case `setupLegacyFn` and the Update success case `setupLegacyFn`). Severity: Minor.
   - **What this is:** `legacyStoreMock` and `storageMock` share one `*mock.Mock` (`m`).
   - **Problem:** In Update, the "legacy" `m.On("Update", ...)` is byte-for-byte the same as the storage one, so it is a duplicate expectation. In Create, the storage setup already matches any input with `mock.Anything`. Neither legacy setup changes what the test proves. Worse, in the Create error case the expectation labelled `setupLegacyFn` is the one the *storage* call hits, so the name misleads.
   - **Fix:** Delete the two success-case `setupLegacyFn` blocks (-6 lines). Rename or move the Create error-case setup into `setupStorageFn`.
   - **If we skip it:** Readers will think these tests check legacy writes. They do not.

4. **An etcd mode-3 subtest that never runs** (`pkg/tests/apis/playlist/playlist_test.go:287-312`). Severity: Minor.
   - **What this is:** 27 lines copied from the etcd mode 0/1/2 blocks, starting with `t.Skip("local etcd testing")`.
   - **Problem:** It never runs in CI. It does match the existing convention for modes 0–2, so this is house style, not a defect.
   - **Fix:** None needed for this PR. Mention it only if someone folds the 12 near-identical subtests into a loop over modes later.

Not lean findings, flagged once so they are not lost (outside my seat, reasoned only):
- The legacy write goroutines derive their context from the request `ctx`. When the request finishes, that context is cancelled, so the background legacy write can be cancelled with it. Mode 1 has the same pattern.
- Update now passes the caller's `objInfo` straight to Legacy, so `UpdatedObject` runs a second time against legacy's old object and not against what storage stored.
- `return created, err` at `:59` always returns a nil `err`.

Verdict: fix 1 first, because it corrupts the metrics this PR exists to emit.
Lean: -12 lines possible.

Files not reviewed: `go.work.sum` (a generated dependency checksum file, nothing in it to review for over-engineering).
Not checked: I did not compile or run tests, per the brief. The metrics claim in finding 1 is reasoned from source, not executed.
