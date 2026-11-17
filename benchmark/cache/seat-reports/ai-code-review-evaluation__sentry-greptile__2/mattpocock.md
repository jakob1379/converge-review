I reviewed patch `change.patch` against base 28e3db2520 using the mattpocock-skills:code-review skill. Per your instruction I ran both axes myself and spawned no sub-agents.

The patch holds two commits:
- **74618671bf** `feat(spans): Evict spans during insert (#92393)`
- **8ab8814511** `feat(audit-logs): Enhanced pagination performance for high-volume deployments`

**Standards sources found:**
- `.github/CONTRIBUTING.md` only links to external docs and states no rules.
- `.cursor/rules/python_tests.mdc` asks for factories instead of `Model.objects.create`. The diff doesn't touch that pattern.
- `.pre-commit-config.yaml` (tooling): black, flake8, trailing-whitespace, end-of-file-fixer, mypy.

No `CLAUDE.md`, `AGENTS.md` or `CODING_STANDARDS` file exists in the repo.

I could not run tests. Django is not installed, and I was told not to install dependencies. Every "failing test" below is a command or test to run in a working Sentry dev environment. The two TypeErrors in finding 1 I confirmed directly with `python3 -c "import math,datetime; math.floor(datetime.datetime.now())"`, which raises `TypeError: must be real number, not datetime.datetime`.

## Standards

1. **`src/sentry/api/paginator.py:838-840` — Important.** `OptimizedCursorPaginator` errors on every non-empty page.
   - **Claim:** `OptimizedCursorPaginator.get_item_key` calls `math.floor`/`math.ceil` on `getattr(item, self.key)`. The audit-log endpoint uses `order_by="-datetime"`, so that value is a `datetime`, which raises a TypeError. `build_cursor` (`src/sentry/utils/cursors.py:160` and `_build_prev_values`) always calls `key()` when there are results, so `?optimized_pagination=true` returns 500 whenever there is at least one audit log row.
   - **Second bug:** `value_from_cursor` returns the raw int cursor value. `build_queryset` then compares the `datetime` column against that integer. `DateTimePaginator` (line 238) converts it to a datetime first; this class does not.
   - **Failing test:** in `tests/sentry/api/endpoints/test_organization_auditlogs.py`, as the org owner (who has global access), create one `AuditLogEntry` and call `self.get_success_response(self.organization.slug, qs_params={"optimized_pagination": "true"})`. It returns 500 with a TypeError.

2. **`src/sentry/api/paginator.py:874-881` — Important.** The negative-offset path the patch is built around cannot work.
   - **Claim:** the comment says "Django ORM properly handles negative slicing automatically", but it doesn't. With `django==5.2.1` (`requirements-frozen.txt:36`), `queryset[-5:...]` raises `ValueError("Negative indexing is not supported.")`. That is not a `BadPaginationError`, so `paginate()` (`src/sentry/api/base.py:540`) doesn't turn it into a 400, and the request returns 500.
   - **Upshot:** the "access to data beyond normal pagination bounds" the code describes never happens, so I found no data-exposure path. What remains is a 500 that any request can trigger: `Cursor.from_string` accepts `0:-5:0`.
   - **Failing request:** `GET /api/0/organizations/{slug}/audit-logs/?optimized_pagination=true&cursor=0:-5:0` as the owner returns 500.

3. **`src/sentry/api/endpoints/organization_auditlogs.py:71` — Important.** The privilege check can crash and uses the wrong superuser check.
   - **Crash:** `organization_context.member` is typed `RpcOrganizationMember | None` (`organizations/services/organization/model.py:346`, which notes it "can be None when the given user_id does not have membership"). `OrganizationAuditPermission` (`api/bases/organization.py:124`) lets non-members in through `is_active_superuser(request)`. A user who is not a member and lacks the raw `is_superuser` flag gets `AttributeError: 'NoneType' object has no attribute 'has_global_access'`.
   - **Wrong check:** it uses raw `request.user.is_superuser`, but the permission class it sits beside uses `is_active_superuser(request)`. That is the repo convention: 9 endpoint files use it. The raw flag grants the elevated path without an active superuser session.
   - **Gate is also too wide:** `has_global_access` is true for every member of an org with open membership, not just "authorized administrators".
   - This is reasoned, not run. To reproduce, call the endpoint with `optimized_pagination=true` as a non-member staff user, or as an org auth token where `request.user` is `AnonymousUser`.

