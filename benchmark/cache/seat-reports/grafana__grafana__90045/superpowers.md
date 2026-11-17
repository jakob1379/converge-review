## Code review: grafana PR, dual writer mode 3 (base 66c4dff17e..HEAD e369f24665)

I loaded the `superpowers:requesting-code-review` skill and did the review myself, as you asked, without dispatching a subagent. I checked that `git diff base..HEAD` is identical to `pinned.patch`. There was no spec, so I judged the change against how mode 1 and mode 2 already behave, against `SetDualWritingMode`, and against the playlist legacy storage. I ran no builds or tests. Every claim below comes from reading the code, and each Important finding names a test that would show it.

**Verdict: not ready to merge.** The mode-3 tests never run mode 3. The new code also has real problems with keeping legacy storage in sync and with its metrics.

### Important

**1. The new mode-3 integration tests actually run mode 1, and mode 3 cannot be turned on at all.**
- **Where:** `pkg/tests/apis/playlist/playlist_test.go:132`, `:191`, `:287`; the cause is in `pkg/apiserver/rest/dualwriter.go:151-222`.
- **Claim:** `SetDualWritingMode` only has transitions for 1→2 and 2→1. When the stored mode is unset (as in every fresh integration-test DB), it defaults to `Mode1` and stores it (lines 188-196). A desired `Mode3` falls through to `// #TODO add support for other combinations` and returns `Mode1`.
- **Effect:** The "file, mode 3" and "unified storage, mode 3" subtests run the whole playlist suite in mode 1. That doubles existing coverage and adds CI time while giving false confidence. In production, `[unified_storage_mode] playlists...=3` also gives mode 1, so `DualWriterMode3` can be reached only by calling `NewDualWriter(Mode3, …)` directly, which only the unit tests do. A PR titled "Finish mode 3" leaves mode 3 unreachable.
- **Test that fails on the patched code:** add `{desiredMode: Mode3, expectedMode: Mode3}` to the table in `TestSetDualWritingMode` (`pkg/apiserver/rest/dualwriter_test.go:26`). It returns `Mode1`.

**2. The background legacy writes use a child of the request context, so they can be cancelled as soon as the response is sent.**
- **Where:** `pkg/apiserver/rest/dualwriter_mode3.go:51`, `:110`, `:135`, `:163`.
- **Claim:** Each goroutine calls `context.WithTimeoutCause(ctx, 10s, …)` on the request ctx. `net/http` cancels the request ctx when `ServeHTTP` returns, and the apiserver timeout filter also cancels on return. The legacy SQL write therefore races the response and can fail with `context canceled`.
- **Effect:** In mode 3, legacy is the store you roll back to, so losing writes silently means legacy drifts from storage without anyone noticing. The goroutines also never log a legacy error: they only record a histogram. The old code logged those failures.
- **Fix direction:** use `context.WithoutCancel(ctx)` (the module targets go 1.22.4) and log the errors.
- **Status:** reasoned, not demonstrated. Mode 1 already uses the same pattern for its storage writes (`dualwriter_mode1.go:54` and following), so this copies an existing flaw into the path that matters for rollback.

**3. Update passes the caller's original `objInfo` to legacy, so legacy can end up with a different object than storage.**
- **Where:** `dualwriter_mode3.go:139`.
- **Claim:** The patch drops the `updateWrapper{updated: obj}` hand-off. Legacy `Update` (`pkg/registry/apis/playlist/legacy_storage.go:147`) now calls `objInfo.UpdatedObject(ctx, legacyOld)` again, in the background, against legacy's own old object.
- **Effect:** For PATCH and server-side apply, the objInfo is the apiserver patcher, which re-runs patch application and admission against a different base object after the request has finished. Legacy can therefore store a result that differs from what storage stored. The wrapper existed to stop exactly this.
- **Status:** reasoned. A unit test can show it: give an `UpdatedObjectInfo` whose output depends on `oldObj`, then compare what the legacy mock receives with what storage returned.

