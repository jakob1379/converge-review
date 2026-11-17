Code review (mattpocock-skills:code-review; I ran both axes myself, no sub-agents). Fixed point is 66c4dff17e, HEAD is e369f24665: 11 commits, 5 files, +524/-131. I reviewed only the pinned patch.

Standards sources used:
- `contribute/backend/style-guide.md`
- `contribute/backend/instrumentation.md`
- `contribute/create-pull-request.md`
- `CONTRIBUTING.md`, which points into `contribute/`
- `.golangci.toml` is the lint config. I skipped anything it enforces.

Your brief told me to leave generic code smells out, so I did not apply the skill's Fowler smell baseline.

## Standards

**1. Important (hard breach of `instrumentation.md`, "Label values and high cardinality")**
- **Where:** `pkg/apiserver/rest/dualwriter_mode3.go:106`
- **Claim:** `d.recordStorageDuration(false, mode3Str, name, method, startStorage)` puts the object `name` into the histogram's `kind` label. `metrics.go` declares the labels as `[]string{"is_error", "mode", "kind", "method"}`. The guide says: "Very **important** to only allow a pre-defined set of labels to minimize the risk of high cardinality problems", and that label values from user input should be validated.
- **Evidence:** A Kubernetes object name is user input with no bound. Every successful mode-3 Delete creates a new histogram series for `grafana_dual_writer_storage_duration_seconds`. Every other call in the file passes `options.Kind`, and so do modes 1 and 2.
- **Check:** This is reasoned; I wrote and ran no test, since builds and tests were off. A test would call `dw.Delete(ctx, "foo", ...)` and assert that `testutil.CollectAndCount(DualWriterStorageDuration)` gains a series labelled `kind="foo"`.

**2. Minor (`style-guide.md` → "Assertions")**
- **Where:** `pkg/apiserver/rest/dualwriter_mode3_test.go:72-74`
- **Claim:** The test calls `assert.NoError(t, err)` after `meta.Accessor(obj)` and then calls `acc.GetResourceVersion()`.
- **Evidence:** The guide says to use `require.*` for error checks because "continuing the test after such an assertion fails is chaotic … you'll often have segfaults". If `meta.Accessor` errors, `acc` is nil and the test panics. Earlier mode tests have the same pattern, but this file is new code.

**3. Minor (`style-guide.md` → "Globals": "avoid using global variables")**
- **Where:**
  - `pkg/apiserver/rest/dualwriter_mode1_test.go:138`, where the local `p := prometheus.NewRegistry()` was removed in favour of the package-global `p` at `dualwriter_mode1_test.go:27`.
  - `dualwriter_mode3_test.go:63, 174, 228, 282, 343`, which use the global.
  - `dualwriter_mode3_test.go:119`, which still makes a local registry.
- **Claim:** The diff moves tests toward a shared global registry, and does so inconsistently within one file.

**4. Minor (`create-pull-request.md`: "The pull request contains necessary tests that verify the intended behavior")**
- **Where:** `dualwriter_mode3_test.go:37-44, 297-325`
- **Claim:** The unit tests share one `mock.Mock` between `legacyStoreMock` and `storageMock`. None of them asserts that Legacy was or was not called.
- **Evidence:** The Create error case named "unified store fails" sets up its expectation only through `setupLegacyFn`. It passes only because the storage call matches the legacy expectation on the shared mock. No test checks mode 3's defining behaviour: reads come from Storage only, and writes go to Storage and then asynchronously to Legacy. Mode 1 tests use `AssertNotCalled` for this; mode 3 has none.

**5. Minor (judgement call, `instrumentation.md` → "Start the log message with a capital letter")**
- **Where:** `dualwriter_mode3.go:44, 69, 85, 101, 128, 155`
- **Claim:** Messages such as "unable to create object in storage" start lowercase.
- **Caveat:** The guide is written for `pkg/infra/log`, while this package uses klog, and modes 1 and 2 also use lowercase. I would not block on it.

**6. Minor (process, `create-pull-request.md` → "Commit message format" / "Pull request titles")**
- **Where:** the commit list.
- **Claim:** Subjects lack the `<Area>: ` prefix, for example "Dual writer: mode 3" and "[REVIEW] FInish mode 3 and add tests". Grafana squashes commits, so only the PR title matters, and I can't see it.

## Spec
There is no spec. No issue reference appears in the commits and none was supplied, so this axis was not evaluated.

## Outside both axes
These are correctness bugs I saw while reading. I did not rank or verify them:
- **Wrong metric on Storage errors:** `dualwriter_mode3.go:45` and `:129` record a Storage failure with `recordLegacyDuration`.
- **Wrong metric for the Legacy call:** `dualwriter_mode3.go:166` records the Legacy `DeleteCollection` with `recordStorageDuration`.
- **Wrong logger in the context:** `dualwriter_mode3.go:97` passes `d.Log` instead of `log` to `klog.NewContext`.
- **Legacy writes may be cancelled:** the async Legacy goroutines (lines 50, 108, 134, 161) build their context from the request `ctx`. If the request context is cancelled after the handler returns, those writes can be cancelled before they finish. Mode 1 uses the same pattern, so it matches the codebase, but it is still risky.

## Summary
- **Standards:** 6 findings (1 Important, 5 Minor). The worst is the object name used as a metric label value (`dualwriter_mode3.go:106`).
- **Spec:** 0 findings, because there is no spec.

## Files not reviewed
- **`go.work.sum`** (+15 lines): generated checksum entries from the "Update dependencies" commit. No standard applies to its contents beyond its being auto-generated. I did not check whether these entries are needed or relate to this change.

All other files in the patch were reviewed:
- `pkg/apiserver/rest/dualwriter_mode1_test.go`
- `pkg/apiserver/rest/dualwriter_mode3.go`
- `pkg/apiserver/rest/dualwriter_mode3_test.go`
- `pkg/tests/apis/playlist/playlist_test.go`: conforms. The new subtests sit inside `TestIntegrationPlaylist`, which has the `testing.Short()` guard and uses `require` for errors.

Not checked: nothing was compiled, linted or run, so every claim is reasoned from source. The package `rest` has no `TestMain`; that predates this change and the diff does not touch it.
