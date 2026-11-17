## Code review: fix/cancelled-rescheduled-workflow-emails (d1440bb5d2..6048e2a86b, 10 files)

I followed the `mattpocock-skills:code-review` skill and did both axes myself, with no sub-agents. I read the code and docs only. I did not run lint, tsc or tests.

**Standards sources found:**
- `CONTRIBUTING.md`: "yarn lint … If you get errors, be sure to fix them before committing."
- `.eslintrc.js`, which loads `packages/config/eslint-preset.js`. Its rules include:
  - `@typescript-eslint/consistent-type-imports: error` with `prefer: "type-imports"`
  - `unused-imports/no-unused-imports: error`
  - `plugin:prettier/recommended`
- `.prettierrc.js`, which loads `packages/config/prettier-preset.js` (`trailingComma: "es5"`).
- `.github/PULL_REQUEST_TEMPLATE.md` has nothing that applies to code.
- There is no AGENTS.md or CODING_STANDARDS.md.

As you asked, I left generic code smells out.

## Standards

### 1. `packages/trpc/server/routers/viewer/workflows.tsx:9`: unused import (Important, hard violation)
- **Claim:** `Prisma` is imported but no longer used, which breaks `unused-imports/no-unused-imports` (an `error` in eslint-preset.js).
- **Evidence:** At the base commit, `Prisma` was used only at old line 376 (`PrismaPromise<Prisma.BatchPayload>[]`). The patch deletes that line. Running `grep -n '\bPrisma\b'` on the file at HEAD now matches only the import on line 9.
- **Failing command (not run):** `yarn eslint packages/trpc/server/routers/viewer/workflows.tsx`

### 2. `packages/trpc/server/routers/viewer/workflows.tsx:1-10`: type imports turned into value imports, plus a formatting break (Important, hard violation)
- **Claim:** The patch changes `import type { Prisma, PrismaPromise }` into a value import that it merges with the enums. That breaks `@typescript-eslint/consistent-type-imports` (`prefer: "type-imports"`, error), because `PrismaPromise` is only used as a type (line 342).
- **Evidence:** Line 9, `  Prisma`, has no trailing comma, which breaks prettier's `trailingComma: "es5"`. Through `plugin:prettier/recommended` that is a lint error.
- **Failing command (not run):** the same eslint command as finding 1.

### 3. `packages/features/bookings/lib/handleNewBooking.ts:1-10`: `import type` downgraded to a value import (Important, hard violation)
- **Claim:** At the base commit the file had `import type { App, Credential, EventTypeCustomInput, Prisma } from "@prisma/client"`. The patch folds these into a value import, which breaks `consistent-type-imports`.
- **Evidence:** All four names are used only in type positions:
  - `App["categories"]` at line 79
  - `Credential` at lines 90 and 109
  - `EventTypeCustomInput[]` at lines 349 and 1289
  - `Prisma.UserGetPayload`, `JsonValue`, `PromiseReturnType` and `BookingCreateInput`
- I found no value use of `Prisma.*`.
- **Failing command (not run):** `yarn eslint packages/features/bookings/lib/handleNewBooking.ts`

### 4. `packages/features/ee/workflows/api/scheduleEmailReminders.ts:10`: types imported as values (Important, hard violation)
- **Claim:** The new line `import { Prisma, WorkflowReminder } from "@calcom/prisma/client"` imports two names that are only used as types (line 54). This breaks `consistent-type-imports`.
- **Failing command (not run):** `yarn eslint packages/features/ee/workflows/api/scheduleEmailReminders.ts`

All four of these can be auto-fixed, and `yarn lint` would catch them. They show the branch was committed without the lint step that CONTRIBUTING.md requires.

### 5. `packages/trpc/server/routers/viewer/workflows.tsx:~901-960`: whitespace churn in a commented-out block (Minor, judgement call)
- **Claim:** The patch strips indentation inside a `/* … */` block. It has nothing to do with the fix.
- **Evidence:** The diff hunk at `@@ -923,63 +901,63 @@`.
- No rule is broken, because prettier does not format inside comments. It is diff noise.

## Spec

There is no spec, so I skipped this axis.

The notes below check the code against the branch's stated intent: workflow reminders for cancelled or rescheduled bookings must not be sent. They are not backed by any spec, and every one is reasoned rather than reproduced.

