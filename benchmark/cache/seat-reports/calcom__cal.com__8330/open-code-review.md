## Review: calcom__cal.com__8330, "use the correct timezone of user for date overrides" (93cb21f5 → ee38fd29)

I ran this through the OCR delegate flow: `ocr delegate preview --from/--to`, then `ocr delegate rule`. I reviewed the patch directly and did not edit anything. There is no `node_modules` in the checkout, and I was told not to install, so I ran nothing. Every claim below is reasoned from the code. Where it fits, I give a concrete test that should fail on the patched code.

Verdict: do not merge. The new `checkIfIsAvailable` logic adds two regressions that hit every event type, not only round-robin with overrides. One allows double booking. The other drops availability for common schedules.

### Findings

**1. Critical: `packages/trpc/server/routers/viewer/slots.ts:133-135`. On any date that has an override, busy times are ignored.**
- When `dateOverrideExist` is true, the function returns `true` before reaching `busy.every(...)`.
- Any slot inside an override window counts as available, even if there are existing bookings or calendar busy times. That means double bookings.
- Failing test: in "Check for Date overrides" (`apps/web/test/lib/getSchedule.test.ts`), add a booking for user 101 at `${plus2DateString}T08:30:00Z–09:29:59Z`. Expect `08:30:00.000Z` to be absent. The patched code still returns it.

**2. Critical: `packages/trpc/server/routers/viewer/slots.ts:138-151`. The working-hours check rejects valid slots.**
- `workingHours.find` returns true if *any* block that covers that weekday does not contain the slot.
- If a user has two blocks on the same day, every slot is outside one of them, so every slot is rejected. A split day such as 09:00–12:00 plus 13:00–17:00 loses all availability.
- Timezone alone triggers the same thing. `getWorkingHours` (`packages/lib/availability.ts:101-121`) splits hours that cross UTC midnight into a main block and an overflow block. Example: America/Los_Angeles, 9–17, Mon–Fri becomes `[1..5]` 1020–1439 plus `[2..6]` 0–60. A Tuesday 00:00Z slot (Monday 16:00 local) fails the Tuesday main block and is dropped. The last hour of Mon–Thu disappears.
- This runs on every `getSchedule` call, because `...schedule` / `...userSchedule` spread `workingHours` into the call.
- Separate bug on line 142: `const end = slotStartTime.hour()*60 + slotStartTime.minute()` should use `slotEndTime`. As written, slots that run past the end of working hours are never rejected.
- Failing test: a single user with availability 09:00–12:00 and 13:00–17:00 UTC on all days. Expect slots. The patched code returns none.

**3. Important: `packages/trpc/server/routers/viewer/slots.ts:108-113`. An override is matched to slots by the UTC calendar date of its start, not the organizer's local date.**
- Example: an Australia/Sydney organizer has an override on Jan 10, 09:00–12:00 local, which is Jan 9 23:00Z to Jan 10 02:00Z.
- Every slot on UTC Jan 9 (most of Jan 9 local) is treated as "outside the override" and rejected.
- Slots inside the override that fall on the other UTC date skip the override entirely and are judged on working hours.
- A smaller mismatch: `dayjs(date.start)...format()` formats in the server's local timezone, while `slotStartTime` is UTC. The two only agree when the server runs in UTC.

**4. Important: `packages/trpc/server/routers/viewer/slots.ts:123`. The end boundary only checks `slotStartTime.isAfter(end)`.**
- A slot that starts inside the override but ends after it passes.
- So does a slot that starts exactly at the override's end.
- It should test `slotEndTime.isAfter(end)`.
- This matters for round-robin. `getSlots` builds the union of all hosts' slots, so this check is the only per-host gate. Host B with an override of 09:00–12:00 would be assigned 11:30–12:30.

**5. Important: `packages/lib/slots.ts:211-225`. After the offset is applied, an override can wrap past the invitee's midnight, and then it vanishes.**
- `hour()*60+minute()` wraps around midnight, so `endTime < startTime`.
- `buildSlots` skips that range (`if (start >= end) continue`, line 68). The user's working hours for that day were already removed at lines 228-243, so the day has zero slots.
- Example: organizer America/New_York with an override of 09:00–17:00 and an invitee in Asia/Kolkata. The offset is +570, giving 1110 to 150, which is dropped.
- Before the patch the slots were wrong but at least present. After it there are none.
- The cause is that `activeOverrides` (lines 205-207, unchanged) still picks the invitee day using the organizer's wall-clock time treated as a UTC instant. The conversion assumes that day is correct.

**6. Minor: `packages/trpc/server/routers/viewer/slots.ts:114`.** `dayjs(a) === dayjs(b)` compares two Dayjs objects by identity, so it is always false and the branch is dead. A whole-day "unavailable" override (start equals end) leans on the later checks instead, and a slot that starts exactly at that instant falls through as available.

**7. Minor: `packages/lib/slots.ts:212-213`.**
- `dayjs(override.start.toString())` parses the non-ISO output of `Date#toString()`. That relies on engine-specific parsing and drops milliseconds; `dayjs(override.start)` is enough.
- `TimeRange.timeZone` is optional (`packages/types/schedule.d.ts:5`). When it is missing, `.tz(undefined)` falls back to the default or server timezone without any warning.
- The offset is taken at the fake-UTC wall-clock instant, so it can be wrong on DST-transition days.

**8. Minor (test gap): `apps/web/test/lib/getSchedule.test.ts:788-804`.**
- The new case only changes the invitee timezone, for one user with no bookings.
- It does not test round-robin (the purpose of the branch), busy times on an override day, an organizer whose hours cross UTC midnight, or split hours.
- The query window was copied from the IST case (starting at 18:30Z) rather than Dhaka's midnight (18:00Z).
- Findings 1–5 would all pass this test.

### Coverage

| File | Status | Note |
|---|---|---|
| `packages/lib/slots.ts` | reviewed | |
| `packages/trpc/server/routers/viewer/slots.ts` | reviewed | |
| `packages/types/schedule.d.ts` | reviewed | No issue beyond finding 7. |
| `apps/web/test/lib/getSchedule.test.ts` | reviewed by hand | OCR excluded it by default path; I read it anyway. |

OCR counts: total_files 4, reviewable 3, reviewed 3, skipped 0, coverage 100%. No spec was provided, so there are no spec-gap findings. The OCR ruleset adds only generic TS rules, and nothing beyond the items above breaches them.

I did not execute anything, because there are no dependencies installed. The failing tests for findings 1 and 2 are the fastest way to confirm before anyone acts on this.
