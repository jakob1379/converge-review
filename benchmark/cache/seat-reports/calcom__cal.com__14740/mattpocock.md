I reviewed all 15 files in <bench>/work/calcom__cal.com__14740.scratch/change.patch using the `mattpocock-skills:code-review` skill. Per the override, I ran both axes myself with no sub-agents.

**Inputs and assumptions**
- Fixed point: b004587262. There is no spec, so the spec axis only covers what the patch itself implies: owners, admins, organizers and attendees can add guests; the existing attendees get a "guests added" email; the new guests get a booking email; the calendar event is updated.
- Standards sources:
  - `CONTRIBUTING.md`, which only asks for clean lint, a production build and the yarn.lock rules.
  - `packages/config/eslint-preset.js`.
  - `packages/eslint-plugin` recommended rules, including `no-prisma-include-true` (warn).
  - Conventions set by the sibling code: `editLocation` (`bookingsProcedure`), `sendLocationChangeEmails`, how `handleNewBooking` handles the guest blacklist, and the role check in `confirm.handler`/`get.handler`.
- I wrote no executable failing tests, because installing deps or running project checks was off-limits. Every Critical/Important finding below is reasoned from code, with exact evidence.

## Spec axis (implied by the patch)

1. **`packages/trpc/server/routers/viewer/bookings/addGuests.handler.ts:46-48` — Important.**
   - Claim: the `isTeamAdminOrOwner` check lets only team owners through. Team admins get FORBIDDEN, even though the variable name says admins should pass.
   - Evidence: the code is `isTeamAdmin(...) && isTeamOwner(...)`. `isTeamAdmin` (`packages/lib/server/queries/teams/index.ts:264-284`) already matches `role ADMIN OR OWNER`, and `isTeamOwner` (`:286-295`) matches `OWNER` only. So the AND reduces to owner-only.
   - The repo convention is `role === OWNER || role === ADMIN` (`confirm.handler.ts:127-128`, `get.handler.ts:405-406`).
   - Failure case: a team ADMIN who is not the organizer or an attendee calls `addGuests` on a team booking and gets FORBIDDEN.

2. **`addGuests.handler.ts:70-78` — Important.**
   - Claim: the `BLACKLISTED_GUEST_EMAILS` filter can be bypassed by changing the case of an email or adding a plus-alias.
   - Evidence: the blacklist is lowercased, but `guest` is compared raw with `.includes(guest)`. `extractBaseEmail` is never applied.
   - `handleNewBooking.ts:741-745` sets the convention: `extractBaseEmail(guest).toLowerCase()` compared case-insensitively.
   - Failure case: with `BLACKLISTED_GUEST_EMAILS=bad@x.com`, the inputs `Bad@x.com` and `bad+1@x.com` are both inserted as attendees and emailed.

3. **`addGuests.handler.ts:168` with `packages/emails/email-manager.ts:525-549` — Important.**
   - Claim: `sendAddGuestsEmails` ignores the event type's settings that turn off standard host and attendee emails.
   - Evidence: the sibling `sendLocationChangeEmails` (`email-manager.ts:495-523`) gates host emails on `eventTypeDisableHostEmail(metadata)` and attendee emails on `eventTypeDisableAttendeeEmail(metadata)`. The new function takes no metadata, has no such gate, and the handler passes none.
   - Failure case: on an event type that disables standard emails (e.g. because it uses workflows), adding a guest still sends Cal.com organizer and attendee emails.

4. **`addGuests.handler.ts:168` — Minor.**
   - Claim: the handler passes the raw input `guests` instead of the filtered `uniqueGuests`.
   - Effect: an email that was already an attendee and is re-submitted alongside a real new guest gets a fresh "scheduled" email instead of the "guests added" update (the split happens at `email-manager.ts:541`).

5. **`packages/trpc/server/routers/viewer/bookings/addGuests.schema.ts:5` — Minor.**
   - Claim: the server never checks that the submitted emails are unique; only the client dialog (`AddGuestsDialog.tsx`, the `.refine`) does.
   - Failure case: a direct tRPC call with `["a@x.com","a@x.com"]` creates two attendee rows. The case-sensitive comparison with existing attendees (`handler:76`) also lets `A@x.com` in alongside `a@x.com`.

