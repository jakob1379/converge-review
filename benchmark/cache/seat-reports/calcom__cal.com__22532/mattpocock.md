I reviewed this directly as the `mattpocock-skills:code-review` skill describes, with one deviation: the skill says to spawn a Standards sub-agent and a Spec sub-agent, and you said not to spawn agents, so I did both passes myself. There is no spec, so the Spec axis is limited to scope notes measured against what the PR appears to be for. I read every file in the patch.

The standards I found in the repo are `.cursor/rules/review.mdc` (the only rule file with real coding rules), `CONTRIBUTING.md` (process only: build, lint, PR hygiene) and `packages/app-store/CONTRIBUTING.md` (app metadata, docs links, env vars via zod.ts). The repo has no AGENTS.md, CLAUDE.md or CODING_STANDARDS.md. The `.claude/` folder in the checkout is not tracked by git; it is harness config, not repo standards.

## Standards

1. **`packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:17-22` — Important.**
   - **Claim:** `prisma.credential.findFirst({ where: { id, userId } })` has no `select`, so it loads the whole Credential row, including `key` (the OAuth tokens), only to check that the row exists.
   - **Evidence:** `review.mdc` says "Only select data you need … Unnecessary data exposure … (In our case app credentials …)". The key is not returned to the client, so the separate "credential.key must never be returned" rule is not broken. The "select only what you need" rule is, on the exact table it names.
   - **Check that fails on the patched code:** `grep -c "select" packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts` prints 0.

2. **`packages/lib/server/repository/user.ts:899-900` — Minor.**
   - **Claim:** `updatedAt` and `googleChannelId` are added to the `selectedCalendars` select inside `findUnlockedUserForSession`, which runs for every authenticated session. Nothing in the patch reads them. The only other change is widening the `UserWithCalendars` Pick types in `packages/lib/getConnectedDestinationCalendars.ts:21-28` to match. Cache status actually comes from `CalendarCache` through `getCacheStatusByCredentialIds`.
   - **Evidence:** this breaks the `review.mdc` rule "Only select data you need". `grep -rn "googleChannelId" packages/trpc/server/routers/viewer/calendars packages/platform/atoms/selected-calendars packages/features/apps/components/CredentialActionsDropdown.tsx` finds nothing.

3. **`packages/features/apps/components/CredentialActionsDropdown.tsx:89` — Minor, judgement call.**
   - **Claim:** the "Last updated" timestamp uses a hard-coded `new Intl.DateTimeFormat("en-US", …)`, so it ignores the user's locale even though the label around it goes through `t()`.
   - **Evidence:** `review.mdc` says "Always use t() for text localization in frontend code". This is the spirit of that rule rather than its letter.

4. **`packages/features/apps/components/CredentialActionsDropdown.tsx:20-36` and `packages/platform/atoms/selected-calendars/wrappers/SelectedCalendarsSettingsWebWrapper.tsx:70-79,123-132` — Minor, judgement call.**
   - **Claim:** the new component takes six props. Four of them (`integrationType`, `cacheUpdatedAt`, `delegationCredentialId`, `disableConnectionModification`) are passed in only so it can work out `canDisconnect` and `hasCache`. The same six-prop block is copied into two call sites.
   - **Evidence:** `review.mdc` says "Prefer Composition over Prop Drilling". The copied block is also a possible case of Duplicated Code.

5. **`packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:17,28` vs `packages/trpc/server/routers/viewer/calendars/connectedCalendars.handler.ts:28` — Minor, judgement call (possible Duplicated Code / inconsistent layering).**
   - **Claim:** reading the cache status goes through `CalendarCacheRepository`, but deleting the cache calls `prisma.calendarCache.deleteMany` directly from the tRPC handler. Commit c615a404c7 says "use repository pattern", which this handler does not do.
   - **Evidence:** no documented rule requires repositories, so this is a heuristic, not a breach.

6. **`packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:25` — Minor, judgement call.**
   - **Claim:** a failed ownership check throws a plain `Error`, so the client gets a 500 instead of a NOT_FOUND or FORBIDDEN error.
   - **Evidence:** the sibling `setDestinationCalendar.handler.ts:7` uses `TRPCError`. That is a local convention; no document requires it.

I checked these `review.mdc` rules and found nothing:
- **Early returns:** followed.
- **O(n²) logic:** none. The cache-status merge uses a `Map`, so it is O(n).
- **Circular imports:** none new. `trpc` → `@calcom/features` and `app-store` → `lib/server/repository` are both existing import directions.
- **Day.js:** not used.
- **API v1/v2 breaking changes:** none. The only API change is a new tRPC field added to the response.

## Spec

There is no spec, so I can't check this patch against stated requirements. Below are changes that don't fit the apparent goal (cache status and delete cache for Google Calendar credentials), to read as possible scope creep.

7. **`scripts/test-gcal-webhooks.sh` (whole file) — Minor, scope.**
   - **Claim:** this is an unrelated developer script for setting up Tunnelmole. It also hard-codes `ENV_FILE="../.env"`, which depends on the directory you run it from.
   - **Evidence (correctness, outside the strict remit):** line 68 runs `sed -i '' -E …`. That form only works on BSD/macOS sed; on GNU sed (Linux) it fails.

8. **`apps/web/package.json:11` — Minor, scope.** `dev:cron` changes from `ts-node` to `npx tsx`. This is unrelated tooling.

9. **`packages/lib/server/repository/selectedCalendar.ts:259-260` — Minor, scope.** It drops the `satisfies Prisma.SelectedCalendarFindManyArgs` check from `findMany`. This is unrelated and weakens type checking.

10. **`packages/platform/atoms/selected-calendars/wrappers/SelectedCalendarsSettingsWebWrapper.tsx:123-132` — Minor, reasoned.** In the second branch (the card for an errored or unlisted calendar), "Remove App" used to be hidden only for delegation credentials. It is now also hidden when `disableConnectionModification` is set. The commits don't mention this behaviour change.

11. **`packages/app-store/googlecalendar/lib/CalendarService.ts:1024` — Minor, reasoned.**
    - **Claim:** every time the cache refreshes, `updateManyByCredentialId(this.credential.id, {})` runs to bump `SelectedCalendar.updatedAt`, but nothing in the UI reads that value. The dropdown reads `CalendarCache.updatedAt` instead.
    - **Unverified:** I did not confirm whether Prisma's `updateMany` with empty `data` actually bumps an `@updatedAt` column.

## Files not reviewed

None. All 17 files in the patch were reviewed. I did not run lint, build or tests, as instructed.

**Summary:** 6 findings on the Standards axis (worst: #1, the credential query in the deleteCache handler has no `select`). On the Spec axis there was no spec, so 5 scope notes only (worst: #7, the unrelated webhook script that breaks on GNU sed).
