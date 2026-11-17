What the change does: it adds an `updatedAt` column to `CalendarCache`, sends the latest cache timestamp for each credential through `connectedCalendars`, and adds a `deleteCache` tRPC mutation. A new `CredentialActionsDropdown` replaces `DisconnectIntegration` in the selected-calendars settings, and Google Calendar connections get "cache status" and "delete cache" items in it. The patch also carries several unrelated edits (a dev script, a package.json script change, a repository refactor).

I reviewed for over-engineering only. I assumed normal multi-tenant cal.com production load.

Findings:

1. packages/app-store/googlecalendar/lib/CalendarService.ts:1023-1024 and packages/lib/server/repository/selectedCalendar.ts:400-405. Severity: Important.
   - Claim: The new `updateManyByCredentialId(this.credential.id, {})` write is dead work, and so is its new repository method. It adds an extra UPDATE on every `fetchAvailabilityAndSetCache` run (the cron and webhook path) for every Google credential.
   - Evidence: Nothing in the patch or the repo reads `SelectedCalendar.updatedAt` for this feature. The UI gets its timestamp from `CalendarCache.updatedAt` through `getCacheStatusByCredentialIds`. A grep for `updateManyByCredentialId` finds only the definition and this one caller. The empty `data: {}` also depends on Prisma's `@updatedAt` behaviour when no field is set, which the patch never checks.
   - Fix: delete both. That is about 10 lines less and one less DB write per credential per sync.
   - Evidence type: reasoned (grep-verified that nothing consumes it).

2. packages/lib/server/repository/user.ts:899-900 and packages/lib/getConnectedDestinationCalendars.ts:20-28. Severity: Minor.
   - Claim: `updatedAt` and `googleChannelId` are added to the user's selected-calendar select and to the `UserWithCalendars` type, but nothing consumes them.
   - Evidence: A grep for `googleChannelId` or `.updatedAt` in getConnectedDestinationCalendars.ts, the calendars tRPC router and the selected-calendars atoms finds only the type lines. The two new columns are fetched on every connected-calendars load for nothing.
   - Fix: revert both hunks (about 10 lines).

3. packages/features/calendar-cache/calendar-cache.repository.interface.ts:30-32 and packages/features/calendar-cache/calendar-cache.repository.mock.ts:26-30. Severity: Minor.
   - Claim: The new method is added to the interface and to the mock, but the only caller bypasses both.
   - Evidence: packages/trpc/server/routers/viewer/calendars/connectedCalendars.handler.ts:28 does `new CalendarCacheRepository()` directly. It does not use the `CalendarCache.initFromCredential` factory (calendar-cache.ts:27-28), which is what picks the mock. So the mock method can never run on this path. The concrete class may have methods the interface does not declare, so the interface edit is not needed either.
   - Fix: either use the factory or drop the interface and mock edits (about 8 lines).

4. packages/features/apps/components/CredentialActionsDropdown.tsx:53-65 and 143-154. Severity: Minor.
   - Claim: The disconnect mutation, toasts, invalidation and confirm dialog are copied from packages/features/apps/components/DisconnectIntegration.tsx, so two copies now have to change together.
   - Evidence: The two `trpc.viewer.credentials.delete.useMutation` blocks are near-identical: same toast keys, same `onSettled` invalidations. The copy drops DisconnectIntegration's `isDelegationCredential({ credentialId })` guard and its `teamId` passthrough. `DisconnectIntegration` is still used elsewhere, so the logic now lives in two places.
   - Fix: keep `DisconnectIntegration` for removal, and add the cache items next to it, or have the dropdown reuse it.

5. packages/lib/server/repository/selectedCalendar.ts:259-260. Severity: Minor.
   - Claim: Unrelated refactor in a feature patch. It also removes the `satisfies Prisma.SelectedCalendarFindManyArgs` type check.
   - Evidence: the diff hunk at patch lines 288-291. No feature code needs it.
   - Fix: revert.

6. apps/web/package.json:11 (`dev:cron` changed from ts-node to `npx tsx`). Severity: Minor.
   - Claim: Unrelated tooling change, and `npx tsx` may download a package that is not declared.
   - Evidence: nothing in the feature uses it.
   - Fix: revert or move to its own PR.

7. scripts/test-gcal-webhooks.sh (new file, 79 lines). Severity: Important.
   - Claim: An unrelated dev script is bundled into the feature, and on Linux it fails to update an existing `GOOGLE_WEBHOOK_URL`.
   - Evidence: line 68 runs `sed -i '' -E "s|...|..."`, which is BSD/macOS-only syntax. On GNU sed it fails. Reproduced in my temp dir:
     `printf 'GOOGLE_WEBHOOK_URL=old\n' > e.env && sed -i '' -E "s|^GOOGLE_WEBHOOK_URL=.*|GOOGLE_WEBHOOK_URL=new|" e.env`
     Output: `sed: can't read s|^GOOGLE_WEBHOOK_URL=.*|...: No such file or directory`, rc=2, file unchanged. The script then still prints "Updated GOOGLE_WEBHOOK_URL".
   - Other problems: `ENV_FILE="../.env"` depends on the current directory, and the script has emoji output.
   - Fix: drop it from this PR (-79 lines).

8. packages/trpc/server/routers/viewer/calendars/_router.tsx:29. Severity: Minor.
   - Claim: The input schema is inlined, which breaks the router's convention.
   - Evidence: the sibling procedures use `connectedCalendars.schema.ts` and `setDestinationCalendar.schema.ts`.
   - Fix: a `deleteCache.schema.ts`, or reuse the pattern.

9. packages/trpc/server/routers/viewer/calendars/deleteCache.handler.ts:24-26. Severity: Minor.
   - Claim: It throws a plain `Error` where the sibling handler uses `TRPCError`.
   - Evidence: setDestinationCalendar.handler.ts:7 imports `TRPCError`. A plain Error turns a not-found or forbidden case into a 500 for the client.
   - Fix: `new TRPCError({ code: "NOT_FOUND" })`.

10. packages/platform/atoms/selected-calendars/wrappers/SelectedCalendarsSettingsWebWrapper.tsx:98 and :162. Severity: Minor.
    - Claim: Unrelated churn: `delegationCredentialId || null` and a lone blank line.
    - Evidence: the diff hunks. Neither is needed by the feature.
    - Fix: revert.

11. packages/prisma/migrations/20250715160635_add_calendar_cache_updated_at/migration.sql:1-6 and packages/prisma/schema.prisma:1718. Severity: Minor.
    - Claim: The migration header says the column is added "without a default value. This is not possible…", but the SQL adds `DEFAULT NOW()`. Stale comments like this, plus the explanatory comments at CalendarService.ts:1023 and schema.prisma:1718, go against the user's documented "DO NOT ADD COMMENTS unless asked" rule.
    - Evidence: the patch text at lines 415-423 and 432.
    - Fix: delete the stale warning block and the comments.

Verdict: fix 1 and 7 first. Then trim 2, 3 and 5 for a leaner diff.
Lean: about 120 lines could go (script 79, dead SelectedCalendar write about 10, dead selects and types about 10, interface and mock about 8, churn about 10), plus removing the copied disconnect logic.

Not checked: whether Prisma bumps `@updatedAt` on `updateMany` with empty `data`. It does not matter if finding 1 is deleted. I did not run builds or tests, per the brief.

Files not reviewed: none. All 17 files in the patch were read. apps/web/public/static/locales/en/common.json only got a check that the keys are used, because it only adds i18n strings.
