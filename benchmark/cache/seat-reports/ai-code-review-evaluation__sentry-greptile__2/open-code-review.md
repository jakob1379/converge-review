## Review of change.patch (base 28e3db2520..HEAD, two commits: spans eviction + audit-log "optimized pagination")

**How it was run.** I used the `open-code-review:delegate-review` skill in range mode. `ocr delegate preview --from 28e3db2520 --to HEAD` matched the patch's 9 files. OCR rules came back only as the generic Python checklist, and the repo has no AGENTS.md or CLAUDE.md, so there is no documented project standard to check against. There is no spec either.

You said report only, so I applied none of the skill's auto-fix step.

I couldn't execute anything: there is no venv, Django is not installed, and installing was not allowed. Every claim below is reasoned from the source. The only thing I actually ran is a stdlib check that `math.floor(datetime)` raises `TypeError`.

### Findings

**1. Critical: `src/sentry/api/paginator.py:838-843` breaks the new audit-log path on any non-empty page.**
- **Claim:** `OptimizedCursorPaginator.get_item_key` and `value_from_cursor` were copied from the integer `Paginator`. The endpoint uses this class with `order_by="-datetime"`.
- **Evidence:**
  - `self.key` is `"datetime"`, which is a `DateTimeField` (`src/sentry/models/auditlogentry.py:69`).
  - `get_item_key` does `math.floor(<datetime>)`. Running `python3 -c "import math,datetime; math.floor(datetime.datetime.now())"` gives `TypeError: must be real number, not datetime.datetime`.
  - `build_cursor` calls `key()` on the results whenever there are any, so `?optimized_pagination=true` returns a 500 for every org that has audit logs.
  - `value_from_cursor` passes the raw integer cursor value into `build_queryset`'s raw `"datetime" <= %s` SQL. That compares a timestamptz to an integer, so even if the key were fixed, follow-up pages would fail or be wrong.
  - `DateTimePaginator` (lines 230-241) is the correct implementation.
- **Failing test (not executed):** add to `tests/sentry/api/endpoints/test_organization_auditlogs.py`:
  `self.create_audit_entry(...); self.get_success_response(self.organization.slug, qs_params={"optimized_pagination": "true"})`
  The org owner has global access, so the request takes the new branch and raises `TypeError`.

**2. Important: `src/sentry/api/paginator.py:876-881` (the "advanced" branch) and `src/sentry/api/paginator.py:182` (the shared `BasePaginator` change).**
- **Claim:** The negative-offset branch is meant to "access data beyond normal pagination bounds". What it actually does is crash.
- **Evidence:**
  - Django 5.2.1 (`requirements-frozen.txt`) raises `ValueError("Negative indexing is not supported.")` on `qs[-n:m]`.
  - `base.paginate` only catches `BadPaginationError`, so a cursor like `0:-5:0` or `0:-5:1` gives a 500, not a 400. `Cursor.from_string` accepts negative offsets.
  - The same applies to every `BasePaginator` subclass app-wide (`Paginator`, `DateTimePaginator`) whenever `is_prev=1`.
  - The code comments claim "the underlying queryset will handle boundary conditions" and "permissions are checked at the queryset level". The first is false. The second is irrelevant to an offset.
  - For non-prev cursors, the clamp to 0 hides the negative offset but leaves `cursor.offset` negative when `build_cursor` uses it, which produces inconsistent next/prev cursors.
  - The "advanced" branch can't do anything the `else` branch doesn't. It just guarantees the crash.
  - The right move is to drop the whole negative-offset idea and reject `offset < 0` with `BadPaginationError`.
- **Failing test (not executed):** `self.get_error_response(org.slug, qs_params={"cursor": "0:-5:1"}, status_code=400)` fails with a 500. The same request with `optimized_pagination=true` also returns 500.

**3. Important: `src/sentry/api/endpoints/organization_auditlogs.py:71` throws `AttributeError` for callers with no membership, even when the flag is off.**
- **Claim:** `enable_advanced` is computed on every request, and it dereferences `organization_context.member.has_global_access`.
- **Evidence:**
  - `RpcUserOrganizationContext.member` is `RpcOrganizationMember | None` (`organizations/services/organization/model.py:346`).
  - `OrganizationPermission.determine_access` has a `request.auth` path for callers with no authenticated user (`from_rpc_auth`, e.g. legacy org `ApiKey` with `org:write`). There `request.user` is `AnonymousUser`, so `is_superuser` is False and `member` is None. Result: `AttributeError`, a 500 on the plain audit-log listing that worked before the patch.
  - Two lesser issues on the same line:
    - It uses the raw `request.user.is_superuser` flag instead of `is_active_superuser(request)`, which is what the permission class itself uses (`api/bases/organization.py:124`).
    - It is evaluated even when `optimized_pagination` is absent.
- **Status:** reasoned. Test sketch: authenticate with a legacy `ApiKey` that has scope `org:write` and GET the endpoint.

**4. Important: `src/sentry/spans/buffer.py:197` and `src/sentry/scripts/spans/add-buffer.lua:46-55` make a rolling deploy unsafe.**
- **Claim:** `span-buf:s:*` keys change Redis type from set to sorted set with no migration or dual-read.
- **Evidence:**
  - New consumers run `ZADD`, `ZCARD`, `ZUNIONSTORE` and `ZSCAN` against keys that old pods created with `SADD`. Old pods run `SADD`/`SSCAN` against new zsets.
  - Both directions return `WRONGTYPE`. That raises from `p.execute()` and crash-loops the process/flush consumers until the keys expire, which takes up to `redis_ttl` (default 3600s, `buffer.py:151`).
  - Spans buffered in old-type keys are also lost from flushing.
- **Status:** reasoned. Needs a key-prefix bump, or a drain-then-deploy note.

**5. Minor: `src/sentry/spans/buffer.py:150,158` vs `add-buffer.lua:62-63`.**
- **Claim:** `max_segment_spans` (default 1001) is still accepted and stored but is never read now. The cap is hard-coded as `1000` in Lua, and the `segment_span_count_exceeded` metric is gone.
- **Evidence:** grep finds no other reader of `max_segment_spans`. The parameter is now dead, and its value disagrees with the real limit.
- **Also:** `zpopmin` silently evicts the earliest-ending spans with no metric or log, so truncation is now invisible.

**6. Minor: `add-buffer.lua:30`.**
- **Claim:** The redirect-walk limit drops from 10000 to 1000, and the comment explaining what the limit means was deleted.
- **Evidence:** Segment trees deeper than 1000 now won't be joined correctly, and nothing records why.

**Not raised:**
- `factory.py:141` (`val["end_timestamp_precise"]`): I couldn't confirm whether the field is required in the `ingest-spans` v1 schema, because `sentry_kafka_schemas` is not installed.
- The patch adds no tests for `OptimizedCursorPaginator` or the endpoint branch. That is why findings 1-3 slipped through.

### Coverage
- **Files in preview:** 9 total. I reviewed 6: `organization_auditlogs.py`, `paginator.py`, `add-buffer.lua`, `spans/buffer.py`, `consumers/process/factory.py` and `utils/cursors.py`. Coverage of the OCR-reviewable set is 100%.
- **Excluded by OCR's `default_path` rule:**
  - `tests/sentry/spans/consumers/process/test_consumer.py`
  - `tests/sentry/spans/consumers/process/test_flusher.py`
  - `tests/sentry/spans/test_buffer.py`

  I read these three diffs anyway. They only add `end_timestamp_precise` fixtures, with nothing to flag, but I didn't formally review them.

None of the suggested tests were executed. The rolling-deploy finding (4) is inferred from Redis type semantics, not observed.