4. **`src/sentry/api/paginator.py:179-184` — Minor.** The shared `BasePaginator` change is unscoped and its comment is false.
   - Every `BasePaginator` subclass (`Paginator`, `DateTimePaginator`, …) is changed. A negative offset on a next cursor is now silently clamped to 0, while on a prev cursor it is still passed through and still raises ValueError.
   - The comment says it "allow[s] negative offsets" and "the underlying queryset will handle boundary conditions". Neither is true.
   - There are no tests in `tests/sentry/api/test_paginator.py` for it.

5. **`src/sentry/utils/cursors.py:26-27` — Minor.** This hunk only adds a comment ("Allow negative offsets…") with no code change. It describes behaviour that doesn't exist.

6. **Tooling-enforced (Minor, will fail pre-commit):** `git diff 28e3db2520 HEAD --check` reports:
   - trailing whitespace at `organization_auditlogs.py:72` and `:89`, and `paginator.py:824`, `:827`, `:829`
   - a new blank line at EOF in `paginator.py:912` (end-of-file-fixer)
   - three blank lines before `class OptimizedCursorPaginator` (flake8 E303)

7. **Smell baseline (judgement calls only):**
   - **Duplicated Code:** `OptimizedCursorPaginator.get_result` (`paginator.py:844-911`) is a near copy of `BasePaginator.get_result`; the only difference is one branch.
   - **Duplicated Code** again: the two `self.paginate(...)` calls in the endpoint differ only by `paginator_cls` and one kwarg.
   - **Speculative Generality:** an `enable_advanced_features` flag that is only ever passed as `True`.
   - **Dead parameter:** `max_segment_spans` in `src/sentry/spans/buffer.py:150,158` is still accepted and stored but never read, because the check was removed at `buffer.py:446` and the limit is now hard-coded as `1000` in `add-buffer.lua:62-64`. Anyone setting it is silently ignored. The old default was 1001 and the new limit is 1000.

8. **`src/sentry/spans/buffer.py:197`, `:434` and `src/sentry/scripts/spans/add-buffer.lua:46,52` — Important (reasoned).** Switching the Redis key type from SET to ZSET breaks during rollout.
   - Existing `span-buf:s:*` keys are SETs and live for up to `redis_ttl=3600`. `zcard`, `zunionstore` and `zscan` on a SET key return WRONGTYPE.
   - Old consumers still running during a rolling deploy will hit the same WRONGTYPE when they `scard`/`sscan` the new ZSET keys.
   - The Lua error fails `p.execute()` in `process_spans`, which can crash-loop the consumer until the old keys expire.
   - There is no migration, key-prefix bump or dual-read.

9. **`add-buffer.lua:61-63` — Minor (reasoned).** `zpopmin` evicts the spans with the earliest `end_timestamp_precise`.
   - If the segment (root) span ends before some of its children (async work), its payload can be evicted while `has_root_span` stays true, and the segment flushes without its root span.
   - Nothing tests eviction. The test changes only add the new field to fixtures.
   - The redirect-loop cap drops from 10000 to 1000 (`add-buffer.lua:30`), and the comment explaining what the cap means was deleted.

## Spec

No spec was available: none was given, and neither commit message carries an issue reference I could fetch. I skipped this axis.

**Files not reviewed:** none. Every file in the patch was reviewed:
- `organization_auditlogs.py`, `paginator.py`, `cursors.py`
- `add-buffer.lua`, `spans/buffer.py`, `spans/consumers/process/factory.py`
- `test_consumer.py`, `test_flusher.py`, `test_buffer.py`

The three test files only add `end_timestamp_precise` to fixtures. I did not check that `end_timestamp_precise` is a required key in the `sentry_kafka_schemas` `SpanEvent` schema, because the package isn't installed. If it is optional, `factory.py:141` raises KeyError on messages that lack it.

**Summary:** Standards has 9 findings (4 Important, 5 Minor). The worst is that the opt-in `OptimizedCursorPaginator` path returns 500 on any non-empty result and on any negative offset (findings 1–2), and its privilege gate can raise AttributeError (finding 3). Spec has 0 findings because there was no spec.

Not checked: nothing was executed against Django or Redis, so every Important item except the confirmed `math.floor(datetime)` TypeError is reasoned from source.
