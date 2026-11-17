## Correctness review: calcom__cal.com__14740 ("add guests to booking")

I ran `ocr delegate preview --from b004587262 --to HEAD`, which listed the same 15 files as the patch, and pulled the OCR rule pack. I reviewed every file directly. I wrote no fixes and ran no project tests. Every finding below is reasoned from the source; none has a failing command, because running the handler needs a DB and tRPC harness I was told not to set up.

### Important

1. **packages/trpc/server/routers/viewer/bookings/addGuests.handler.ts:74-78 — Important — the blacklist check can be bypassed by changing the case of the email or adding a `+tag`.**
   - The code lowercases the `BLACKLISTED_GUEST_EMAILS` entries but compares the raw `guest` with `includes(guest)`, and never calls `extractBaseEmail`.
   - The existing path in `packages/features/bookings/lib/handleNewBooking.ts:742-743` does `extractBaseEmail(guest).toLowerCase()` and compares lowercased values. `checkIfBookerEmailIsBlocked.ts:17-18` does the same.
   - So `Blocked@x.com` or `blocked+1@x.com` gets past this filter, is added as an attendee, and is sent an invite.
   - The existing-attendee de-dup on the same lines is also case-sensitive, so `A@x.com` can be added next to `a@x.com`.

2. **addGuests.handler.ts:46-48 — Important — team admins are refused even though the variable is named `isTeamAdminOrOwner`.**
   - The code is `isTeamAdmin(...) && isTeamOwner(...)`.
   - `isTeamAdmin` (packages/lib/server/queries/teams/index.ts:264-283) already matches `role: ADMIN` or `OWNER`, so the `&&` collapses to "is owner".
   - A team ADMIN who is not the organizer gets FORBIDDEN. It should be `||`, or just `isTeamAdmin`.

3. **addGuests.handler.ts:52-56 and _router.tsx:79 — Important (security) — permissions are wider than the existing booking mutations, and the guest list has no size limit.**
   - The new route uses plain `authedProcedure` with its own check, which lets in any logged-in user whose `user.email` equals any attendee's email.
   - The comparable mutation `editLocation` uses `bookingsProcedure` (bookings/util.ts:19-63). That only allows the organizer or a COLLECTIVE host.
   - The schema (addGuests.schema.ts:5) has no `.max()` on `guests`.
   - Result: a booker with a Cal account can add any number of arbitrary addresses. Each one gets a calendar invite sent in the organizer's name (`from: organizer.name`, `replyTo: organizer.email`), and the organizer's external calendar event is changed (handler line 165). That is a spam/abuse path.
   - Collective hosts who are neither `booking.userId` nor attendees are now refused, which is a regression against `bookingsProcedure`.

4. **addGuests.handler.ts:26-56 — Important — the server never checks the booking's status or time.**
   - The UI only shows the action when `isUpcoming && !isCancelled` (BookingListItem.tsx:544), but the API accepts any booking id.
   - Adding guests to a CANCELLED, REJECTED or past booking writes attendee rows and sends `method: "REQUEST"`, `status: "CONFIRMED"` ICS invites (attendee-add-guests-email.ts:10-17, organizer-add-guests-email.ts:14-20). That effectively brings a cancelled meeting back onto recipients' calendars.

### Minor

5. **addGuests.handler.ts:168 — sends emails based on the raw `guests` input instead of `uniqueGuests`.**
   - email-manager.ts:541-545 sends `AttendeeScheduledEmail` (a fresh confirmation) to every attendee whose email is in `newGuests`.
   - If the request repeats an existing attendee's address, that attendee gets a fresh confirmation instead of the "guests added" notice.

6. **addGuests.handler.ts:74, schema line 5 — duplicates inside one request are not removed on the server.**
   - Only the client checks uniqueness (AddGuestsDialog.tsx:27-30). A direct API call with `["a@x.com","a@x.com"]` creates two attendee rows and sends two emails.
   - There is also no transaction or uniqueness guard, so two concurrent requests can both pass the de-dup and insert the same guest.

7. **addGuests.handler.ts:165-171 — failures are handled badly.**
   - `updateCalendarAttendees` runs after the DB insert, with no try/catch at this level. If it throws, the client gets an error even though the attendees were saved. A retry then fails with BAD_REQUEST `emails_must_be_unique_valid`.
   - When email sending fails, the `catch` logs a fixed string and drops `err`.

8. **addGuests.handler.ts:124-147 + email-manager.ts:531 — the team branch in `sendAddGuestsEmails` never runs.**
   - `evt` has no `team` set, so `calendarEvent.team?.members` is always undefined and team members are never emailed.

9. **email-manager.ts:542/544 — seated events with `seatsShowAttendees: true` show only the recipient.**
   - `AttendeeScheduledEmail` is constructed without its `showAttendees` argument (attendee-scheduled-email.ts:19-26). For any seated event, every email lists only the recipient, even when the event type says attendees should be shown.
   - Adding attendees to a seated booking also bypasses `seatsPerTimeSlot` and creates no seat records.

10. **AddGuestsDialog.tsx:43-46 — the error toast fallback can never trigger, and one message key is missing.**
    - The template string `${code}: ${t(msg)}` is never falsy, so `unable_to_add_guests` is never shown.
    - The handler throws `you_do_not_have_permission`, which is not in en/common.json. The user sees the raw text `FORBIDDEN: you_do_not_have_permission`.

11. **AddGuestsDialog.tsx:34,88-93,114 — the validation error can be stale when the dialog is reopened.**
    - `isInvalidEmail` is never reset on success, on edit, or when the dialog is closed through `onOpenChange` (overlay or Esc). Only the Cancel button resets it.
    - Reopening the dialog can show an old "Emails must be unique and valid" error. Closing through the overlay also keeps the old email values.

### Files not reviewed
None. All 15 files in the patch were reviewed: BookingListItem.tsx, AddGuestsDialog.tsx, en/common.json, email-manager.ts, AttendeeAddGuestsEmail.tsx, OrganizerAddGuestsEmail.tsx, emails templates/index.ts, attendee-add-guests-email.ts, organizer-add-guests-email.ts, _router.tsx, addGuests.handler.ts, addGuests.schema.ts, MultiEmail.tsx, MultiEmailLazy.tsx and packages/ui/index.tsx. The locale file, index re-exports and the lazy wrapper were only checked to confirm the keys and exports exist.

Not checked: recurring-booking behaviour (only one occurrence is updated) and how the EventManager calendar update behaves when an attendee or admin uses their own credentials. EventManager falls back to fetching the credential from the DB by `reference.credentialId`, so I did not report the credentials point.
