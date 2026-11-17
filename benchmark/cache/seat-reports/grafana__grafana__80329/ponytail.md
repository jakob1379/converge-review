## Over-engineering review: grafana__grafana__80329 (change.patch, base a886bd3c79 to head 04cfa3bfd4)

**What this change does:** Annotation cleanup used to run one `DELETE ... WHERE id IN (subquery)` statement per batch. Now each batch first selects the IDs, then deletes them by ID list. The stated reason is to avoid MySQL deadlocks when inserts run at the same time. On SQLite, when the batch size is over 999, the IDs go straight into the SQL text instead of as parameters. The tests became integration tests, insert their data in bulk, and add a 40003-row case for the SQLite parameter limit.

Load I assumed: one Grafana server per DB. The cleanup job runs on a ticker, and `cleanupjob_batchsize` defaults to 100 (`pkg/setting/setting.go:710`). I read the patched source directly and ran no tests (the brief says not to). All findings below are reasoned, not reproduced.

### Must fix

1. **Debug logging left in at Error level, and it logs every ID** (`pkg/services/annotations/annotationsimpl/xorm_store.go:534,537,554,557,576,579`)
   - **What this is:** Each cleanup batch now writes two `r.log.Error` lines. The first holds the full `ids` slice and the SQL condition. The second always has `"err"` set, even when it is nil.
   - **Problem:** These are leftover debug lines. With the default batch size of 100, every batch writes an ERROR line listing 100 IDs, even on a healthy server. With batch size 32767 (the size the new test uses), one log line holds 32k IDs. Alerting on error logs will fire with nothing wrong. At line 534 the `"err", err` value is always nil, because the error was already returned on the line above.
   - **Fix:** Delete all six lines. If a log is wanted, keep one `r.log.Debug` per batch with only the count. This also removes the `x, y :=` temporaries, so each closure can end with `return r.deleteByIDs(ctx, table, ids)`.
   - **If we skip it:** Error logs fill up with noise on every install, and real errors get lost.

2. **Cleanup ticker changed from 10 minutes to 1 minute** (`pkg/services/cleanup/cleanup.go:77`)
   - **What this is:** This ticker drives every cleanup job in Grafana (tmp files, snapshots, annotations, and more), not only annotations.
   - **Problem:** Nothing in the patch explains the change, and the annotation fix does not need it. It looks like a local-testing tweak. It makes every cleanup query run 10 times as often on every install.
   - **Fix:** Revert to `time.Minute * 10`.
   - **If we skip it:** All users get 10 times the cleanup load on the database. Because of finding 1, they also get 10 times the error-log noise.

### Should fix

3. **Two SQL paths in `deleteByIDs` where one is enough; the repo already inlines integer IDs** (`xorm_store.go:604-622`, `asAny` at `:632-638`)
   - **What this is:** For SQLite with batch size over 999, the IDs are written into the SQL text. Everywhere else they go in as `?` placeholders, which needs the extra `asAny` helper.
   - **Problem:** The IDs are `int64` values just read from the database, so putting them in the SQL text carries no injection risk. Injection means attacker-controlled text ending up inside the SQL. This same file already writes integer IDs straight into SQL on every database (`xorm_store.go:387-395`, the `dashboard_id IN (...)` built with `strconv.AppendInt`). Keeping two paths means two code paths to test, and the placeholder path still breaks on Postgres or MySQL if someone sets the batch size above 65535 (Postgres caps a statement at 65535 placeholders, MySQL at 65535). The comment's 999 is the limit for SQLite before 3.32. Newer SQLite allows 32766, yet the new test name talks about 3.32.0 and up.
   - **Fix:** Always build the list the way lines 387-395 do. Then delete the `GetDBType` branch, `sqliteParameterLimit`, `args`, `asAny` and the `migrator` import. That is about 20 lines gone.
   - **If we skip it:** We keep a branch that only runs on SQLite with a non-default batch size, plus a latent placeholder limit on the other databases.

4. **Building the ID list is quadratic** (`xorm_store.go:609-612`)
   - **What this is:** The SQLite path builds the list with `values = fmt.Sprintf("%s, %d", values, v)` in a loop.
   - **Problem:** Each step copies the whole string again. At 32767 IDs that is about 32k allocations of a string that keeps growing (hundreds of MB copied) for every batch. "Quadratic" means the cost grows with the square of the batch size.
   - **Fix:** Covered by the fix for 3, which uses `strconv.AppendInt` on one buffer.
   - **If we skip it:** Large batches on SQLite get slow and churn memory.

5. **The fetch-then-delete closure is copied three times** (`xorm_store.go:528-539`, `548-559`, `570-581`)
   - **What this is:** Each of the three cleanups builds a condition, calls `fetchIDs`, logs, calls `deleteByIDs`, and logs again.
   - **Problem:** The three copies are the same apart from the table name and the condition, and they have already drifted apart in their log messages. A future fix has to be made in three places.
   - **Fix:** Once finding 1 is fixed, each closure shrinks to about two lines, which is probably enough. Or merge `fetchIDs` and `deleteByIDs` into a single `cleanBatch(ctx, table, cond)` and pass that to `untilDoneOrCancelled`.
   - **If we skip it:** We keep about 15 extra lines, and the three copies keep drifting.

### Nice to have

6. **An empty-condition guard that no caller can trigger** (`xorm_store.go:586-588`)
   - **What this is:** `fetchIDs` returns an error when `condition == ""`.
   - **Problem:** All three callers pass a non-empty `fmt.Sprintf` string that always contains `annotationType` or `NOT EXISTS`, so the guard never fires. The function also builds the SQL in two steps for no reason.
   - **Fix:** Delete the guard and write `sql := fmt.Sprintf("SELECT id FROM %s WHERE %s", table, condition)`.
   - **If we skip it:** Three dead lines stay.

7. **A no-op rewrite of the MaxCount return** (`xorm_store.go:562-565`)
   - **What this is:** `return totalAffected, err` became `if err != nil { return totalAffected, err }` followed by the shared `return totalAffected, nil`.
   - **Problem:** The behavior is the same. It is only churn in the diff.
   - **Fix:** Keep the original line.
   - **If we skip it:** Nothing breaks.

8. **The bulk-insert loop is pasted twice in the test helper** (`cleanup_test.go:273-291`)
   - **What this is:** Two copies of the same 500-row `InsertMulti` chunk loop, one for annotations and one for annotation tags. Each also calls `require.NoError` inside the DB callback and then returns nil.
   - **Problem:** It is duplicated test code.
   - **Fix:** Do both inserts in one `WithDbSession` with one loop body, and return the error rather than calling `require` inside the callback.
   - **If we skip it:** It costs only a few lines.

Verdict: fix 1 and 2 first (both are debug leftovers that change production behavior), then 3.
Lean: about -45 lines possible (logs about 6 plus temporaries, SQLite branch and asAny about 20, closure merge about 10, guard 3, test loop about 8).

Files not reviewed: none. I reviewed all three files in the patch: `cleanup_test.go`, `xorm_store.go` and `cleanup/cleanup.go`.
Not checked: I did not run anything, so the claims are reasoned from the code. I also did not check whether fetching IDs and then deleting them really removes the MySQL deadlock. That is outside an over-engineering-only seat.
