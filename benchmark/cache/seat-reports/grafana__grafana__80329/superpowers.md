Review of grafana__grafana__80329 change.patch (base a886bd3c79, head 04cfa3bfd4). Seat: correctness. No spec was given, so I judged against the commit history: the PR splits annotation cleanup into SELECT-ids then DELETE-by-ids to avoid MySQL deadlocks and works around SQLite's parameter limit. I loaded superpowers:requesting-code-review and did the review myself, with no subagents, as instructed. I ran no tests or builds, so every finding below is reasoned from the code.

Verdict: the core approach (fetch ids, delete by ids, loop until a batch affects 0 rows, check context cancellation between batches) is sound. Do not merge as-is. Two pieces of debugging scaffolding were left in, and both cause real production problems.

## Important

**1. Debug logging left in at Error level, including the full list of ids.**
- Where: pkg/services/annotations/annotationsimpl/xorm_store.go, in the patched CleanAnnotations (MaxAge and MaxCount closures) and CleanOrphanedAnnotationTags. These are the `r.log.Error("Annotations to clean by time"...)`, `"cleaned annotations by time"`, `"... by count"`, `"Tags to clean"` and `"cleaned tags"` calls.
- Claim: every batch writes two Error-level lines, even when nothing was deleted (count 0, err nil). One cleanup run calls CleanAnnotations for three annotation types, with the MaxAge and MaxCount phases each, plus the tag pass. Each loop needs at least one extra batch to find out it is done. So a single idle run writes about 14 or more Error lines.
- The `"ids", ids` field dumps up to `cleanupjob_batchsize` ids per line. That is 100 by default, and 32767 in the new test.
- The logged `"err", err` value is always nil, because it is logged after the `if err != nil` return.
- Effect: anyone who alerts on error-level logs gets paged on every cleanup cycle, and log volume grows.
- Evidence: read the diff. Run `grep -n 'r.log.Error' pkg/services/annotations/annotationsimpl/xorm_store.go` to see the six new calls.
- Fix: remove them, or drop them to Debug and remove the `ids` field.

**2. The cleanup ticker changed from 10 minutes to 1 minute, for every cleanup job.**
- Where: pkg/services/cleanup/cleanup.go:77.
- Claim: this is not part of the stated change and looks like a local testing leftover. It does not only affect annotations. `clean()` runs all 8 jobs on each tick: temp files, snapshots, dashboard versions, images, annotations, invites, short URLs and query history.
- The per-run timeout is still `9 * time.Minute` (cleanup.go, `clean()`). That timeout was sized for the 10-minute interval. With a 1-minute ticker, a slow run is followed straight away by the next one, because time.Ticker buffers one tick. Cleanup can then run back to back against the DB on every Grafana instance.
- Effect: about 10x more cleanup query load overall, on a PR whose goal is to reduce lock contention.
- Evidence: the one-line diff hunk. Nothing in the commit messages justifies it.
- Fix: revert to `time.Minute * 10`.

## Minor

**3. Building the inlined SQLite id list takes quadratic time.**
- Where: xorm_store.go, `deleteByIDs`, SQLite branch: `values = fmt.Sprintf("%s, %d", values, v)` in a loop.
- At batch size 32767 (the size the new test uses) the string reaches about 230KB. Rebuilding it on every iteration copies roughly 3–4 GB per batch, which costs seconds per batch on SQLite.
- Fix: use `strings.Builder`, or `strconv.AppendInt` into a `[]byte`.
- Related: the inlined statement can hit SQLITE_MAX_SQL_LENGTH (1,000,000 bytes by default) once the batch is above roughly 140k ids.
- Reasoned, not measured.

**4. No upper bound on batch size for the placeholder path on MySQL and Postgres.**
- Where: xorm_store.go, `deleteByIDs`, else branch.
- Postgres and MySQL prepared statements are capped at 65535 placeholders. If `cleanupjob_batchsize` is set above 65535, the delete fails on every run. Before this patch the batch size was only a LIMIT, so any value worked.
- Only an operator who sets an extreme value hits this, but it is a new way for cleanup to fail. Clamp the size or chunk the ids.
- Reasoned.

**5. The code comment gets the SQLite limit wrong.**
- Where: xorm_store.go, `deleteByIDs`.
- The comment says "SQLite has a parameter limit of 999". That is true only before SQLite 3.32. From 3.32 on the limit is 32766, which is what the new test name refers to.
- The code still works because it inlines whenever batch size > 999. The comment is just misleading.

**6. One test now does something different from what its name says.**
- Where: cleanup_test.go, case "running the max count delete again should not remove any annotations".
- Each case now seeds fresh data, so this case no longer runs cleanup a second time over the state the previous case left. It now checks that 9 annotations under a max count of 3 per type delete nothing. That is a valid assertion, but nothing tests "run twice is idempotent" any more. Rename the case or restore the second run.

**7. Seeded data can leak into later subtests if seeding fails.**
- Where: cleanup_test.go, subtest body.
- `t.Cleanup` is registered after `createTestAnnotations` and the count asserts. If `createTestAnnotations` hits `require.NoError` part-way through (FailNow), the cleanup is never registered. The partly inserted rows then leak into the next subtest, which hides the real failure behind count mismatches.
- Fix: register the cleanup before seeding.

**8. Possible Postgres sequence drift from explicit ids.**
- Where: cleanup_test.go, `createTestAnnotations`, which sets `ID: int64(i + 1)` explicitly.
- I confirmed xorm only skips an autoincrement column when its value is zero (pkg/util/xorm/session_insert.go:153 and :204), so these ids really are written.
- On Postgres, explicit ids do not advance `annotation_id_seq`. Today it is harmless because every subtest empties the table. Any later test in the same DB that seeds with explicit ids and then inserts through the sequence, without clearing, would hit a duplicate key. Reasoned, low risk.

## Checked and found OK
- `strings` is already imported.
- The `min` builtin is fine: go.mod says go 1.21.
- `GetDBType() == migrator.SQLite` compiles, because `migrator.SQLite` is an untyped const.
- The `annotationTag` struct already exists at base.
- The loop terminates on a batch that affects 0 rows.
- Context cancellation is checked before every batch.
- The MaxCount path no longer returns early, so its behaviour is unchanged.
- Inlining int64 ids into the SQL string is not an injection risk.
- Expected counts in the 40003-row test case: the i%3 split gives 13335/13334/13334, keeping 1 per type deletes 40000, which matches.

## Declined to judge
- Whether splitting SELECT and DELETE outside a transaction actually removes the MySQL deadlock. That needs MySQL under concurrent inserts. The under-deletion trade-off is documented in the code comment and acceptable.

## Files not reviewed
None. All three files in the patch were reviewed: cleanup_test.go, xorm_store.go and cleanup.go.

I did not run any test (as instructed), so Important #1 and #2 have no failing command. Both are plain from the diff, and the cheapest checks are `grep -n 'r.log.Error' pkg/services/annotations/annotationsimpl/xorm_store.go` and `grep -n 'NewTicker' pkg/services/cleanup/cleanup.go`.
