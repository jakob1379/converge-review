I did the review myself and did not dispatch a reviewer, as the override required. I read the whole patch (15 files, +555 lines) against `b004587262`. The patch has no spec, so I took its intent from the diff: logged-in users can add guest emails to an existing booking from the bookings list, and the server saves the new attendees, updates the calendar event and sends emails. Dependencies are not installed and the brief said not to run checks, so every claim below comes from reading the code and none was executed.

## Findings

1. **`packages/trpc/server/routers/viewer/bookings/addGuests.handler.ts:46-48`, Important.** Team admins are refused. The check for "team admin or owner" uses `&&`. `isTeamAdmin` matches ADMIN or OWNER, and `isTeamOwner` matches OWNER only, so together only owners pass. An ADMIN who is neither the organizer nor an attendee gets `FORBIDDEN`. This conflicts with the codebase's own rule in `get.handler.ts:405-406` (`role === OWNER || role === ADMIN`), which is the flag the UI relies on (`booking.isUserTeamAdminOrOwner`). Repro: a team booking organized by user A; user B has role ADMIN on that team and is not an attendee; B calls `viewer.bookings.addGuests` and gets `FORBIDDEN: you_do_not_have_permission`. Fix: use `isTeamAdmin(...)` alone, or join the two with `||`.

2. **`addGuests.handler.ts:70-78`, Important (abuse control bypass).** The `BLACKLISTED_GUEST_EMAILS` filter can be bypassed. The blacklist entries are lowercased but the incoming `guest` is not, and there is no `extractBaseEmail`. `handleNewBooking.ts:741-743` does `extractBaseEmail(guest).toLowerCase()` before comparing. Repro: set `BLACKLISTED_GUEST_EMAILS=spam@x.com` and submit `guests: ["Spam@x.com"]` or `["spam+1@x.com"]`. The address is saved as an attendee and receives the scheduled email plus a calendar update. The attendee de-duplication on line 75 has the same case problem: `Foo@x.com` is added even though `foo@x.com` is already an attendee.

3. **`packages/emails/email-manager.ts:525-550` (`sendAddGuestsEmails`), Important (breaks a documented convention).** The function ignores the event type's settings that turn off host and attendee emails. Every sibling sender (`sendLocationChangeEmails` at 503/515, `sendScheduledSeatsEmails` at 248/260) checks `eventTypeDisableHostEmail` / `eventTypeDisableAttendeeEmail`. The new function does not take `eventTypeMetadata`, and the handler (line 168) does not pass `booking.eventType?.metadata`. Event types that disabled these emails (for example platform customers) will still email the organizer, team members and every attendee.

4. **`addGuests.schema.ts:5` together with `addGuests.handler.ts:52-54`, Important (spam / abuse).** The guest list has no size cap and the server does not de-duplicate it. Any authenticated user whose email matches an attendee can add guests. Each request:
   - sends mail on the organizer's behalf (`from: <organizer name>`) to every new guest;
   - re-sends to every existing attendee;
   - pushes the attendee list to the organizer's calendar provider.

   The client's uniqueness check (`AddGuestsDialog.tsx:26-29`) is not enforced on the server. Sending `guests: ["a@x.com","a@x.com"]` straight to tRPC creates two attendee rows through `createMany`. Fix: add `.max(N)` and a uniqueness refine to `ZAddGuestsInputSchema`.

5. **`addGuests.handler.ts:22-56`, Important (reasoned).** Booking state and seated events are never checked.
   - Guests can be added to cancelled, rejected or past bookings. The UI exposes past confirmed bookings through `BookingListItem.tsx:554`, and a direct API call reaches any status. Emails and calendar updates then go out for a dead booking.
   - On seated events (`seatsPerTimeSlot`), Attendee rows are created without `BookingSeat` rows, which skips the seat limit. Any one seat-holder (`isAttendee`) can add guests to a booking shared with strangers. The full attendee list is then pushed to the organizer's calendar event, which can expose seat-holders to each other through the provider's invite even when `seatsShowAttendees` is false.

6. **`addGuests.handler.ts:156-163`, Minor.** The handler builds `EventManager` from `ctx.user`'s credentials, which may not be the organizer's. When an attendee or team owner triggers the update, calendar references that lack a `credentialId` are matched against the caller's calendars (`EventManager.ts:872-878`), so the organizer's event is not updated. `editLocation` avoids this because `bookingsProcedure` limits it to organizers and collective hosts.

7. **`addGuests.handler.ts:91-104` and `:163`, Minor.** There is no transaction or compensation. Attendees are written before the calendar update, and `updateCalendarAttendees` is not wrapped in try. If it throws, the DB already has the guests and no emails go out. A retry then fails with `emails_must_be_unique_valid`, because the guests now count as existing attendees.

8. **`addGuests.handler.ts:168`, Minor.** The handler passes the raw `guests` to `sendAddGuestsEmails` instead of `uniqueGuests`. An input email that was already an attendee gets a duplicate "scheduled" email instead of the "guests added" one.

9. **`packages/emails/templates/attendee-add-guests-email.ts` (inherits the constructor at `attendee-scheduled-email.ts:19-26`), Minor.** `showAttendees` is never passed, so seated events with `seatsShowAttendees=true` still hide the attendee list in these emails.

10. **`apps/web/components/dialog/AddGuestsDialog.tsx:42-45`, Minor.** In `onError`, the message is a template string and is never empty, so the `unable_to_add_guests` fallback can never show. Users see raw strings such as `BAD_REQUEST: ...`.

11. **`AddGuestsDialog.tsx:48-58` and `:61`, Minor.**
    - If the user removes every email field, `handleAdd` returns without any feedback.
    - `isInvalidEmail` is never cleared after a successful add.
    - Closing through `onOpenChange` (overlay or Esc) keeps the old emails and the error state.
    - The client uniqueness check is case-sensitive.

12. **`addGuests.handler.ts:83-88`, Minor.** Guests are saved with `name: ""`, so the emails and calendar entries show blank names. They also inherit the organizer's time zone and locale, which is defensible but not stated anywhere.

13. **Whole patch, Important (tests).** The patch adds a new authenticated mutation that writes to the DB, calls external calendars and sends email, with zero tests: no handler integration test (permission matrix, blacklist, de-duplication) and no E2E test for the dialog. `data-testid="add_members"` is added but nothing uses it.

## Unreviewed files

- None. All 15 files in the patch were reviewed.
- Looked at only briefly: `apps/web/public/static/locales/en/common.json` (keys only; all new keys are used and nothing is missing), `packages/ui/index.tsx` and `packages/ui/form/MultiEmailLazy.tsx` (export wiring that follows the existing `PhoneInputLazy` pattern), and the `packages/emails/src/templates/*AddGuestsEmail.tsx` wrappers and `index.ts` (thin wrappers that follow the LocationChange pattern).

Not checked: whether `updateAllCalendarEvents` swallows provider errors (only partly read), and how Google Calendar actually notifies invitees on update in the seated case.
