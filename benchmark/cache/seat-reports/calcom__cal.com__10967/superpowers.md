## Code review: calcom PR (base a308075bc3 to head de62829564), destinationCalendar becomes an array for collective events

I loaded `superpowers:requesting-code-review` and applied its checklist myself (no subagent): plan alignment, correctness, error handling, edge cases, test coverage and scope. I read surrounding source at head. I ran no builds or tests. The one runtime check was a standalone `node -e` snippet that imports nothing from the project.

### Findings

**1. packages/core/EventManager.ts:118-119 — Critical**
- **Claim:** Booking any Google Meet event crashes with a TypeError when the event type and organizer have no destination calendar. Before the patch this fell back to Cal Video.
- **Evidence:**
  - `const [mainHostDestinationCalendar] = evt.destinationCalendar ?? [];` gives `undefined` when the array is null or empty.
  - The next line reads `mainHostDestinationCalendar.integration` with no `?.`.
  - `handleNewBooking.ts:1063-1067` sets `destinationCalendar: null` in exactly this case.
  - TypeScript does not catch it, because destructuring a `DestinationCalendar[]` gives a non-optional element type.
- **Repro (runs without the project):** `node -e 'const evt={destinationCalendar:null,location:"integrations:google:meet"}; const [m]=evt.destinationCalendar??[]; if (evt.location==="integrations:google:meet" && m.integration!=="google_calendar") console.log("fallback")'` throws `TypeError: Cannot read properties of undefined`. The old code was `evt.destinationCalendar?.integration`.

