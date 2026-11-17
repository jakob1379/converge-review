Ponytail review: calcom__cal.com__7232 (pinned.patch, d1440bb5d2..6048e2a86b). This seat looks for over-engineering, plus breaches of the repo's documented standards.

**What this change does:** When a booking is cancelled or rescheduled, its email workflow reminders are no longer cancelled at SendGrid right away. The patch marks them with a new nullable `cancelled` column instead. The cron job then cancels them at SendGrid once they are less than an hour from their send time, and deletes the rows. Deleting a workflow or a step still cancels at once through a new `immediateDelete` flag, and so does a reschedule in `handleNewBooking`. SMS reminders are still cancelled at Twilio right away.

Load assumed: a multi-tenant SaaS, with the reminder cron running every few minutes over all users' reminders.

## Findings

**1. Important: type-only imports changed to value imports, and one unused import added. This breaks a lint rule the repo sets to "error".**
- **Files:** `packages/features/bookings/lib/handleNewBooking.ts:1-10`, `packages/trpc/server/routers/viewer/workflows.tsx:1-10`, `packages/features/ee/workflows/api/scheduleEmailReminders.ts:10`
- **Claim:** The patch rewrites `import type { App, Credential, EventTypeCustomInput, Prisma }` and `import type { Prisma, PrismaPromise }` as plain value imports, but these names are only used as types. `scheduleEmailReminders.ts` adds a new value import of `Prisma` and `WorkflowReminder` that is also type-only. In `workflows.tsx`, `Prisma` is no longer used at all, because its only use (`Prisma.BatchPayload`) was deleted.
- **Evidence:**
  - `packages/config/eslint-preset.js:35` sets `@typescript-eslint/consistent-type-imports` to "error" with `prefer: "type-imports"`.
  - `eslint-preset.js:22` sets `unused-imports/no-unused-imports` to "error".
  - `grep -n "Prisma\b" packages/trpc/server/routers/viewer/workflows.tsx` finds only the import line (line 9).
  - In `handleNewBooking.ts`, `Prisma` is only used as `Prisma.UserGetPayload`, `Prisma.JsonValue` and `Prisma.PromiseReturnType`. `App`, `Credential` and `EventTypeCustomInput` are only used in type positions.
- **Failing command (I did not run it, because I was told not to run project checks):** `yarn eslint packages/trpc/server/routers/viewer/workflows.tsx packages/features/bookings/lib/handleNewBooking.ts packages/features/ee/workflows/api/scheduleEmailReminders.ts`. Expected result: consistent-type-imports errors in all three files, and no-unused-imports on `Prisma` in `workflows.tsx`.
- **Fix:** Put back `import type { ... }` and add `WorkflowMethods` to the existing value import. In `workflows.tsx`, use `import type { PrismaPromise }` and drop `Prisma`. In the cron file, drop the import entirely (see finding 2).

**2. Minor (lean): the cron builds a typed array of lazy Prisma promises where one inline `await` would do.**
- **Location:** `packages/features/ee/workflows/api/scheduleEmailReminders.ts:54-75`
- **Claim:** `workflowRemindersToDelete: Prisma.Prisma__WorkflowReminderClient<WorkflowReminder, never>[]`, the push and the trailing `Promise.all` save no time, because the loop already awaits one SendGrid request per reminder in sequence. This is also the only reason the `Prisma`/`WorkflowReminder` import from finding 1 exists.
- **Side effect (reasoned):** Prisma queries are lazy and only run when awaited. If the SendGrid call for reminder k throws, the deletes already queued for reminders 0..k-1 never run. Those rows stay `cancelled: true` and get re-cancelled on the next cron run.
- **Fix:** Replace the queue with `await prisma.workflowReminder.delete({ where: { id: reminder.id } })` inside the loop. That removes about 6 lines and one import.

**3. Minor (merge): the SendGrid cancel request is copied in two places.**
- **Locations:** `packages/features/ee/workflows/lib/reminders/emailReminderManager.ts:214-221` and `packages/features/ee/workflows/api/scheduleEmailReminders.ts:57-64`
- **Claim:** The same `client.request({ url: "/v3/user/scheduled_sends", method: "POST", body: { batch_id, status: "cancel" } })` appears in both files. This patch already had to change it once: it dropped the follow-up `DELETE`, which had been undoing the cancel. The copies will drift.
- **Fix:** In the cron, call `deleteScheduledEmailReminder(reminder.id, reminder.referenceId, true)` (or one small exported cancel helper), then delete the row.

