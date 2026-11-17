Remit: over-engineering only (code that is not needed, extra abstraction, duplication, lines that can be deleted). I read the whole patch (all 22 files, 1126 lines) and the head-version code around each hunk. I did not run builds or tests. Load assumed: a multi-tenant SaaS booking path, where many bookings run at once.

What this change does: `CalendarEvent.destinationCalendar` changes from one calendar to an array of calendars. For COLLECTIVE team events, each host's destination calendar is added to the array, and `EventManager` creates, updates and deletes an event per calendar. Every place that builds a `CalendarEvent` now wraps its single calendar in an array.

## Findings

**1. The "fetch credential from DB" block is copied three times** — `packages/core/EventManager.ts:342-365` and `:515-538`, plus `packages/features/bookings/lib/handleCancelBooking.ts:431-441`. Severity: Important.
- Claim: The two EventManager copies are the same 22 lines: `prisma.credential.findUnique` including `app.slug`, then a hand-built `CredentialWithAppName`. The handleCancelBooking copy is a third variant without the `app` include, so the three already differ. Any change to the credential shape now has to be made in three places.
- Evidence: Diff lines 324-351 and 427-453 are the same text. Diff lines 628-638 are the variant.
- Fix: One private helper, e.g. `getCredentialById(id)` next to `calendarCredentials` in EventManager, called from both loops. The cancel path can reuse it. About -40 lines.
- Reasoned. No failing test: this is duplication, not a wrong result.

**2. Dead `.find()` fallback in Google `updateEvent` and `deleteEvent`** — `packages/app-store/googlecalendar/lib/CalendarService.ts:254-256` and `:315-317`. Severity: Important. It is dead code and it also hides a regression.
- Claim: `externalCalendarId ? externalCalendarId : event.destinationCalendar?.find((cal) => cal.externalId === externalCalendarId)?.externalId`. The else branch only runs when `externalCalendarId` is falsy. It then looks for a calendar whose `externalId` equals that falsy value, so it returns `undefined` in practice. The whole expression is just `externalCalendarId`.
- What it hides: the old fallback to the destination calendar's `externalId` is gone. Old bookings whose reference has no `externalCalendarId` now update with `calendarId: undefined` and delete from `"primary"`.
- Fix: Either delete the branch and write `externalCalendarId`, or restore a real fallback: `externalCalendarId || mainHostDestinationCalendar?.externalId`. The variable already exists in `updateEvent` (line 198).
- Reasoned from the code.

**3. Two parameters carry the same fact (which destination calendar to use)** — `packages/core/CalendarManager.ts:221,236,267`; `packages/types/Calendar.d.ts:221`; `packages/app-store/googlecalendar/lib/CalendarService.ts:87,145-150`; `packages/types/EventManager.d.ts:26`. Severity: Minor.
- Claim: `EventManager` already knows `destination.externalId` and passes it to `CalendarManager.createEvent` as `externalId`. That function only echoes it back in the result. It also passes `credential.id` to `calendar.createEvent`, and Google then searches the array again by `credentialId` to find the same `externalId`.
- The `Calendar` interface change (`createEvent(event, credentialId)`) has exactly one consumer: Google. No other calendar service reads the new argument.
- Fix: Pass the target `externalId` once (or set it on the event) and drop the credential-based search. This also removes the comment and blank line at 145-146.

**4. `schedulingType` added to `CalendarEvent` is never read** — `packages/types/Calendar.d.ts:182`, `packages/features/bookings/lib/handleNewBooking.ts:1074`. Severity: Minor.
- Evidence: `grep -rnE "(evt|event|calEvent|calEventRaw)\??\.schedulingType" packages apps` finds only `Booker/components/EventMeta.tsx:67`, which is the booker event, not a `CalendarEvent`.
- Fix: Delete the field, the assignment and the `SchedulingType` import. -3 lines.

**5. Team calendars are collected through a side effect inside `map`, with a redundant guard** — `packages/features/bookings/lib/handleNewBooking.ts:987-994` and `:1077-1079`. Severity: Minor.
- Claim: `teamDestinationCalendars` is pushed from inside the async `teamMemberPromises.map`, then spread into `evt.destinationCalendar?.push(...)` behind a second COLLECTIVE check. `isTeamEventType && schedulingType === "COLLECTIVE"` is redundant both times, because COLLECTIVE already implies a team event.
- Fix: Build it in place: `[eventType.destinationCalendar ?? organizerUser.destinationCalendar, ...(eventType.schedulingType === "COLLECTIVE" ? users.slice(1).map((u) => u.destinationCalendar) : [])].filter(Boolean)`.
- Side benefit: the current `?.push` silently drops every team calendar when the organizer has no destination calendar, because `evt.destinationCalendar` is then `null` (lines 1063-1067). The one-expression form removes that case.