**2. packages/trpc/server/routers/viewer/organizations/create.handler.ts:151 — Critical (unrelated to the PR's purpose)**
- **Claim:** The slug condition is inverted.
  - **Before:** `...(!IS_TEAM_BILLING_ENABLED && { slug })` set the slug when billing is disabled.
  - **After:** `...(IS_TEAM_BILLING_ENABLED ? { slug } : {})` sets it only when billing is enabled.
- **Evidence:** Line 153 (requestedSlug) kept its meaning, so with billing enabled the org now gets both `slug` and `requestedSlug`. That claims the slug before payment/publish.
  - With billing disabled (self-hosted), the org gets neither field.
  - `createTeams.handler.ts:66-67` then throws `NoOrganizationSlugError` (`!metadata?.requestedSlug && !organization?.slug`).
- Reasoned; no test was run.

**3. packages/core/EventManager.ts:170 — Important**
- **Claim:** Video references (Zoom, Daily and so on) lose their `credentialId`.
  - **Before:** `credentialId: isCalendarType ? evt.destinationCalendar?.credentialId : result.credentialId`
  - **After:** `credentialId: isCalendarType ? result.credentialId : undefined`
- **Evidence:** `handleCancelBooking.ts:486-503` deletes the video meeting only when `bookingVideoReference.credentialId` is set. New bookings will no longer delete their Zoom/Daily meetings on cancel.
- Reasoned.

**4. packages/app-store/googlecalendar/lib/CalendarService.ts:254-256 and :315-317 — Important**
- **Claim:** The fallback for an empty `externalCalendarId` is dead code. It runs `find(cal => cal.externalId === externalCalendarId)` only when `externalCalendarId` is falsy, so it always returns `undefined`.
- **Effects:**
  - **Update:** sends `calendarId: undefined` to `events.update`, which errors. Before, it used `destinationCalendar.externalId`.
  - **Delete:** falls back to `"primary"`. A 404 is swallowed (`if (err.code === 404) return resolve()`), so events in a non-primary destination calendar are silently left behind for references without an `externalCalendarId`.
- Reasoned.

**5. packages/features/bookings/lib/handleNewBooking.ts:1063-1067 and :1077-1079 — Important (spec gap)**
- **Claim:** The fix does nothing when neither the event type nor the organizer has a destination calendar.
- **Evidence:** `evt.destinationCalendar` is `null`, so `evt.destinationCalendar?.push(...teamDestinationCalendars)` does nothing. Team members' destination calendars are dropped, and `createAllCalendarEvents` takes the organizer-only else branch.
- Members with no destination calendar of their own also still get no event (line 993 pushes only when `user.destinationCalendar` is set). The "only one team attendee gets the event" bug stays for those configurations.
- Reasoned.

**6. packages/app-store/office365calendar/lib/CalendarService.ts:73-76, packages/lib/CalendarService.ts:156-165, packages/app-store/larkcalendar/lib/CalendarService.ts:128-129 — Important (spec gap)**
- **Claim:** Only Google picks the destination per credential (`find(cal => cal.credentialId === credentialId)`). Office365, CalDAV and Lark always use the first (main host's) destination calendar, even when called with a team member's credential.
- **Effects:**
  - **Office365:** host 2 calls `/me/calendars/<host1 externalId>/events`, which fails, or the external ID is a Google ID.
  - **CalDAV:** `.filter(c => c.externalId === host1.externalId)` matches none of host 2's calendars. `Promise.all([])` then returns a success result with a uid, so a booking reference is stored for an event that was never created.
- Collective events with non-Google hosts are still broken, and CalDAV now fails silently.
- Reasoned.

**7. packages/core/EventManager.ts:337-385 — Important**
- **Claim:** A team member's calendar event is created with the main host as organizer, the other team members as Google attendees, and the same `conferenceData.createRequest.requestId`.
- **Evidence:** The `requestId` is `uuidv5(location)`, a constant (`EventManager.ts:31`).
- **Expected effects** (I don't know Google's exact behaviour here):
  - Each host's Google calendar may get its own Meet link. The booker only receives `results[0]`'s link (`handleNewBooking.ts:2186`).
  - Members who are already attendees on host 1's event may see the event twice: the auto-added invitation plus the explicit insert.
- Reasoned, medium confidence.

**8. packages/features/bookings/lib/handleCancelBooking.ts:422-482 — Important**
- **Claim:** In the recurring-series branch (lines 445-466), every calendar reference repeats the same loop over the organizer's credentials. That gives N times duplicate deletes, all using the organizer's credentials and `find` (first reference only).
- **Effects:**
  - Team members' events for recurring collective bookings are never deleted.
  - Only the evt sent to the calendar apps carries the organizer's destination calendar (lines 251-255).
- Reasoned.

**9. Whole patch — Important (testing standard)**
- **Claim:** The core behaviour change has no test: multiple destination calendars fanned out per credential, the reference credential/externalId mapping, and multi-reference update/cancel.
- **Evidence:** The only test change is `webhook.e2e.ts:249` (`null` → `[]`). `packages/core/CalendarManager.test.ts` and the booking tests are untouched.
- Findings 1, 3 and 4 would each have been caught by an integration test of create, cancel or reschedule.

**10. packages/core/EventManager.ts:375-382 and :543-548 — Minor**
- **Create (375-382):** a destination with no `credentialId` fans out to every credential of that integration type, once per destination. Several such destinations create duplicate events. These results also carry no `externalId`, so references lose the `externalCalendarId` they used to get from `evt.destinationCalendar.externalId`.
- **Update (543-548):** the same per-reference fan-out duplicates updates.

**11. packages/core/EventManager.ts:340-366 and :511-541, handleCancelBooking.ts:433-440 — Minor**
- **Claim:** The credential-from-DB fallback is copy-pasted three times, and the copies differ: the cancel copy has no `app` include.
- **Evidence:** In `updateAllCalendarEvents`, `credential` can still be `undefined` and is passed straight to `updateEvent`.

**12. packages/features/bookings/lib/handleNewBooking.ts:724-763 — Minor (scope creep, behaviour change)**
- **Claim:** The `loadUsers` rewrite is unrelated to the PR and changes behaviour.
- **Evidence:**
  - Errors that are neither `HttpError` nor Prisma errors (including its own `throw new Error("dynamicUserList ...")`) become a generic 500, "Unable to load users".
  - Prisma errors become 400.
  - The dynamic-user select drops `organization: { select: { slug } }`, though `IsFixedAwareUser` (line 355) still declares it.

**13. packages/core/CalendarManager.ts:230 — Minor**
- **Claim:** A user-visible string changed ("organiser" → "organizer"), unrelated to the PR. Anything matching the old text will see the change.

**14. handleNewBooking.ts:990-1006, 1074 — Minor**
- **Claims:**
  - Team-member objects now get hardcoded `firstName: ""` and `lastName: ""`.
  - `schedulingType` is added to `CalendarEvent`, which leaks into webhook payloads.
  - The webhook payload's `destinationCalendar` now includes every collective member's destination calendar row (`credentialId`, `externalId`, `userId`).

### Files in the patch I did not review in depth
- `packages/core/builders/CalendarEvent/builder.ts`: import-only change (`import type`), nothing to review.
- `packages/core/builders/CalendarEvent/class.ts`, `packages/types/Calendar.d.ts`, `packages/types/EventManager.d.ts`: read as type changes only. I did not check every `Calendar` implementer against the new `createEvent(event, credentialId)` signature. Fewer parameters is still type-compatible.
- `apps/web/pages/api/cron/bookingReminder.ts`, `packages/features/ee/payments/api/webhook.ts`, `packages/features/ee/payments/api/paypal-webhook.ts`, `packages/trpc/.../deleteCredential.handler.ts`, `confirm.handler.ts`, `editLocation.handler.ts`, `requestReschedule.handler.ts`, `packages/emails/src/templates/BrokenIntegrationEmail.tsx`: mechanical wrap-in-array changes. I checked the diff only and found no defects.

I did not run the project's typecheck or tests (forbidden). Every severity except finding 1 is reasoned from source.