### A. `packages/features/ee/workflows/api/scheduleEmailReminders.ts:53-77`: one failure stalls every later cancel (Important, reasoned)
- **Claim:** The cancel loop is a single try/catch with sequential `await client.request(...)` calls. If one SendGrid POST throws, the loop stops. None of the queued `prisma.workflowReminder.delete` calls run either, because PrismaPromises are lazy and `Promise.all` is never reached.
- **Why it matters:** The next cron run (every 15 minutes, per `.github/workflows/cron-scheduleEmailReminders.yml`) tries the same reminder first and can fail the same way. That happens, for example, if SendGrid refuses a second "cancel" on a batch it has already cancelled. Every cancelled reminder after it in the result set is then never cancelled, and those emails go out.
- **When it clears:** Only once the bad row's `scheduledDate` passes and the earlier `deleteMany` at line ~33 removes it.

### B. `packages/features/ee/workflows/lib/reminders/emailReminderManager.ts:214-223`: "immediate" path cancels without cleanup (Important, reasoned, partly uncertain)
- **Claim:** The `immediateDelete` path puts SendGrid batches straight into "cancel" status. This path is used by:
  - reschedules in `handleNewBooking.ts:968`
  - workflow deletion in `workflows.tsx:214`
  - step deletion in `workflows.tsx:521`
- **The problem:** The deferred design (set a `cancelled` flag, then have the cron cancel within one hour of send time) only makes sense if SendGrid limits how many batches can be cancelled or paused at once.
- If that limit exists, deleting a workflow with many future reminders goes over it. Later cancel POSTs then fail, and the emails are sent.
- I don't know SendGrid's exact current limit, so verify this against their scheduled-sends docs.
- **Secondary point:** this path also leaves the DB row untouched (no delete, no `cancelled` flag).

### C. Fire-and-forget DB writes (Important, reasoned)
- **Where:**
  - `packages/features/bookings/lib/handleCancelBooking.ts:485-493`
  - `packages/trpc/server/routers/viewer/bookings.tsx:488-494`
  - `packages/trpc/server/routers/viewer/workflows.tsx:376-382`
  - `packages/trpc/server/routers/viewer/workflows.tsx:574-580`
- **Claim:** The DB writes that matter, the `cancelled: true` update or the row delete, now happen inside `deleteScheduled*Reminder` calls that nobody awaits. Before the patch, the row deletes were awaited with `Promise.all`.
- **Why it matters:** On serverless hosting the request can finish before the update lands. If it is lost, the cron never cancels the batch and the reminder is sent, which is exactly the bug this branch targets.
- **Also:** the `try/catch` at `handleNewBooking.ts:964-975` cannot catch errors from these un-awaited async calls.

### D. `packages/features/ee/workflows/lib/reminders/emailReminderManager.ts:204-208`: delete now errors when the row is already gone (Minor, reasoned)
- **Claim:** The patch uses `prisma.workflowReminder.delete`, where callers used `deleteMany` before. `delete` throws P2025 when the row no longer exists.
- **When it happens:** On workflow deletion (`workflows.tsx:214`), cascade deletes can remove the row before this async call runs. The error is caught and logged, so the effect is log noise rather than a failure.
- `smsReminderManager.ts:182` has the same issue.

### E. Scope creep (Minor)
- `packages/features/ee/workflows/components/WorkflowStepContainer.tsx:390`: a UI change ("small UI fix") that drops `isSenderIdNeeded` from the wrapper condition, which removes an empty gray box. It is unrelated to reminder cancellation.
- The commented-block whitespace in Standards finding 5 also falls here.

## Summary
- **Standards:** 5 findings. The worst are the lint errors in `workflows.tsx:1-10`: an unused `Prisma` import, plus a type-imports and prettier break.
- **Spec:** no spec, so no findings on this axis. Of the intent-level notes, the worst is A, the cron cancel loop that stalls on one failure.

## Unreviewed files
None. I read all 10 files in the patch:
- `packages/features/bookings/lib/handleCancelBooking.ts`
- `packages/features/bookings/lib/handleNewBooking.ts`
- `packages/features/ee/workflows/api/scheduleEmailReminders.ts`
- `packages/features/ee/workflows/components/WorkflowStepContainer.tsx`
- `packages/features/ee/workflows/lib/reminders/emailReminderManager.ts`
- `packages/features/ee/workflows/lib/reminders/smsReminderManager.ts`
- `packages/prisma/migrations/20230217230604_add_cancelled_to_workflow_reminder/migration.sql`
- `packages/prisma/schema.prisma`
- `packages/trpc/server/routers/viewer/bookings.tsx`
- `packages/trpc/server/routers/viewer/workflows.tsx`

Not checked: I ran no eslint, tsc or tests, so findings 1-4 are inferred from the config plus grep. I did not confirm SendGrid's API limits, so B depends on that.
