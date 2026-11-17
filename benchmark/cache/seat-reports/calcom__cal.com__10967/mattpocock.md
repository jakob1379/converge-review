Review of calcom__cal.com__10967 (base a308075bc → head de62829564). I used the mattpocock-skills:code-review criteria and did both axes myself, without sub-agents.

There is no written spec. I treated the target behaviour as issue #7754, inferred from the branch name and commit messages: for a COLLECTIVE team event, every host's destination calendar gets the event. That covers create, reschedule and cancel. The repo's standards sources are CONTRIBUTING.md (lint must pass, production build must pass), .github/PULL_REQUEST_TEMPLATE.md and packages/config/eslint-preset.js. The repo has no AGENTS.md, CLAUDE.md or .cursorrules. Lint rules are enforced by tooling, so I skipped them. I ran nothing: no build, no tests, no lint.

## Spec axis

1. **packages/core/EventManager.ts:119 — Critical**
   - **Claim:** Google Meet bookings crash when no destination calendar is set.
   - **Evidence:** the line is `mainHostDestinationCalendar.integration` with no optional chaining. `evt.destinationCalendar` is `null` (handleNewBooking.ts:1063-1067) or `[]` (every other caller) when no calendar is set. Destructuring that gives `undefined`, and `.integration` throws a TypeError. The base code used `evt.destinationCalendar?.integration`. So any booking with Google Meet as the location and no destination calendar fails inside `EventManager.create`. Before this change it fell back to Cal Video. The same path runs for every caller that passes `[]`, such as confirm and payment webhooks, when the location is Meet.
   - **Repro (mirrors the logic):** `node -e 'const evt={destinationCalendar:null,location:"integrations:google:meet"}; const [m]=evt.destinationCalendar ?? []; console.log(m.integration)'` throws `TypeError: Cannot read properties of undefined`.
   - A real test: call `new EventManager({credentials:[],...}).create(evt)` with `location: MeetLocationType` and `destinationCalendar: null`.

2. **packages/features/bookings/lib/handleNewBooking.ts:1063-1067, 1077-1079 — Important**
   - **Claim:** the fix does nothing when the organizer has no destination calendar.
   - **Evidence:** `evt.destinationCalendar` is set to `null` when neither the event type nor the organizer has one. `evt.destinationCalendar?.push(...teamDestinationCalendars)` then does nothing, so the other hosts' calendars are silently dropped. `createAllCalendarEvents` then takes the legacy branch (EventManager.ts:384+), which only uses the organizer's credentials. That is the original #7754 symptom. Reasoned, not run.

3. **packages/core/EventManager.ts:170 — Important**
   - **Claim:** video conferencing references (Zoom, Daily, etc.) lose their `credentialId`.
   - **Evidence:** the line changed from `isCalendarType ? evt.destinationCalendar?.credentialId : result.credentialId` to `isCalendarType ? result.credentialId : undefined`, so non-calendar results now store `undefined`.
   - **Consequence:** handleCancelBooking.ts:491 only deletes the meeting when `bookingVideoReference.credentialId` is set. New bookings will therefore leave Zoom or other video meetings behind after cancellation. This is out of scope and a regression. Reasoned.

4. **packages/app-store/googlecalendar/lib/CalendarService.ts:256 and :317 — Important**
   - **Claim:** the fallback for updating and deleting events is dead code.
   - **Evidence:** both lines read `externalCalendarId ? externalCalendarId : event.destinationCalendar?.find((cal) => cal.externalId === externalCalendarId)?.externalId`. The else branch only runs when `externalCalendarId` is falsy, so it searches for a calendar whose `externalId` is falsy and returns `undefined`. The base code fell back to `event.destinationCalendar.externalId`.
   - **Consequence:** older bookings whose reference has no `externalCalendarId` now call `events.update` with `calendarId: undefined`, which fails. They also delete from `"primary"` instead of the selected calendar. Reasoned.