**4. The metrics are recorded under the wrong store, and one label gets object names.**
- **Where:** `dualwriter_mode3.go:45`, `:129`, `:166`, `:106`.
- **Wrong store:**
  - `:45` (Create) and `:129` (Update) record a *storage* failure with `recordLegacyDuration`.
  - `:166` records the *legacy* DeleteCollection time with `recordStorageDuration`.
- **Effect of the mix-up:** the `dual_writer_{legacy,storage}_duration_seconds` histograms will be wrong for mode 3. Those are the signals you would use to decide whether moving to mode 3 is safe.
- **Object names as a label:** `:106` passes `name` (the object name) as the `kind` label. Every deleted object creates a new label set on a global native histogram, so the number of label combinations grows without limit. Mode 1 has the same bug at `dualwriter_mode1.go:155`, which is where it was copied from.
- **Test that fails:** run Create with a failing storage mock and a fresh registry, then assert that the storage histogram has `is_error="true"`. Today the sample lands in the legacy histogram.

**5. The unit tests cannot check what mode 3 is supposed to guarantee.**
- **Where:** `pkg/apiserver/rest/dualwriter_mode3_test.go` (the whole file).
- **Shared mock:** `legacyStoreMock` and `storageMock` share one `*mock.Mock`. Expectations set for "legacy" are matched by storage calls and the other way round.
- **Wrong labels on cases:** the Create case "creating an object only in the unified store" sets up a legacy expectation. The case "error when … unified store fails" sets its failure only through `setupLegacyFn` (lines 28-42), and it passes because the mock is shared.
- **What is never checked:**
  - that reads never reach legacy;
  - that legacy is written at all;
  - that a legacy failure does not affect the response.

  There is no `AssertExpectations`, no `AssertNotCalled`, and no waiting for the goroutine. Together with finding 1, nothing in the PR tests the new background legacy write.
- **Side effect:** the goroutines call the mock after the subtest has finished. They only avoid a panic because the shared expectation happens to match.

### Minor

- **`dualwriter_mode3.go:42` / `:55` (Create):** legacy receives the caller's input `obj`, not `created`, and without a DeepCopy. Mode 1 copies first (`createdCopy`) and mode 2 enriches the object. The playlist legacy store uses `p.Name` as the UID, so generated names reach legacy only because `genericregistry.BeforeCreate` happens to modify `obj` in place. The goroutine also shares `obj` with the request path.
- **`dualwriter_mode3.go:97` (Delete):** `klog.NewContext(ctx, d.Log)` should be `log`. As written, the name, kind and method fields never reach the downstream loggers. This is copied from mode 1.
- **`dualwriter_mode3.go:100-104` (Delete):** this is a behaviour change. The old code ignored NotFound from storage and still deleted from legacy. Now a NotFound from storage returns early, so objects that exist only in legacy (never migrated) are never cleaned up and come back after a rollback to mode 1 or 2. That is acceptable only if mode 3 can require that the data is fully synced first, and finding 1 shows no such gate exists.
- **`go.work.sum:405`:** the added `github.com/grafana/grafana/pkg/apimachinery v0.0.0-20240701135906-559738ce6ae1/go.mod` line duplicates the line just above it. Check with `sort go.work.sum | uniq -d`. The whole go.work.sum change is unrelated dependency churn from the "Update dependencies" commit.
- **`pkg/apiserver/rest/dualwriter_mode1_test.go:138`:** an unrelated edit that switches to the package-level registry `p`. It is harmless, but it is noise.

### Files not reviewed
I reviewed all five files in the patch. For `go.work.sum` I checked only for duplicate and unrelated lines. I did not check the checksums against the module proxy, because that needs network access and is out of scope for this review.

I did not run the unit or integration tests, as instructed. Findings 2 and 3 are reasoned from how the context and patcher code behave and were not reproduced. Finding 1 is the one to fix first: until mode 3 can actually be reached, the mode-3 integration tests prove nothing.
