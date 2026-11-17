What this change does: It adds a `retryCount` column to `WorkflowReminder` (schema plus migration). The SMS cron now adds 1 to that count when Twilio returns nothing or the scheduling throws, and on the next run it deletes any reminder whose count is above 1. This stops failing SMS reminders from being retried forever.

I reviewed this for over-engineering only. The design is the right size: one column and one delete clause. The waste is in how the counter gets bumped.

**Should fix**

1. **The counter bump is hand-rolled and copy-pasted** (`packages/features/ee/workflows/api/scheduleSMSReminders.ts:56-60, 178-187, 190-197`). Severity: Minor.
   - **What this is:** The patch adds `retryCount` to the select and widens the cast to `PartialWorkflowReminder & { retryCount: number }`. It reads the value back only to write `reminder.retryCount + 1`. The same 8-line `prisma.workflowReminder.update` block then appears twice, once in the `else` branch and once in `catch`.
   - **Problem:** Prisma already has an atomic `{ increment: 1 }`, and the repo uses it in `packages/features/tasker/repository.ts:110,122` (`attempts: { increment: 1 }`). Read-then-write also loses a bump if two cron runs overlap.
   - **Fix:** Use `data: { retryCount: { increment: 1 } }`. That lets you drop the select spread and go back to `select,` and `as PartialWorkflowReminder[]`. To remove the duplicate block, do the bump in one place: in the `else`, throw an `Error`, so the `catch` handles both failure paths.
   - **If we skip it:** You keep two copies of the same block that must change together, plus a type cast that exists only for this.

**Nice to have**

2. **The new delete clause has no SMS filter** (`scheduleSMSReminders.ts:38-42`). Severity: Minor.
   - **What this is:** The `OR` branch `{ retryCount: { gt: 1 } }` drops the `method: WorkflowMethods.SMS` filter that the other branch has.
   - **Problem:** Today only this SMS job writes `retryCount`, so nothing else is hit. But if the email or WhatsApp crons (`scheduleEmailReminders.ts`, `scheduleWhatsappReminders.ts`) ever start counting retries, this SMS job would quietly delete their rows too.
   - **Fix:** Move `method: WorkflowMethods.SMS` to the top level of the `where`, next to the `OR`. That costs no extra lines.
   - **If we skip it:** A coupling between the jobs that nobody will notice until it bites.

Out of scope, but seen while reading (reasoned, not tested):
- `twilio.scheduleSMS` returns `undefined` when the user or team is SMS-locked (`twilioProvider.ts:92-95`). With this patch, those reminders now count as failures and are deleted after two cron runs. If the lock is lifted later, they do not come back.
- The new `prisma.workflowReminder.update` inside `catch` is not guarded. If it throws, for example because the reminder was deleted between `findMany` and the update, the loop stops and the rest of the reminders in that run are skipped. Before this patch, the `catch` only logged.

Verdict: Ship. Finding 1 is cleanup, not a blocker.
Lean: -10 lines possible.

Files reviewed: all 3 files in the patch (`scheduleSMSReminders.ts`, `migration.sql`, `schema.prisma`). None skipped. The migration and schema change are the minimal form and have no findings. No spec was given, so I assumed the goal is to stop retrying failed SMS reminders after a few attempts.

Not checked: I ran no commands or tests. There is no test for the new retry and delete logic, but that is outside the over-engineering scope.
