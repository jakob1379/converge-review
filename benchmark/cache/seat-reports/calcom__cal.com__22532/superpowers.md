I loaded `superpowers:requesting-code-review`. That skill says to send the review to a subagent, but the brief says not to spawn agents, so I did the review myself. I read every file in the patch and the code around it. Base is 30a92a4d66 and head is 5fd11f9faa. There is no spec, so I judged the change against what it appears to be for: showing the cache status and deleting the cache for Google Calendar credentials.

**Findings**

1. **packages/app-store/googlecalendar/lib/CalendarService.ts:1023 — Important (reasoned, not run).**
   - **Claim:** `SelectedCalendarRepository.updateManyByCredentialId(this.credential.id, {})` almost certainly does not do what its comment says ("Update SelectedCalendar.updatedAt…"). It also adds a database round-trip on a hot path every time it runs.
   - **Evidence:**
     - It sends an empty `data` object.
     - As I understand Prisma (^5.4.2 per `packages/prisma/package.json`), `@updatedAt` is only added when there is at least one other field to write. With `{}`, nothing changes.
     - Even if it did bump the timestamp, nothing reads it. `grep -rn "googleChannelId\|\.updatedAt" packages/lib/getConnectedDestinationCalendars.ts` finds only the type definitions.
     - `fetchAvailabilityAndSetCache` runs from the webhook and cron cache-refresh paths, so this adds one `UPDATE` per run for no consumer.
   - **Suggested test:** an integration test against a real DB that runs this method and then asserts `SelectedCalendar.updatedAt` has moved. I expect it to fail. I could not run it because builds and tests were out of scope.

2. **packages/lib/getConnectedDestinationCalendars.ts:21-28 and packages/lib/server/repository/user.ts:899-900 — Minor.**
   - **Claim:** `updatedAt` and `googleChannelId` are added to the `UserWithCalendars` type and to the `findUnlockedUserForSession` select, but no code reads either field.
   - **Evidence:**
     - The grep above finds no use outside the type.
     - `findUnlockedUserForSession` is the session-user query, so every session lookup now fetches two extra columns for nothing.
     - The fields are also required in the type, so every caller that builds this type must now supply them. The v1 caller (`apps/api/v1/pages/api/connected-calendars/_get.ts`) and the v2 caller (`calendars.service.ts`, which uses `include: true`) both happen to fit.

3. **packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:24-25 — Minor.**
   - **Claim:** When the credential is missing or belongs to someone else, the handler does `throw new Error(...)`. Clients get a 500 INTERNAL_SERVER_ERROR instead of a NOT_FOUND or FORBIDDEN error.
   - **Evidence:** The handler next to it, `setDestinationCalendar.handler.ts:77,97`, throws `TRPCError` with proper codes, so this breaks the local convention.

4. **packages/trpc/server/routers/viewer/calendars/_router.tsx:27-33 — Minor.**
   - **Claim:** The input schema is an inline `z.object(...)`. The other procedures put theirs in `*.schema.ts` files (`ZConnectedCalendarsInputSchema`, `ZSetDestinationCalendarInputSchema`), and they are also listed in the `CalendarsRouterHandlerCache` type. The new procedure does neither.
   - **Evidence:** Lines 1-11 of the same file.

5. **packages/trpc/server/routers/viewer/calendars/connectedCalendars.handler.ts:28 — Minor.**
   - **Claim:** `new CalendarCacheRepository()` skips the global cache flag. That flag is normally checked in `CalendarCache.init` (`packages/features/calendar-cache/calendar-cache.ts:27-28`), which returns the mock when caching is turned off.
   - **Evidence:**
     - The patch adds `getCacheStatusByCredentialIds` to `CalendarCacheRepositoryMock`, but this call path can never reach the mock, so that method is dead code.
     - When caching is turned off, the status query and the "Delete cached data" item still run against the table.

6. **packages/features/calendar-cache/calendar-cache.repository.ts:243-258 — Minor.**
   - **Claim:** `getCacheStatusByCredentialIds` takes the latest `updatedAt` across all rows without filtering out expired ones (`expiresAt`). The UI can therefore show a "Cache Status" for a credential whose cache has fully expired.
   - **Evidence:** The `groupBy` `where` clause contains only `credentialId`.

