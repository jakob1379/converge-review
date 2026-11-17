Review: grafana__grafana__80329, base a886bd3c..HEAD 04cfa3bf. I invoked the `mattpocock-skills:code-review` skill and did the review myself, without its sub-agents.

There was no spec, so I skipped the Spec axis. Standards sources: contribute/backend/style-guide.md, contribute/backend/instrumentation.md, CONTRIBUTING.md. I ran no tests or builds, so every finding is reasoned from the code and the docs.

## Standards

1. **pkg/services/annotations/annotationsimpl/xorm_store.go:534, 537, 554, 557, 576, 579 — Important.** Debug logging was left in at Error level on a code path that is working normally.
   - **Rule breached:** contribute/backend/instrumentation.md, "Log levels": Error is for "messages indicating some operation failed… and the program didn't have a way of handle the error". High-frequency messages belong at Debug.
   - **Evidence:** each batch logs twice at Error, even when it succeeds. Each first line (534/554/576) includes the full `ids` slice, which holds up to `cleanupjob_batchsize` IDs; the new test sets this to 32767. The cleanup job will flood logs with Error entries on every run.
   - **Rule breached:** the same doc's naming rules ("Start the log message with a capital letter"; "Use the key _error_ when logging Go errors"). Lines 537, 557 and 579 start lowercase ("cleaned annotations by time", "cleaned tags"), and all six lines use the key `"err"` instead of `"error"`.
   - **Fix:** delete these lines or demote them to Debug, drop `ids` and `cond`, and use the key `error`.
   - **How to see it:** run `TestIntegrationAnnotationCleanUp` with `-v` and watch Error-level log output appear on a passing run. I did not run it.

2. **pkg/services/cleanup/cleanup.go:77 — Important.** The interval of the global cleanup ticker went from `time.Minute * 10` to `time.Minute * 1`. This looks like a debugging leftover (it arrived in commit 4ecfade258, "Iterate in batches").
   - **Evidence:** the ticker drives every cleanup job, not just annotations: tmp files, snapshots, dashboard versions, images, invites, short URLs and query history. Those now run 10x as often on every Grafana instance.
   - The per-run timeout (`const timeout = 9 * time.Minute`, cleanup.go:~89) was sized for a 10-minute interval and was not changed. Now a run can last up to 9 minutes while ticks arrive every minute, so the job runs almost continuously.
   - Nothing in the commit messages or the docs explains or documents the change. This is not a documented-standard breach, but it is unrelated to the annotation-batching change, so I'm flagging it as scope creep.

3. **pkg/services/annotations/annotationsimpl/cleanup_test.go:116-120 — Minor, judgement call.**
   - **Rule:** style-guide.md, "Cleanup": use `t.Cleanup`.
   - **Evidence:** the sub-test registers its `t.Cleanup` only after `createTestAnnotations` and the count assertions run. If `createTestAnnotations` fails a `require` partway through the insert, cleanup is never registered. Its leftover rows then break the shared `fakeSQL` for every later sub-test.
   - **Fix:** register the cleanup before seeding.

4. **xorm_store.go, `deleteByIDs` — Minor, judgement call.** Two possible smells:
   - **Mysterious Name:** `x, y := r.deleteByIDs(...)` appears 3 times.
   - **Duplicated Code:** the fetch → log → delete → log closure is copied three times (time, count, tags).

**Compliant:**
- The tests were renamed to `TestIntegration*` and given the `testing.Short()` guard, as style-guide.md "Integration Tests" requires.
- The tests use testify `require`/`assert` correctly.
- The builtin `min` is fine: go.mod is at go 1.21.
- The SQLite inline-ID branch formats only `int64` values read back from the DB, so there is no injection risk.

## Spec

Skipped: there is no spec or issue reference. The commit messages ("Split subquery when cleaning annotations", "Work around parameter limit on sqlite…") match the xorm_store changes. The cleanup.go ticker change matches no stated goal (see Standards 2).

**Summary:** Standards has 4 findings (2 Important, 2 Minor). The worst is the Error-level logging of full ID lists on every batch, alongside the 10x faster cleanup ticker. Spec: not run, no spec.

**Files not reviewed:** none. I reviewed all 3 files in the patch (cleanup_test.go, xorm_store.go, cleanup.go). I did not check MySQL or Postgres behaviour of the new `LIMIT`/`OFFSET` conditions passed to `fetchIDs`.
