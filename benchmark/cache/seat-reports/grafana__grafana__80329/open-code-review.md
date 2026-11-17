OCR delegate review, correctness seat, range a886bd3c..04cfa3bf. I found 2 Important and 3 Minor issues. The two Important ones look like debug leftovers that would ship: error-level logging that includes the full list of deleted IDs, and the cleanup interval cut from 10 minutes to 1. The core change, which fetches IDs and then deletes them in batches, is logically sound: the loop stops correctly, it respects cancellation, and errors propagate the same way as before. xorm's `Find(&[]int64)` handles a single column, and the SQLite inlined IDs are int64 values the code fetched itself, so there is no injection risk. I ran no tests or builds, as instructed. Every claim below is reasoned from the source, with a grep that shows it.

## Findings

**1. Important — `pkg/services/annotations/annotationsimpl/xorm_store.go:533, 537, 556, 560, 577, 580`: debug logging at error level, including the full ID list.**
- Every batch calls `r.log.Error(...)` with `"ids", ids`, the whole slice (up to `AnnotationCleanupJobBatchSize` entries, so 32767 in the new test). The first log of each pair always prints `"err", nil`.
- `untilDoneOrCancelled` only stops after a batch that affects 0 rows, so each enabled path (alert, dashboard and API by age and by count, plus orphaned tags) logs at least 2 error lines per run, even when there is nothing to delete.
- Combined with finding 2, a healthy instance writes many error lines every minute. That breaks error-rate alerting and inflates log volume with large ID dumps.
- Fix: `r.log.Debug`, and drop `ids`, or log only the count.
- Check: `grep -n 'r.log.Error' pkg/services/annotations/annotationsimpl/xorm_store.go` shows 6 new call sites inside the cleanup closures.

**2. Important — `pkg/services/cleanup/cleanup.go:77`: `time.NewTicker(time.Minute * 1)` (was 10 minutes).**
- This runs the whole cleanup suite 10 times as often on every instance: temp files, snapshots, dashboard versions, images, annotations, invites, short URLs, query history.
- The annotation-cleanup purpose of the PR does not explain this change. It contradicts the per-run timeout `const timeout = 9 * time.Minute` at line 89, which assumes a 10-minute cadence.
- The ticker drops ticks, so runs don't overlap. But a slow run (up to 9 minutes) is followed immediately by another, so cleanup becomes nearly continuous DB load.
- In HA setups every replica does this. That adds lock contention, which is the problem the xorm_store change is trying to fix.
- Check: `git --no-pager diff a886bd3c..HEAD -- pkg/services/cleanup/cleanup.go`.

**3. Minor — `xorm_store.go:613-616`: the bound-parameter path has no cap for Postgres or MySQL.**
- When the database is not SQLite, `deleteByIDs` always uses one placeholder per ID.
- Postgres and MySQL both reject statements with more than 65535 bind parameters. With `cleanupjob_batchsize` above 65535, every DELETE would fail, so annotation cleanup would stop working.
- The old single-statement SQL had no parameters, so this is a regression, but only for a non-default config (default is 100, `setting.go:710`).
- Fix: chunk the IDs, or cap the batch size.

**4. Minor — `xorm_store.go:609-612`: quadratic string building on the SQLite inlined path.**
- `values = fmt.Sprintf("%s, %d", values, v)` inside the loop copies the growing string on every iteration, which is O(n²).
- At batch size 32767 the final string is about 200KB, so each batch copies roughly 3–4 GB. That is seconds of CPU per batch, and it only applies on SQLite with batch size above 999.
- Fix: `strings.Builder` with `strconv.AppendInt`.

**5. Minor — `xorm_store.go:604-608`: the SQLite branch gates on configured batch size, and the comment states the old limit.**
- The branch checks `r.cfg.AnnotationCleanupJobBatchSize`, not `len(ids)`. That is correct today because `len(ids)` can never exceed the batch size, but it is fragile.
- The comment says SQLite's limit is 999, while the new test's name refers to 32766 for SQLite 3.32 and later. 999 is the safe, conservative choice; the comment just doesn't say why. No behavioural bug.

## Coverage
- `total_files` 3, `reviewed_files` 2 (`xorm_store.go`, `cleanup/cleanup.go`), `skipped_files` 1, `coverage_rate` 67%.
- Skipped: `pkg/services/annotations/annotationsimpl/cleanup_test.go`. OCR's `default_path` rule excludes `*_test.go`. I read its diff only for context and found no correctness problems in it: it now inserts in batches with explicit IDs, cleans up per subtest, and uses the `min` builtin, which the module's `go 1.21` allows.
- No spec was provided, so there were no spec gaps to check.

I applied no fixes, per the task's report-only instruction, which overrides the skill's auto-fix step. I did not confirm findings 3 and 4 against a real Postgres, MySQL or SQLite instance.