7. **packages/platform/atoms/selected-calendars/wrappers/SelectedCalendarsSettingsWebWrapper.tsx:123-131 — Minor.**
   - **Claim:** The disconnect control now behaves differently on the error/Alert branch. Before, it was hidden only for delegation credentials. Now it is also hidden when `disableConnectionModification` is set, which happens whenever the scope is disabled (line 168). In that view, a user can no longer remove a broken credential.
   - **Evidence:** The removed lines checked only `!connectedCalendar.delegationCredentialId`, while the new component also gates on `!disableConnectionModification`.

8. **packages/features/apps/components/CredentialActionsDropdown.tsx:139-142 — Minor.**
   - **Claim:** The timestamp is formatted with `new Intl.DateTimeFormat("en-US", ...)`. That ignores the user's locale and their profile timezone, even though the label right next to it is translated with `t()`.
   - **Evidence:** The locale is a hard-coded literal.

9. **packages/features/apps/components/CredentialActionsDropdown.tsx:134-147 — Minor.**
   - **Claim:** The read-only status block sits inside a `DropdownMenuItem`. It can be focused and selected but does nothing.
   - **Evidence:** The block uses raw `text-gray-900` and `text-gray-500` classes instead of the design-system tokens (`text-emphasis` and `text-subtle`) used elsewhere in `@calcom/ui`.

10. **packages/features/apps/components/CredentialActionsDropdown.tsx:56 — Minor.**
    - **Claim:** The file imports `@calcom/platform-constants`, but `packages/features/package.json` does not declare it as a dependency. No other file in `packages/features` imports it.
    - **Evidence:**
      - `grep -n "@calcom" packages/features/package.json` lists only atoms, dayjs, lib, trpc and ui.
      - The new file is the only `@calcom/platform-constants` importer under `packages/features`.

11. **packages/features/apps/components/CredentialActionsDropdown.tsx:103-115 — Minor.**
    - **Claim:** The disconnect mutation logic copies `DisconnectIntegration.tsx` instead of reusing it. The copy drops two things the original has: the `teamId` forwarding and the `isDelegationCredential({credentialId})` guard.
    - **Evidence:** Compare with `packages/features/apps/components/DisconnectIntegration.tsx:26-46`.

12. **packages/prisma/migrations/20250715160635_add_calendar_cache_updated_at/migration.sql:1-6 — Minor.**
    - **Claim:** The header comment says the column is added "without a default value. This is not possible if the table is not empty". The SQL below it adds the column `DEFAULT NOW()`, so the comment is out of date and misleading.
    - **Evidence:** Line 9 of the migration.

13. **scripts/test-gcal-webhooks.sh:56 — Minor.**
    - **Claim:** `sed -i '' -E ...` is the macOS/BSD form. GNU sed on Linux treats `''` as the script and fails, so `.env` is never updated.
    - **Evidence:** I ran `printf 'A=1\n' > $TMPDIR/e; sed -i '' -E "s|^A=.*|A=2|" $TMPDIR/e`. It printed "sed: can't read s|^A=.*|A=2|: No such file or directory", exited with 2, and the file still said A=1.
    - `ENV_FILE="../.env"` also depends on which directory the script is run from.

14. **apps/web/package.json:11 — Minor.**
    - **Claim:** `dev:cron` switches from `ts-node` to `npx tsx`. This has nothing to do with the feature, and `tsx` is not a declared dependency, so `npx` may download it on the fly. `ts-node` is still declared at line 196.
    - **Evidence:** The `grep` for `tsx` in the `package.json` files found no dependency.

15. **(No new tests anywhere) — Minor.** None of the new code is tested: `deleteCacheHandler` (which includes an ownership check), `getCacheStatusByCredentialIds`, the extra field in `connectedCalendars`, and the dropdown UI. The calendars router already has handler tests, for example `setDestinationCalendar.handler.test.ts`.

**Checked and found no problem:** the ownership check in `deleteCacheHandler` (`findFirst` by `id` + `userId` before `deleteMany`); all i18n keys the new component uses exist in `common.json`; `DropdownItem` and `ConfirmationDialogContent` are exported; the migration timestamp is in order (it comes before 20250716135157); the `findMany` simplification in `selectedCalendar.ts:259-261` does not change behaviour.

**Files not reviewed:** none. I reviewed all 17 files in the patch.

I did not install anything or run tsc, lint or tests, as the brief instructed. Finding 1 is reasoned from Prisma's behaviour with an empty update, not confirmed against a database. It is the one finding to verify before acting on it.