5. **packages/app-store/googlecalendar/lib/CalendarService.ts:147-154 — Important**
   - **Claim:** destination calendars without a `credentialId` are ignored.
   - **Evidence:** the target calendar is now chosen only by `cal.credentialId === credentialId`. `DestinationCalendar.credentialId` is nullable (`Int?`, schema.prisma:159). The no-`credentialId` branch in EventManager.ts:376-381 also calls `createEvent(c, event)` without an externalId.
   - **Consequence:** in that case the event goes to `"primary"` instead of the selected calendar. The base code used `destinationCalendar.externalId`. Reasoned.

6. **packages/features/bookings/lib/handleCancelBooking.ts:423-466 — Important**
   - **Claim:** cancelling a recurring collective booking misses most host calendars and repeats work.
   - **Evidence:** the recurring branch now runs once per calendar reference. Each time it loops over the organizer's credentials (`bookingToDelete.user.credentials`, line 449) and only the first `_calendar` reference of each occurrence (`.find`, line 454).
   - **Consequence:** with N references the same events get N delete calls, and the other hosts' copies are never deleted. Cancelling a non-recurring booking does handle all references. Reasoned.

7. **packages/core/EventManager.ts:554 — Minor**
   - **Claim:** when a reschedule merges two bookings, only one old calendar event is deleted.
   - **Evidence:** the line still uses `.find` for the old calendar event, so the other hosts' old copies stay.

8. **packages/app-store/googlecalendar/lib/CalendarService.ts:122 and :228 — Minor**
   - **Claim:** every host's copy names the main host as organizer.
   - **Evidence:** the organizer email is always taken from `destinationCalendar[0]`, even when the event is inserted into another host's calendar. Reasoned.

