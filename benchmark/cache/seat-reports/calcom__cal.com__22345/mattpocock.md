Review of `change.patch` (base c9a47dd0ce, head da09bc0808), using the mattpocock-skills:code-review two-axis process. I did both axes myself, with no sub-agents.

## Spec
No spec was provided, and none of the commits reference an issue (the log is "fix: use raw query at InsightsBookingService", "convert InsightsBookingService to use Prisma.sql raw queries", "clean up tests", "address feedback"). This axis was skipped. I assumed the intent is to swap the Prisma `WhereInput` objects for `Prisma.sql` fragments without changing which rows each scope can see. Read against that intent, the SQL matches the old semantics in every scope:
- `1=0` replaces `{id:-1}`.
- `= ANY(...)` replaces `in`. The org `teamIds` always includes `orgId`, so it is never empty.
- The team scope now drops the `userId` clause when the user list is empty. That is equivalent to the old `in: []`, which matched nothing.

## Standards
The documented standards I found:
- `CONTRIBUTING.md`: run `yarn lint` (ESLint and Prettier, enforced by tooling, so skipped).
- `docs/developing/open-source-contribution/code-styling.mdx`: ESLint/Prettier, plus an external JS/TS style guide. The link to it is missing in that doc, so it can't be checked.
- `.github/PULL_REQUEST_TEMPLATE.md`, mandatory task: "I confirm automated tests are in place that prove my fix is effective or that my feature works."

The repo has no AGENTS.md, CLAUDE.md, .cursor/rules or CODING_STANDARDS.md.

## Findings
1. `packages/lib/server/service/__tests__/insightsBooking.integration-test.ts:437` (around the old "Caching" describe block, now deleted). **Minor.**
   - **Claim:** The patch deletes the whole "Caching" test suite, but the caching it covered is still there (`insightsBooking.ts:49-50` and `:84-94`, the `cachedAuthConditions` / `cachedFilterConditions` memoisation). That behaviour now has no tests, which runs against the PR template's mandatory "automated tests are in place" item.
   - **Evidence:** The removed hunk is `-  describe("Caching", () => { ... should cache authorization conditions ... should cache filter conditions`, and nothing in the patch replaces it.
   - **Mitigation:** The deleted tests only compared two return values for equality. They would also have passed without any caching, so the coverage actually lost is small.
   - Reasoned, no failing command.

2. `packages/lib/server/service/insightsBooking.ts:29-34` and `:58`. **Minor.** This one is a contract issue, not a documented-standard breach.
   - **Claim:** The constructor parameter changes from the zod-inferred discriminated union `InsightsBookingServiceOptions` to a new, looser `InsightsBookingServicePublicOptions` (`scope: "user"|"org"|"team"; teamId?: number`). The new type duplicates the zod schema by hand, and it drops the compile-time check that `scope: "team"` comes with a `teamId`.
   - **Effect:** A caller passing `{scope:"team", userId, orgId}` now compiles. At runtime `safeParse` fails, `options` becomes `null`, and every query silently returns `1=0`, i.e. an empty result with no error.
   - **Evidence:** The diff hunk `-    options: InsightsBookingServiceOptions;` / `+    options: InsightsBookingServicePublicOptions;`.
   - **Scope:** `git grep insightsBooking` finds no production callers outside `packages/lib/server/service/`, so nothing is affected today.
   - Reasoned; I didn't run tsc because dependencies aren't installed.

3. `packages/lib/server/service/insightsBooking.ts:68`. **Minor, informational.**
   - **Claim:** The public method `findMany(args)` is removed and replaced by `getBaseConditions(): Promise<Prisma.Sql>`. That breaks the class's public API.
   - **Evidence:** The diff hunk `-  async findMany(...)` / `+  async getBaseConditions()`. `git grep` shows no callers outside the service and its test, so nothing breaks in this repo.
   - **Remaining work:** The PR template's "updated the developer docs in /docs" item looks N/A, because no docs mention this service.

No Critical or Important findings. Per the brief, I left out generic smells: the unreachable final branches in `getBaseConditions`, the repeated `reduce` join helper, and the tests asserting exact SQL text.

## Files not reviewed
None. I reviewed both files in the patch:
- `packages/lib/server/service/insightsBooking.ts`
- `packages/lib/server/service/__tests__/insightsBooking.integration-test.ts`

**Summary:** Spec axis skipped (no spec). Standards axis: 3 Minor findings; the most significant is #1, the Caching tests deleted while the caching code stays.

**Not checked:** I did not run tsc, lint or the integration tests (no installs allowed), so the test file's exact `Prisma.sql` equality assertions are unverified at runtime.