6. **`addGuests.handler.ts:10-30` (route at `_router.tsx:79`) — Minor.**
   - Claim: the authorization model differs from the sibling booking-edit endpoint without saying why.
   - `editLocation` runs through `bookingsProcedure` (`util.ts`): organizer, or host of a COLLECTIVE event.
   - `addGuests` uses plain `authedProcedure` with a custom check, so:
     - collective co-hosts are excluded;
     - any attendee whose email matches the logged-in user is allowed.
   - Reasoned; there is no spec to say which model is intended.

7. **`addGuests.handler.ts:124-147` with `email-manager.ts:531-537` — Minor.**
   - Claim: `evt` is built without `team`, so the team-member loop in `sendAddGuestsEmails` never runs. Team hosts are never notified. Reasoned.

8. **`addGuests.handler.ts:158-165` — Minor.**
   - Claim: `EventManager` gets the caller's credentials (`ctx.user`), not the organizer's. `booking.user.credentials` is fetched but never used.
   - Most updates are unaffected, because `updateAllCalendarEvents` falls back to loading credentials from the DB by `reference.credentialId`.
   - References with no `credentialId`, and `other_calendar` (CRM) refs, are matched against the caller's credentials. When an attendee or owner adds guests, those integrations are skipped or the wrong credential is used. Reasoned.

9. **`addGuests.handler.ts:72-101` — Minor.**
   - Claim: there is no check for seated events or booking status. On a seated booking (`seatsPerTimeSlot`) guests are added outside the seat model.
   - Also, `sendAddGuestsEmails` emails every attendee the full attendee list, regardless of `seatsShowAttendees`.
   - Reasoned; the UI only shows the action on upcoming, non-cancelled bookings, but the server does not enforce that.

## Standards axis

10. **`addGuests.handler.ts:30-40` — Minor (lint warning).**
   - Claim: the `findFirst` uses `include: { attendees: true, eventType: true, destinationCalendar: true, references: true, user: { include: { destinationCalendar: true, credentials: true } } }`. The repo rule `@calcom/eslint/no-prisma-include-true` (warn) flags this on `findFirst`.
   - Precedent: the block is copied verbatim from `bookingsProcedure` in `util.ts`, which has the same warning.
   - It also loads the organizer's full credential keys only to leave them unused (see 8).

11. **`packages/ui/form/MultiEmail.tsx:12` — Minor, judgement call (Duplicated Code).**
   - Claim: this is a near-verbatim copy of the `multiemail` factory in `packages/features/form-builder/Components.tsx:231-310`.
   - That factory carries `//TODO: Make it a ui component`. The patch creates the UI component but does not switch form-builder to it, so two copies now drift (they already differ in label `htmlFor`, `data-testid`s and spacing).

12. **`addGuests.handler.ts:46` — Minor, judgement call (Mysterious Name).**
   - Claim: `isTeamAdminOrOwner` does not match what it computes (owner-only); this is the same root cause as finding 1.

What I checked and found no issue with:
- `addGuests` follows the existing lazy-handler pattern in `_router.tsx`.
- `MultiEmail` importing `@calcom/ui` inside `packages/ui` has precedent.
- The icon names `user-plus` and `triangle-alert` exist in `icon-names.ts`.
- `updateCalendarAttendees` exists at base (`EventManager.ts:596`).
- Every i18n key used exists in en `common.json` (`additional_guests`, `add_another`, `emailed_you_and_any_other_attendees`, `add`, `cancel`) or is added by the patch.
- `console.log` in the email catch matches `editLocation.handler.ts:140`.
- No tests were added. `CONTRIBUTING.md` does not require them, so this is not a standards breach; `apps/web/playwright/bookings-list.e2e.ts` would be the natural home.

**Summary:**
- Spec axis: 9 findings. The worst are the owner-only role check (finding 1), the blacklist bypass (2), and email suppression being ignored (3).
- Standards axis: 3 findings, all Minor. The worst is the `no-prisma-include-true` lint warning that also pulls credential keys (10).

**Unreviewed files:** none. All 15 files in the patch were reviewed. Only the en `common.json` changed, so whether other locales are needed was not assessed (they appear to be managed through Crowdin per `crowdin.yml`).

I ran no lint, typecheck or tests, so every finding is reasoned from source rather than demonstrated.