9. **packages/types/Calendar.d.ts:171 plus apps/web/playwright/webhook.e2e.ts:249 — Important**
   - **Claim:** the public webhook payload changes shape, and nothing documents it.
   - **Evidence:** `destinationCalendar` in the payload changes from an object to an array. It is also inconsistent: BOOKING_CREATED still sends `null` (e2e line 119, from handleNewBooking's `: null`), while BOOKING_REJECTED sends `[]`. External webhook consumers will break silently. Neither a changeset nor the PR body flags it as a breaking change, which the PR template asks for.

10. **packages/features/bookings/lib/handleNewBooking.ts:991-994 — Minor (spec gap)**
    - **Claim:** dynamic group bookings are not covered.
    - **Evidence:** the patch removes the TODO "For team events & dynamic collective events…". Only `eventType.schedulingType === "COLLECTIVE"` is handled, so dynamic group bookings (no `eventTypeId`) still write only to the organizer's calendar.

11. **packages/trpc/server/routers/viewer/organizations/create.handler.ts:151, 153 — Critical (scope creep that changes behaviour)**
    - **Claim:** organization slug logic is inverted.
    - **Evidence:** `...(!IS_TEAM_BILLING_ENABLED && { slug })` became `...(IS_TEAM_BILLING_ENABLED ? { slug } : {})`. The base sets the slug when billing is **disabled**. The head sets it when billing is **enabled**, which also writes `requestedSlug`.
    - **Consequence:** self-hosted or non-billing deployments now create organizations with no slug, and billing deployments get a slug before payment. This has nothing to do with #7754. It came in with commit db92960dc4 "fix change from main spread operator".
    - **Check:** `git diff a308075bc HEAD -- packages/trpc/server/routers/viewer/organizations/create.handler.ts`.

12. **packages/features/bookings/lib/handleNewBooking.ts:724-762 — Important (scope creep)**
    - **Claim:** `loadUsers` was rewritten beyond what the fix needs, with new failure modes.
    - **Evidence:**
      - It drops `organization: { select: { slug: true } }` from the dynamic-user query.
      - It throws when `dynamicUserList` is empty.
      - It wraps every error. A missing user list becomes a generic 500 "Unable to load users" because a plain `Error` is not an `HttpError`, and Prisma errors become 400s.
    - None of this is needed for the collective fix. Reasoned.

13. **packages/core/CalendarManager.ts:230 — Minor (scope creep)**
    - **Claim:** text that users see was changed.
    - **Evidence:** "organiser" became "organizer", which appears in calendar event notes.

14. **packages/features/bookings/lib/handleNewBooking.ts:688-689, 370/383, 998-999 — Minor (scope creep)**
    - **Claim:** unrelated changes are bundled into the PR.
    - **Evidence:** the `isTeamEventType` expression was rewritten, `orginal` was renamed to `original`, and `firstName: ""` / `lastName: ""` were added to team members.
    - The `firstName`/`lastName` change alters the shape of team member data passed to emails and webhooks.

15. **Whole patch — Minor**
    - **Claim:** the fix has no test.
    - **Evidence:** no test covers it (create, reschedule, cancel for collective events with several destination calendars). The only test edit changes an expected value in the e2e test. The PR template checklist asks for tests that prove the fix.

## Standards axis

16. **Whole patch, against CONTRIBUTING.md "Please be sure that you can make a full production build" — Minor (unverified)**
    - **Claim:** the build is unverified.
    - **Evidence:** I did not run a build. `Calendar.createEvent(event, credentialId: number)` now requires a second argument, but the only caller I found (CalendarManager.ts:236) passes it, and implementations with one parameter still satisfy the type. I found no hard type break.

17. **packages/core/EventManager.ts:341-366 and 512-539 — Minor (judgement call: possible Duplicated Code)**
    - **Claim:** the same block appears twice.
    - **Evidence:** both places fall back to `prisma.credential.findUnique({ include: { app: { select: { slug } } } })` and map the result to `CredentialWithAppName`, line for line.
    - handleCancelBooking.ts:432-441 does a third version with no `app` include and no `appName`.

18. **packages/app-store/googlecalendar/lib/CalendarService.ts:145-146 and packages/core/EventManager.ts:117 — Minor (judgement call)**
    - **Claim:** new comments add noise and are badly worded.
    - **Evidence:** "// Find in calEventRaw.destinationCalendar the one with the same credentialId" is followed by a stray blank line. "@NOTE: destinationCalendar it's an array now" is ungrammatical, and the code under it contradicts it by not handling the empty case (see finding 1).

19. **packages/features/bookings/lib/handleNewBooking.ts:991-994 — Minor (judgement call)**
    - **Claim:** a side effect is hidden inside a mapping callback.
    - **Evidence:** `teamDestinationCalendars` is filled from inside an async `.map` callback. It works only because the push runs before the first `await`. The order of host calendars is therefore implicit.

## Files not reviewed

None. I read the diff for all 22 files.

- **Diff-only review:** packages/core/builders/CalendarEvent/builder.ts (only an import-type split), packages/app-store/larkcalendar/lib/CalendarService.ts, packages/app-store/office365calendar/lib/CalendarService.ts and packages/lib/CalendarService.ts. These only switch to reading `destinationCalendar[0]`, which fits the main-host semantics. I did not trace their other callers.
- **Payment and booking handlers:** packages/features/ee/payments/api/webhook.ts, paypal-webhook.ts, apps/web/pages/api/cron/bookingReminder.ts, and the trpc confirm/editLocation/requestReschedule/deleteCredential handlers. I checked only that they wrap a single calendar in an array. They never include the other hosts' calendars, so confirming a collective booking that needed confirmation, or one that went through payment, will still only write to the organizer's calendar. I count that under finding 2, unverified.

## Summary

- **Spec:** 15 findings. The worst are the Meet-location crash (EventManager.ts:119) and the inverted organization slug logic (create.handler.ts:151-153).
- **Standards:** 4 findings. The worst is the duplicated credential-from-DB fallback in EventManager.ts.

Not checked: nothing was executed, so every finding is reasoned from source except the one-line node repro for finding 1. Risk: findings 1, 3 and 11 are regressions outside the collective-event fix, so they affect every user, not just team events.
