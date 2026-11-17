I ran the review through `open-code-review:delegate-review` against base 30a92a4d66, in range mode. OCR listed 17 reviewable files and I reviewed all 17. The skill's auto-fix step was skipped because you asked for a report only, and nothing was written to the repo or the scratch directory. There are no Critical findings. Two are Important: one is reproduced on GNU sed, the other is reasoned from Prisma's behaviour.

## Findings

1. **packages/app-store/googlecalendar/lib/CalendarService.ts:1024 — Important (reasoned)**
   - **Claim:** `SelectedCalendarRepository.updateManyByCredentialId(this.credential.id, {})` does nothing. It does not update `SelectedCalendar.updatedAt`, even though the comment says it does.
   - **Evidence:** The repo pins prisma 5.4.2 (yarn.lock:38872). In that version the query engine only adds `@updatedAt` fields when the write args are non-empty, and `updateMany` with empty data returns 0 without running a write. So every Google webhook (the call comes via `webhook.ts:46` → `fetchAvailabilityAndSetCache`) pays for a pointless repository call.
   - **Also:** nothing in the patch reads `SelectedCalendar.updatedAt`. The UI uses `CalendarCache.updatedAt`. The line and the new `SelectedCalendarRepository.updateManyByCredentialId` (selectedCalendar.ts:400) are dead either way and should be removed.
   - **Check (needs a DB):** call `prisma.selectedCalendar.updateMany({ where: { credentialId: X }, data: {} })` and confirm `updatedAt` is unchanged.

2. **scripts/test-gcal-webhooks.sh:68 — Important (reproduced)**
   - **Claim:** `sed -i '' -E ...` only works with BSD/macOS sed. On GNU sed the env update fails, yet the script still prints "✅ Updated GOOGLE_WEBHOOK_URL".
   - **Evidence:**
     ```
     printf 'GOOGLE_WEBHOOK_URL=old\n' > t.env
     sed -i '' -E "s|^GOOGLE_WEBHOOK_URL=.*|GOOGLE_WEBHOOK_URL=new|" t.env
     ```
     On GNU sed 4.10 this gives `sed: can't read s|^GOOGLE_WEBHOOK_URL=.*|...: No such file or directory`, exit 2, and the file still says `old`.
   - **Also in this script:**
     - `ENV_FILE="../.env"` (line 5) depends on the directory you run it from.
     - `cleanup` exits 0 on the failure paths (lines 17, 49, 58).
     - When an existing tmole process is reused, it reads `/tmp/tmole.log`, which may be stale or missing.

3. **packages/features/apps/components/CredentialActionsDropdown.tsx:69 — Minor**
   - **Claim:** `hasCache` ignores `disableConnectionModification`. The event-type Advanced tab (EventAdvancedTab.tsx:372) passes `disableConnectionModification={true}` and previously showed no credential actions. It now shows a destructive "Delete cached data" item.
   - **Stale UI:** that caller passes no `onChanged`. The deleteCache `onSuccess` (line 45) only calls `onSuccess?.()` and never invalidates `viewer.calendars.connectedCalendars`, so the old "Last updated" timestamp stays after a delete. The disconnect mutation in the same file does invalidate in `onSettled`.

4. **packages/features/apps/components/CredentialActionsDropdown.tsx:89 — Minor**
   - **Claim:** the date is formatted with a hardcoded `"en-US"` locale, so the user's locale from `useLocale` is ignored. The dates around it are localised.

5. **packages/features/apps/components/CredentialActionsDropdown.tsx:86-87 — Minor**
   - **Claim:** it uses raw `text-gray-900` / `text-gray-500` / `dark:text-white` instead of the semantic tokens the rest of the UI uses (`text-emphasis`, `text-subtle`).
   - **Also:** the status row is a clickable `DropdownMenuItem` that does nothing.

6. **packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:17 — Minor (breaks a documented standard)**
   - **Claim:** `prisma.credential.findFirst` has no `select`, so it loads the full credential row, including `key`.
   - **Evidence:** `.cursor/rules/review.mdc` says "Only select data you need" and calls out the credential key. The key is not returned to the client, but `select: { id: true }` is enough.

7. **packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:25 — Minor**
   - **Claim:** a plain `throw new Error(...)` reaches the client as INTERNAL_SERVER_ERROR. Sibling handlers (`setDestinationCalendar.handler.ts:7`) use `TRPCError` with a specific code; this should be NOT_FOUND or FORBIDDEN.
   - **Also:**
     - The input schema is inlined in `_router.tsx` instead of a `deleteCache.schema.ts`, which is how this router's other handlers are laid out.
     - The delete repeats an inline `prisma.calendarCache.deleteMany`; the cache repository layer exists but isn't used.
     - No test covers this ownership check.

8. **packages/trpc/server/routers/viewer/calendars/connectedCalendars.handler.ts:28 — Minor**
   - **Claim:** the handler builds `new CalendarCacheRepository()` directly and skips the `calendar-cache` feature-flag gate (calendar-cache.ts:24-27). Cache status and the delete action therefore appear even when the feature is off.
   - **Also:** this makes the new `CalendarCacheRepositoryMock.getCacheStatusByCredentialIds` unreachable dead code.

9. **packages/lib/server/repository/user.ts:899-900 and packages/lib/getConnectedDestinationCalendars.ts:21-28 — Minor (breaks a documented standard)**
   - **Claim:** `updatedAt` and `googleChannelId` are added to the selectedCalendars select and to the `UserWithCalendars` type, but nothing reads them. That breaks "Only select data you need".

10. **packages/platform/atoms/selected-calendars/wrappers/SelectedCalendarsSettingsWebWrapper.tsx:120-132 — Minor**
    - **Claim:** this changes behaviour without saying so. The error/Alert branch used to show "Remove app" for broken credentials whatever `disableConnectionModification` was set to. It now hides it when that flag is true.
    - **Also:** `|| null` at line 98 is a no-op change.

11. **packages/prisma/migrations/20250715160635_add_calendar_cache_updated_at/migration.sql:1-6 — Minor**
    - **Claim:** the auto-generated warning ("required column ... without a default value. This is not possible if the table is not empty") is stale, because the SQL does add `DEFAULT NOW()`.
    - **Also:** existing cache rows get the migration time as `updatedAt`, so "Last updated" is wrong for them until their next refresh.

12. **apps/web/package.json:11 — Minor**
    - **Claim:** `dev:cron` changes from `ts-node` (declared at apps/web/package.json:196) to `npx tsx`. `tsx` is not declared anywhere and is not in yarn.lock, so `npx` downloads it from the registry at run time. This is also unrelated to the feature.

13. **packages/features/apps/components/CredentialActionsDropdown.tsx:6 — Minor**
    - **Claim:** this is the first import of `@calcom/platform-constants` in this package (the only other `@calcom/platform-*` imports are `@calcom/platform-libraries` in two other files). It is not declared in packages/features/package.json, so it only resolves through workspace hoisting.

No issues found in `apps/web/public/static/locales/en/common.json` (keys spelled correctly, placed above the sentinel), `calendar-cache.repository.interface.ts`, `calendar-cache.repository.ts` (the `groupBy` is covered by the `@@id([credentialId, key])` index), `schema.prisma`, or the `selectedCalendar.ts` `findMany` refactor (no behaviour change).

## Files not reviewed

None: 17 of 17 reviewed (100%). Not done: no typecheck, build or tests run, as instructed, and Finding 1 was not confirmed against a live database.
