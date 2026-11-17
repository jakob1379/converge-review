Review of change.patch (range 74618671..8ab88145), done with open-code-review:delegate-review. OCR rules: Python system rules (precision over recall; correctness and security findings block).

Coverage: 3 of 3 files reviewed, 0 skipped, 100%.
- src/sentry/api/endpoints/organization_auditlogs.py [modified]: reviewed
- src/sentry/api/paginator.py [modified]: reviewed
- src/sentry/utils/cursors.py [modified]: reviewed. The only change is a comment; behaviour is unchanged.

## Findings

1. **Critical** at src/sentry/api/paginator.py:838-843 (`OptimizedCursorPaginator.get_item_key` / `value_from_cursor`).
   - **Claim:** The optimized audit-log path raises a 500 error on any non-empty page. The endpoint uses this paginator with `order_by="-datetime"`, so `self.key == "datetime"`. `get_item_key` copies the integer `Paginator` version and calls `math.floor`/`math.ceil` on a `datetime`. `build_cursor` calls that key on every result to build next and prev cursors, so it raises `TypeError`. `paginate()` catches only `BadPaginationError`, so the TypeError surfaces as a 500 error.
   - **Second bug:** `value_from_cursor` returns the raw integer cursor value. `build_queryset` then emits `"datetime" <= %s` with an integer parameter, which is a timestamptz vs integer mismatch. It also does not match the millisecond cursor format of `DateTimePaginator`, so cursors from the old path do not work on the new one.
   - **Evidence:** `python3 -c "import math,datetime; math.floor(datetime.datetime.now(datetime.timezone.utc))"` gives `TypeError: must be real number, not datetime.datetime`.
   - **Failing test:** add to tests/sentry/api/endpoints/test_organization_auditlogs.py: create one AuditLogEntry as an owner, then call `self.get_success_response(self.organization.slug, qs_params={"optimized_pagination": "true"})`. It returns 500. The fix is to subclass `DateTimePaginator` or reuse its key and cursor conversion.

2. **Critical** at src/sentry/api/endpoints/organization_auditlogs.py:71.
   - **Claim:** `enable_advanced = request.user.is_superuser or organization_context.member.has_global_access` runs on every request, whether or not `optimized_pagination` is set.
   - `RpcUserOrganizationContext.member` is documented as `None` when the user has no membership (src/sentry/organizations/services/organization/model.py:344-346). Two kinds of caller pass `OrganizationAuditPermission` (org:write scope) without a membership:
     - legacy org ApiKeys, where `request.user` is anonymous and `user_id` is None;
     - internal-integration tokens, where the proxy user is created with `is_sentry_app=True` and has no OrganizationMember row (src/sentry/sentry_apps/logic.py:351-353).
   - For both, the line raises `AttributeError: 'NoneType' object has no attribute 'has_global_access'` and the request returns 500. This breaks the existing default endpoint for those callers, not just the new feature.
   - Active superusers get through only because `or` short-circuits on them.
   - **Evidence:** reasoned from the code above. **Test:** call the endpoint with an internal-integration token that has org:write; it should return 200 and returns 500. The check needs a `member is not None` guard and belongs inside the `use_optimized` branch.

3. **Important** at src/sentry/api/paginator.py:877-882 (and the advertised "negative offset" feature).
   - **Claim:** The "advanced" branch passes a negative `cursor.offset` straight into `queryset[start_offset:stop]`. Django 5.2.1 (requirements-frozen.txt:36) raises `ValueError("Negative indexing is not supported.")` for a negative slice start. `paginate()` does not convert ValueError, so any cursor like `0:-5:0` sent with `optimized_pagination=true` returns 500.
   - The feature cannot work as described. Its comment says it "enables access to data beyond normal pagination bounds", which says what the intent was. If the ORM did allow it, this would be a deliberate route out of the pagination bounds.
   - Django blocks the slice today, so there is no data leak. This is a client-triggerable 500 error.
   - **Evidence:** reasoned from Django `QuerySet.__getitem__` semantics. **Test:** as an org owner, `GET ...audit-logs/?optimized_pagination=true&cursor=0:-10:0` returns 500.

4. **Important** at src/sentry/api/paginator.py:182 (shared `BasePaginator.get_result`) and :884.
   - **Claim:** `start_offset = max(0, offset) if not cursor.is_prev else offset` changes the base paginator that every `Paginator`, `DateTimePaginator` and similar subclass uses.
   - A negative offset on a next cursor is now silently clamped to 0 instead of failing. A negative offset on a prev cursor still reaches the slice and still returns 500.
   - The change is uneven and has no tests. The comment's justification, "safe because the underlying queryset will handle boundary conditions", is false for Django querysets.
   - The duplicate-trim check at line 891, `len(results) == offset + limit + extra`, still uses the raw `offset` rather than `start_offset`. Once the two differ, the over-fetch trim no longer fires as intended.
   - The right fix is to reject negative offsets at the cursor boundary in `Cursor.from_string` / `get_cursor_from_request`, which already turns ValueError into a 400. Clamping only one direction in shared code is the wrong place.
   - **Evidence:** reasoned. No failing command for the clamp itself. The prev-cursor 500 error is the same as in finding 3.

5. **Minor (security hygiene)** at src/sentry/api/endpoints/organization_auditlogs.py:71.
   - The gate uses the raw `request.user.is_superuser` flag instead of `is_active_superuser(request)`. The permission class in the same flow uses the latter (src/sentry/api/bases/organization.py:124). The raw flag bypasses superuser-session (su mode) semantics.
   - Today the gate only switches paginators, and the queryset is still scoped to `organization_id`, so the impact is limited. If the "beyond normal bounds" behaviour ever worked, this would be a privilege-gate bypass.

6. **Minor** at src/sentry/utils/cursors.py:26-27.
   - The new comment says negative offsets are allowed, but `Cursor` does no such thing: no code changed and no validation exists either way. The comment is misleading. There is no behaviour impact.

## Not checked
I did not run the test suite, by instruction. Findings 2 to 4 are reasoned from the code and the pinned Django version, not executed.

## Biggest risk
Finding 2 is the urgent one: it returns 500 for API-key and integration callers on the default path of an existing endpoint, with no opt-in flag needed.
