What this change does: It rewrites `InsightsBookingService` so its permission and filter checks are built as raw SQL pieces (`Prisma.Sql`) instead of Prisma `where` objects. It replaces `findMany` with `getBaseConditions()`, which returns one SQL condition for callers to use in `$queryRaw`. It also adds a looser constructor options type and updates the integration tests to match. I reviewed it for over-engineering only, as asked.

Context: nothing in the repo calls `InsightsBookingService` except its own integration test (I grepped `packages/` and `apps/`). Every API shape this patch adds is used only by that test.

## Should fix

1. **`getBaseConditions` has two branches that can never run** (`packages/lib/server/service/insightsBooking.ts:72-80`), Minor
   - **What this is:** It combines the permission condition and the filter condition into one SQL condition.
   - **Problem:** `getAuthorizationConditions()` always returns a `Prisma.Sql` object (line 83 return type; every path in `buildAuthorizationConditions`, lines 125-143, returns either `NOTHING_CONDITION` or a built Sql). That object is never null and always truthy. So `else if (filterConditions)` at line 76 and `else return NOTHING_CONDITION` at line 78 are dead code.
   - **Fix:** `return filterConditions ? Prisma.sql\`(${authConditions}) AND (${filterConditions})\` : authConditions;`
   - **If we skip it:** Readers assume permission can be missing, so the query might run on the filter alone. They will reason about a fail-open path that does not exist. About -7 lines.
   - Evidence: this is reasoned from the types and return paths, not from a failing test. It is a lean issue, not a behavior bug.

2. **The same "join with AND/OR" fold is written out three times** (`packages/lib/server/service/insightsBooking.ts:119-122`, `:171-174`, `:204-207`), Minor
   - **What this is:** Each spot glues a list of SQL pieces together with `AND` or `OR` using a hand-written `reduce`.
   - **Problem:** Each list has at most two items, and the shape is fixed. That means one condition that is always there plus one optional condition. A general fold is more machinery than the job needs. The repo already uses `Prisma.join` (for example `packages/features/insights/server/routing-events.ts:830`). In Prisma 5 (`packages/prisma/package.json`: `^5.4.2`) it also takes a separator.
   - **Fix:** In org/team, write the optional second clause directly: `userIds.length ? Prisma.sql\`(${a}) OR (${b})\` : a`. In the filter builder, do the same, or use `Prisma.join(conditions.map((c) => Prisma.sql\`(${c})\`), " AND ")`. The exact-equality tests in `insightsBooking.integration-test.ts` compare the nested paren structure, so they would need updating as well.
   - **If we skip it:** You keep three copies of the same fold that have to change together. About -9 lines.

3. **`InsightsBookingServicePublicOptions` is a hand-written copy of the zod schema, and it is looser** (`packages/lib/server/service/insightsBooking.ts:29-34`, used at `:58`), Minor
   - **What this is:** A second options type for the constructor. It flattens the discriminated union, which is the zod schema's "pick the shape by `scope`" type, so that `teamId` becomes optional for every scope.
   - **Problem:** Line 36 already derives the right type from the schema at lines 10-27. The new type has to be kept in sync with the schema by hand. It also removes a compile-time check. `{ scope: "team", userId, orgId }` without `teamId` now compiles, then fails `safeParse` at line 62 and silently matches nothing (`1=0`). No caller exists that needs the looser type.
   - **Fix:** Delete lines 29-34 and type the constructor with `InsightsBookingServiceOptions`, as the base version did. If a future tRPC caller passes unvalidated input, it can parse with the exported schema first.
   - **If we skip it:** You keep a duplicate type that will drift from the schema, and a mistake that used to fail at compile time now shows up as empty insights at runtime. -7 lines.
   - Evidence: reasoned. I did not run `tsc`, per the instructions.

Verdict: Ship (all findings are advisory and Minor; none changes behavior).
Lean: -23 lines possible.
Not checked: correctness, security, SQL behavior (for example `= ANY(...)` on an empty array), and the deleted caching tests. They are outside the over-engineering scope. I ran no tests and no type-check.

## Files not reviewed
None. Both files in the patch were reviewed:
- `packages/lib/server/service/insightsBooking.ts` (fully)
- `packages/lib/server/service/__tests__/insightsBooking.integration-test.ts` (diff hunks only, read to confirm that the test is the only consumer and asserts exact Sql structure; not reviewed for test quality)
