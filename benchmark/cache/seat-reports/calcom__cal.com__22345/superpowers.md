I found no Critical issues. Nothing else in the repo uses `InsightsBookingService` or its old `findMany` outside this test file, so removing `findMany` breaks no callers. The columns the new SQL relies on (`isTeamBooking`, `eventParentId`, `teamId`, `userId`) exist in the `BookingTimeStatusDenormalized` view and its source migrations. The `isOrgOwnerOrAdmin` rewrite behaves the same as before. Dropping the `userId IN []` branch when the team or org has no users is also equivalent: an empty `IN` matched nothing anyway. I could not run anything because the checkout has no `node_modules`, so every finding below is reasoned from the code.

**Findings**

1. `packages/lib/server/service/insightsBooking.ts:171-174, 204-207, 119-122, 72-80` — **Important** — The public methods return SQL fragments without outer parentheses, so callers that add their own conditions get the wrong AND/OR grouping.
   - The org and team authorization conditions come out as `(A) OR (B)` (lines 173 and 206).
   - When only `eventTypeId` is set, the filter condition is `("eventTypeId" = x) OR ("eventParentId" = x)` (line 106).
   - With no filters, `getBaseConditions()` returns the authorization condition bare (line 75).
   - Removing `findMany` means callers must now write their own SQL around these fragments, e.g. `WHERE ${base} AND "createdAt" >= ${start}` or `WHERE "status" = 'accepted' AND ${base}`. Postgres then reads `(A) OR (B) AND x` as `A OR (B AND x)`. Every row matching A ignores the caller's date or status filter, which silently inflates insights counts.
   - All rows returned are still within the authorized set (A and B are both authorized branches), so this is a correctness problem, not an authorization leak.
   - The only end-to-end test (line 481) uses `WHERE ${baseConditions}` with nothing else and user scope, whose condition is an AND, so it cannot catch this.
   - Simple fix: wrap each returned fragment once, e.g. return `Prisma.sql\`(${...})\`` from the `get*Conditions` methods.
   - Evidence: this is reasoned. A test that would fail: org scope with no filters, a team booking (A branch) outside a date range, and the query `WHERE ${base} AND "createdAt" > now()`; that booking comes back when it should not.

2. `packages/lib/server/service/insightsBooking.ts:29-34, 58` — **Minor** — `InsightsBookingServicePublicOptions` replaces the discriminated union in the constructor's type, so a type error turns into an empty result at runtime. `{ scope: "team", userId, orgId }` with no `teamId` now compiles. The zod `safeParse` then fails, `options` becomes `null`, and every query silently returns nothing (`1=0`). Before the patch this was a compile error. Evidence: compare the old signature (`options: InsightsBookingServiceOptions`, the zod-inferred union) with the new one.

3. `packages/lib/server/service/insightsBooking.ts:76-80` — **Minor** — Two branches of `getBaseConditions()` can never run. `getAuthorizationConditions()` always returns a `Prisma.Sql` and never null, so `else if (filterConditions)` and the final `else return NOTHING_CONDITION` are unreachable. Evidence: the return type is `Promise<Prisma.Sql>` and `buildAuthorizationConditions` has no null path.

4. `packages/lib/server/service/__tests__/insightsBooking.integration-test.ts:273, 295-299, 332-343, 384-386, 407, 429-431` — **Minor** — Most tests now check the exact SQL text instead of what the query returns, against your test philosophy ("test contracts, not implementation").
   - Changing whitespace or parentheses in the service breaks these tests even when the query behaves the same.
   - The org and team `= ANY(${array})` paths are never run against the database. Only user scope is, in the `getBaseConditions` test at line 438.
   - So the Prisma 5 array-parameter binding against the int `teamId`/`userId` columns, and the grouping problem in finding 1, are both untested.
   - The org test (lines 332-343) also expects team and user ids in a fixed order, but the repository queries have no `orderBy`. Its `toEqual` on arrays could flake. The old test had the same problem; the patch keeps it.

5. `packages/lib/server/service/__tests__/insightsBooking.integration-test.ts` (former "Caching" describe block, removed in the hunk at old lines 476-545) — **Minor / informational** — The caching tests were deleted while the caching code (`cachedAuthConditions`, `cachedFilterConditions`) stays. That is acceptable under your philosophy, since caching is an internal detail. Noted only so the removal is known to be deliberate.

**Files not reviewed**

None. Both files in the patch were reviewed in full, together with the surrounding source and the view migration:
- `packages/lib/server/service/insightsBooking.ts`
- `packages/lib/server/service/__tests__/insightsBooking.integration-test.ts`

There was no spec, so I could not check plan alignment. I did not check how Prisma 5.4 types the array parameters at runtime.