**4. Minor (yagni / split): the boolean `immediateDelete` makes one function do two different jobs, and the name is wrong.**
- **Location:** `packages/features/ee/workflows/lib/reminders/emailReminderManager.ts:197-235`
- **Claim:** With `immediateDelete=true` the function cancels at SendGrid and deletes nothing. With it false or absent it only updates the DB. The SMS twin (`smsReminderManager.ts:177-189`) takes no such flag and always cancels and deletes.
- **Evidence:**
  - At `handleNewBooking.ts:968` the old booking's reminder rows are left with `scheduled: true` and `cancelled` null. They are only removed by the cron's past-date `deleteMany` once their date has passed.
  - `bookings.tsx:490` handles the same concept ("reminders of the previous booking") in deferred mode. The last commit, "remove immediate delete for request reschedule", shows these two call sites were meant to agree.
- **Fix:** Pick one behaviour per reason, or name it plainly (for example `cancelNow`) and have it delete the row too. Then the reschedule paths can share the same call.

**5. Minor (merge): the same EMAIL/SMS dispatch block is copied 7 times, and the patch had to edit every copy.**
- **Locations:** `packages/features/bookings/lib/handleCancelBooking.ts:487`, `packages/features/bookings/lib/handleNewBooking.ts:967`, `packages/trpc/server/routers/viewer/bookings.tsx:489`, `packages/trpc/server/routers/viewer/workflows.tsx:213`, `:377`, `:520`, `:575`
- **Claim:** Each copy is `if (method === EMAIL) deleteScheduledEmailReminder(id, refId[, true]) else if (SMS) deleteScheduledSMSReminder(id, refId)`. This change touched all 7, which shows they must change together. The two copies with the `true` flag are already a step toward the drift described in finding 4.
- **Fix:** Add one `deleteScheduledReminder(reminder, cancelNow?)` next to `scheduleWorkflowReminders` in `reminderScheduler.ts`. That removes about 25 lines net.

**6. Minor (delete): a try/catch that can never catch anything.**
- **Location:** `packages/features/bookings/lib/handleNewBooking.ts:964-975`
- **Claim:** The `try`/`catch` wraps a `forEach` that calls async functions without awaiting them. Both callees already catch their own errors and log them (`emailReminderManager.ts:233`, `smsReminderManager.ts:187`). Nothing can throw synchronously into this `catch`, so `log.error` is unreachable.
- **Fix:** Delete the try/catch (-3 lines). If errors matter here, `await Promise.all(...)` instead.

**7. Minor (delete): whitespace-only churn inside a commented-out block.**
- **Location:** `packages/trpc/server/routers/viewer/workflows.tsx:901-963`
- **Claim:** About 60 lines of a `/* ... */` block were de-indented. There is no behaviour change, it does not relate to the branch's purpose, and it adds noise to the diff and to git blame. The same file also drops the `//  BookingInfo,` comment (line 26), which is harmless.
- **Fix:** Revert the hunk.

**Verdict:** Fix 1 first, because it is a lint error under the repo's own config. Findings 2-7 are cleanups.

**Lean:** about -95 lines possible (roughly 60 from 7, 25 from 5, 6 from 2, 3 from 6).

**Reviewed with no finding:**
- `packages/features/ee/workflows/lib/reminders/smsReminderManager.ts`
- `packages/prisma/schema.prisma`
- `packages/prisma/migrations/20230217230604_add_cancelled_to_workflow_reminder/migration.sql`
- `packages/features/ee/workflows/components/WorkflowStepContainer.tsx`: it only removes an empty grey wrapper that showed when just the sender ID was needed. It is unrelated to the branch's purpose but shrinks the code. The sender-ID block at line 464 sits outside this wrapper in both versions, so nothing is lost.

## Unreviewed files

None. All 10 files in the patch were reviewed.

Not checked: I did not run ESLint, tsc or tests (as instructed), so finding 1 is reasoned from `packages/config/eslint-preset.js`. I did not look at deeper correctness questions outside this seat, for example SendGrid's limits on cancelling scheduled sends, or how deferred cancellation behaves if the cron is late.
