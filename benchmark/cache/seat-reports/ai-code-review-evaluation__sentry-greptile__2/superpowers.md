## Code review: change.patch (base 28e3db2520, head 8ab8814511)

**Process note.** I loaded `superpowers:requesting-code-review`. That skill says to hand the review to a reviewer subagent. You told me not to spawn agents, so I reviewed the patch myself against its checklist. There was no spec. I ran no tests: Django is not installed here and I was told not to install anything. Every proposed test below is a test I expect to fail, not one I watched fail.

The patch holds two unrelated commits:
- **74618671bf, spans eviction.** The span buffer moves from Redis SETs to ZSETs and evicts spans past 1000.
- **8ab8814511, audit-log "optimized pagination".** This one is broken and partly a security smell. Do not merge it.

### Critical

**C1. The new audit-log pagination path crashes whenever there is at least one row.** `src/sentry/api/paginator.py:838-843`
- `OptimizedCursorPaginator.get_item_key` copies the integer `Paginator` version, `math.floor(getattr(item, "datetime"))`. The endpoint uses it with `order_by="-datetime"` (`organization_auditlogs.py:82`).
- `build_cursor` calls `key(...)` on the results, so every non-empty page raises `TypeError: must be real number, not datetime.datetime`. I confirmed that error with plain Python: `math.floor(datetime.now())`.
- `value_from_cursor` returns the raw integer cursor value. It then lands in a `datetime <= <int>` SQL comparison, so even the follow-up cursor pages are broken. The class duplicates `BasePaginator.get_result` and gets the key logic of `DateTimePaginator` wrong.
- Failing test (not run): in `tests/sentry/api/endpoints/test_organization_auditlogs.py`, as the owner (who has global access), create one `AuditLogEntry`, then call `self.get_success_response(self.organization.slug, qs_params={"optimized_pagination": "true"})`. I expect a 500 / TypeError.

**C2. Every audit-log request with no organization member now fails with a 500, even without the new flag.** `src/sentry/api/endpoints/organization_auditlogs.py:71`
- `enable_advanced = request.user.is_superuser or organization_context.member.has_global_access` runs on every request.
- `RpcUserOrganizationContext.member` is typed `RpcOrganizationMember | None` (`organizations/services/organization/model.py:346`). It is None whenever the caller is not a member: for example an API key or org token with `org:write` (`AnonymousUser`, `user_id=None`).
- The superuser short-circuit only helps users whose superuser flag is set. Every other non-member hits `AttributeError: 'NoneType' object has no attribute 'has_global_access'` and gets a 500.
- Reasoned, not run. A test would call the endpoint with an `ApiKey` that has `scope_list=["org:write"]` and expect 200.

### Important

**I1. Negative offsets from the client are not validated and give a 500. The code comments also misstate the security model.** `src/sentry/api/paginator.py:877-882` and `:182`
- `Cursor.from_string` accepts `0:-5:0`. The "advanced" branch slices `queryset[-5:...]`. Django 5.2.1 (`requirements-frozen.txt:36`) raises `ValueError("Negative indexing is not supported.")`. `paginate()` only catches `BadPaginationError` (`api/base.py:540`), so the result is a 500.
- The comments say this "enables access to data beyond normal pagination bounds" and is "safe because permissions are checked at the queryset level". That is a stated intent to bypass pagination bounds. It only fails to work because Django refuses negative slices.
- In `BasePaginator` (shared by every paginated endpoint), `is_prev` cursors still pass negative offsets through, giving the same 500. Non-prev negative offsets are now silently clamped to 0. Line 192 still compares against the unclamped `offset`.
- Reject negative offsets in `Cursor.from_string`, or raise `BadPaginationError`, and remove the "advanced" branch.
- Failing request (reasoned): `GET /api/0/organizations/{org}/audit-logs/?optimized_pagination=true&cursor=0:-10:0` as owner returns 500.

**I2. A rolling deploy hits WRONGTYPE errors on span-buffer keys that already exist.** `src/sentry/scripts/spans/add-buffer.lua:46,52`, `src/sentry/spans/buffer.py:197,434`
- `span-buf:s:*` keys written by old consumers are SETs and live up to `redis_ttl` (3600 s).
- New code runs `zadd`, `zcard`, `zunionstore` and `zscan` on them, and Redis returns WRONGTYPE.
- redis-py pipelines raise on the first error by default. So both `process_spans` batches and `flush_segments` fail on any trace that spans the deploy, which can crash-loop the consumer and flusher for up to an hour.
- The patch has no migration and no type check/fallback. Reasoned.

**I3. `max_segment_spans` is now dead config, and the limit it set is hardcoded as 1000 in Lua.** `src/sentry/spans/buffer.py:150,158` and `add-buffer.lua:62-63`
- The span-count check in `_load_segment_data` was deleted, but the constructor parameter (default 1001) and the attribute remain.
- Eviction uses a literal 1000 and is not passed in as an ARGV, so the setting does nothing.
- No test covers the new eviction (more than 1000 spans; which spans survive).

### Minor

- **M1. Duplicate payloads distort eviction order.** `add-buffer.lua:47,53`: `zunionstore` defaults to `AGGREGATE SUM`. If the same payload is in both sets (Kafka redelivery), its score doubles, so it is effectively never evicted. Use `AGGREGATE MAX`.
- **M2. The segment span itself can be evicted.** `add-buffer.lua:63`: `zpopmin` keeps the 1000 latest-ending spans. A segment span that ends early (for example a remote or `is_remote` segment) is dropped, and `has_root_span` is then False at flush time. The patch does not document or meter this.
- **M3. Redirect depth limit cut silently.** `add-buffer.lua:30`: the limit drops from 10000 to 1000, and the comment explaining the limit's effect is deleted.
- **M4. Wrong superuser check.** `organization_auditlogs.py:71` uses `request.user.is_superuser`, which only checks the flag in the database. Sentry's convention, also used by `OrganizationAuditPermission` (`api/bases/organization.py:124`), is `is_active_superuser(request)`.
- **M5. Lint and pre-commit failures.** `git diff 28e3db2520 HEAD --check` reports trailing whitespace at `organization_auditlogs.py:72,89` and `paginator.py:824,827,829`. `paginator.py` also has 3 blank lines before the new class and a trailing blank line at EOF. The repo's pre-commit `trailing-whitespace` and `end-of-file-fixer` hooks and flake8 will fail. The comment in `utils/cursors.py:26-27` describes behaviour the `Cursor` class does not implement.
- **M6. Outdated docs.** The module docs in `buffer.py` (lines 37-61) still describe `span-buf:s:*` as "set keys".

### Files not reviewed

None. I reviewed all 9 files. I only scanned the test-fixture edits (`tests/sentry/spans/test_buffer.py`, `test_flusher.py`, `test_consumer.py`) to confirm the new required `end_timestamp_precise` field is supplied everywhere `Span(...)` is constructed. grep found no other construction sites in `src/` or `tests/`.

### Verdict

Revert 8ab8814511 entirely. C1, C2 and I1 cannot be fixed piecemeal: the feature has no correct use. The spans commit needs a rollout plan for I2 and wiring for I3 before merge.
