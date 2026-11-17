## Review of grafana__grafana__90045 (base 66c4dff1..e369f246). Focus: bugs, security, error handling, concurrency

**How I ran it:** `ocr delegate preview --from 66c4dff1 --to e369f246`, then `ocr delegate rule`, which gave me the Go checklist. OCR treats only `pkg/apiserver/rest/dualwriter_mode3.go` as reviewable. I still read the test files in the patch for context. I ran nothing and edited nothing. I could not reach the k8s.io/apiserver v0.29.2 source in the module cache, so the claims about how the apiserver handles the request context are reasoned from upstream behaviour, not checked against the source.

The patch makes Mode3's legacy writes (Create, Update, Delete, DeleteCollection) run in fire-and-forget goroutines. It adds a real `List`, which was a stub returning `nil, nil` before; that part is a correctness fix. It also adds metrics. The async conversion is where the problems are.

### Important

**1. Legacy writes can be cancelled when the request ends: `dualwriter_mode3.go:51, 110, 135, 163`**
- Each goroutine builds its context with `context.WithTimeoutCause(ctx, 10s, …)`, where `ctx` is the request context.
- In k8s apiserver and net/http, that context is cancelled once the handler returns. The handler returns right after `go func()`.
- So `Legacy.Create/Update/Delete/DeleteCollection` race the cancellation. The playlist legacy store's SQL calls (`pkg/registry/apis/playlist/legacy_storage.go`, Create/Update) use that ctx, so they can fail with `context canceled`.
- Before this patch these writes were synchronous, so this is a regression: the legacy store silently falls behind unified storage. That breaks rollback to Mode1/2, which still read from legacy.
- `dualwriter_mode1.go:54` has the same pattern, so this copies an existing house bug rather than inventing one.
- Fix: `context.WithTimeoutCause(context.WithoutCancel(ctx), …)`. Go 1.22.4 per `go.mod`, so `WithoutCancel` is available.
- Reasoned, not run.

**2. Legacy failures are no longer logged: `dualwriter_mode3.go:50-57, 108-114, 134-141, 161-167`**
- The old code logged legacy failures (`"unable to create object in legacy storage"`, `"could not delete from legacy store"`, and so on).
- The goroutines now drop the error. The only trace is the `is_error` label on a histogram, which carries no object name and no cause.
- Together with #1, legacy divergence becomes very hard to see. Add `log.Error(err, …)` in each goroutine.
- Evidence: diff hunks.

**3. Delete no longer cleans up legacy-only objects: `dualwriter_mode3.go:100-105`**
- The old code ignored `apierrors.IsNotFound` from unified storage and still deleted from legacy. The new code returns on any storage error, NotFound included, before the legacy goroutine starts.
- An object that exists only in legacy (not yet migrated, or a missed write from #1) becomes undeletable through the API. It comes back if the mode is rolled back.
- Mode2 (`dualwriter_mode2.go` Delete) still tolerates NotFound, so Mode3 is now inconsistent with it.
- Reasoned. To confirm: a unit test where the storage mock returns `apierrors.NewNotFound(...)` and the legacy mock expects `Delete`. On the patched code, `m.AssertCalled(t, "Delete", …)` for legacy fails.

**4. Legacy Update gets the raw `objInfo` from a goroutine: `dualwriter_mode3.go:139`**
- Before: the code applied `objInfo` once against the unified-storage object and sent legacy `&updateWrapper{updated: obj}`, so both stores received the same object.
- Now: legacy calls `objInfo.UpdatedObject` again, against its own old object, after the handler may have returned.
  - For PATCH requests the k8s patcher's transformers carry mutable handler state and re-run admission with the (possibly cancelled) request ctx. That is a likely data race and can produce a different result in each store.
  - For a plain PUT, `defaultUpdatedObjectInfo` deep-copies, so it is safe.
- Fix: keep the `updateWrapper{upstream: objInfo, updated: res.DeepCopyObject()}` approach, the way Mode1 deep-copies before its goroutine.
- Reasoned; not run with `-race`.

### Minor

**5. Metrics go to the wrong histogram or label:**
- `dualwriter_mode3.go:45`: Create's storage-error path calls `recordLegacyDuration` with `startStorage`. It should be `recordStorageDuration`.
- `dualwriter_mode3.go:129`: Update has the same bug.
- `dualwriter_mode3.go:166`: the DeleteCollection legacy goroutine calls `recordStorageDuration`. It should be `recordLegacyDuration`.
- `dualwriter_mode3.go:106`: Delete passes `name` instead of `options.Kind` as the label. Every deleted object name becomes a new Prometheus series, so cardinality is unbounded. `dualwriter_mode1.go:155` has the same bug.
- To confirm any of these: a unit test using `prometheus/testutil.CollectAndCount(DualWriterStorageDuration)` after a failing Create would show the storage histogram stays empty. Not run.

**6. Delete loses its log fields: `dualwriter_mode3.go:97`.** `klog.NewContext(ctx, d.Log)` drops the name, kind and method values that every other method attaches. It should be `log`.

**7. The async legacy path has no test coverage: `dualwriter_mode3_test.go`.**
- No test waits for or asserts the legacy goroutine.
- The legacy expectations in Create and Update are set but never checked, so #1-#4 and the swapped metrics all pass CI.
- The new playlist Mode3 integration tests (`playlist_test.go:132-145, 191-204`) go through k8s for both reads and writes, so they do not catch legacy divergence either.

The `dualwriter_mode1_test.go` change (removing a `p` that shadowed the package-level `p`) is fine. Nothing in the patch raises a security concern.

### Coverage
- Total files: 5. Reviewed: 4. Skipped: 1. Coverage: 80%.
- Reviewed in full:
  - `pkg/apiserver/rest/dualwriter_mode3.go`
- Read for context and test gaps (OCR excludes `_test.go` by default):
  - `pkg/apiserver/rest/dualwriter_mode1_test.go`
  - `pkg/apiserver/rest/dualwriter_mode3_test.go`
  - `pkg/tests/apis/playlist/playlist_test.go`
- Skipped: `go.work.sum`. It is only module checksums (+16 lines), there is no logic to review, and OCR excludes it as an unsupported type.

Not checked: the apiserver's actual cancellation code (not in the local module cache), and nothing was run with `-race`. #1 and #4 are the ones that can make legacy and unified storage diverge in production.