**6. `loadUsers` rewrite is unrelated to this PR and adds dead checks** — `packages/features/bookings/lib/handleNewBooking.ts:724-763`. Severity: Minor.
- `Array.isArray(hosts)` after `const hosts = eventType.hosts || []` can never be false.
- The new try/catch rewraps every error as a 400 or 500 `HttpError`.
- The `dynamicUserList` empty check is new behavior nobody asked for.
- The rewrite also quietly drops the `organization: { select: { slug: true } }` select, while `IsFixedAwareUser` (line 355) still declares `organization: { slug: string }`.
- Fix: Revert to the original ternary. About -25 lines.

**7. The same "booking calendar, else user calendar, wrapped in an array" logic is written two ways across 10 sites.** Severity: Minor.
- 5-line nested ternary form: `handleCancelBooking.ts:251-255` and `:528-532`, `paypal-webhook.ts:152-156`, `deleteCredential.handler.ts:290-294`, `confirm.handler.ts:175-179`, `editLocation.handler.ts:85-89`, `handleNewBooking.ts:1063-1067`.
- 2-line form: `const selected = a || b; selected ? [selected] : []` in `bookingReminder.ts:107,130` and `webhook.ts:101,119,207,229`.
- Fix: Use one form everywhere, e.g. `[a ?? b].filter(Boolean)` or the 2-line form. About -20 lines.
- `requestReschedule.handler.ts:240-242` keeps the old `x || x` self-duplication, now written as a ternary.

**8. Recurring-cancel branch runs once per reference** — `packages/features/bookings/lib/handleCancelBooking.ts:443-469`. Severity: Minor.
- Claim: The "delete all recurring occurrences across all user calendar credentials" block now sits inside `for (const reference of bookingCalendarReference)`. It does not depend on `reference`. With N calendar references it repeats the same full sweep N times. The repeats hit already-deleted events, and the try/catch logs those errors.
- Fix: Move the block out of the loop and run it once.

**9. Small no-ops and churn.** Severity: Minor.
- `EventManager.ts:209`: `result.credentialId ?? undefined` is a no-op `?? undefined`.
- Google `CalendarService.ts:100-103`: `x && x.length > 0 ? x : []` does the same job as the `?? []` used in every other file of this patch.
- `handleNewBooking.ts:998-999`: `firstName: ""` and `lastName: ""` added to team members, but the `TeamMember` type (`Calendar.d.ts:41`) has neither field.
- `handleNewBooking.ts:688-689`: the typed `SchedulingType.X` comparison is replaced with string literals plus `!!`, with no gain.
- Unrelated churn that widens the diff: `builder.ts:1-2` import split, `orginal`→`original` rename, `CalendarManager.ts:230` changes the user-visible note text "organiser"→"organizer", the indentation-only rewrap at `CalendarManager.ts:234-253`, and `organizations/create.handler.ts:151,153`.

## Outside my remit, passed on for the correctness seat (reasoned, not verified)

- `packages/core/EventManager.ts:119`: `mainHostDestinationCalendar.integration` has no `?.`. A Google Meet booking whose `destinationCalendar` is `[]` or `null` throws a TypeError. Several callers now pass `[]`.
- `packages/trpc/server/routers/viewer/organizations/create.handler.ts:151`: `...(!IS_TEAM_BILLING_ENABLED && { slug })` became `...(IS_TEAM_BILLING_ENABLED ? { slug } : {})`. The condition is inverted, so the slug is now set only when billing is enabled.
- `packages/core/EventManager.ts` catch block (head ~595): `console.error(message)` was removed, so update failures are now swallowed without a log.

Verdict: fix 1 and 2 first. 2 is a dead branch that hides a lost fallback.
Lean: about -100 lines possible (1: -40, 6: -25, 7: -20, plus 2, 3, 4, 5, 9).

Unreviewed files: none. All 22 files in the patch were reviewed. For `apps/web/playwright/webhook.e2e.ts` and `packages/core/builders/CalendarEvent/builder.ts` there is no lean finding beyond the churn noted in 9.

Not checked: I ran no typecheck or test, so nothing above was confirmed by a failing command. I did not confirm whether removing the `organization` select (finding 6) breaks a downstream reader.
