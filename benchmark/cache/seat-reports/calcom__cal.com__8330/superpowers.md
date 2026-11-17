## Code review: calcom__cal.com__8330, "use the correct timezone of user for date overrides"

**Verdict: do not merge.** The `getSlots` offset fix in `packages/lib/slots.ts` is the right idea. The problem is the large new block in `checkIfIsAvailable` (`packages/trpc/server/routers/viewer/slots.ts`). Before this patch the function ignored the `workingHours` and `dateOverrides` that callers spread in through `...schedule` and `...userSchedule` (the fixed-host and round-robin host paths). Now it uses them, and the new logic has several serious bugs.

I could not run the jest suite: `node_modules` is absent and I was told not to install anything or run project checks. So I wrote a dependency-free Node script that copies the patched predicates using UTC `Date`:
`<bench>/work/calcom__cal.com__8330.scratch/repro.mjs`
Run it with `node <that path>`. All four cases print `true`, which reproduces findings 1–4 at the predicate level. The end-to-end effect through `getSchedule` is reasoned, not run.

### Critical

**1. `packages/trpc/server/routers/viewer/slots.ts:133-135`: busy times are skipped on any day that has a date override.**
- `if (dateOverrideExist) return true;` runs before the `busy.every(...)` check.
- Any slot inside an override window is therefore reported as available, even if it overlaps an existing booking or calendar event.
- This affects the fixed-host path (`...schedule`, around line 488) and the round-robin host path (`...userSchedule`).
- Result: double bookings on every override day.
- Repro case 3. A `getSchedule` test would catch it: use the `IstWorkHoursWithDateOverride` fixture plus a booking at plus2 08:30Z, and the 08:30Z slot is still returned.

**2. `slots.ts:138-151`: the working-hours check rejects valid slots whenever a day has more than one working-hours entry.**
- It uses `workingHours.find(wh => day matches && slot outside wh)`. That means "outside ANY range". The correct test is "inside SOME range".
- `getWorkingHours` (`packages/lib/availability.ts:62-127`) splits any range that crosses UTC midnight into two entries with overlapping `days`.
- Example: a US-Pacific organizer with Mon–Fri 09:00–17:00 PST gets `[1-5] 1020–1439` and `[2-6] 0–60`. Every Tue–Fri slot is outside one of those two entries, so Tue–Fri lose all slots.
- Split hours on the same day (09–12 plus 13–17) lose everything too.
- Repro cases 1 and 2.
- Separately, line 142 has a copy-paste bug: `const end = slotStartTime.hour()...` should use `slotEndTime`. Slots that run past the end of working hours are never rejected.

### Important

**3. `slots.ts:108-128`: an override is matched to slots by its UTC calendar date, not the organizer's local date. It wipes out normal availability on a neighbouring day.**
- Every slot on the same UTC date that falls outside the override window returns `false`.
- Example (UTC-7 organizer): an override from 18:00–20:00 local on Nov 17 is Nov 18 01:00–03:00Z. The organizer's normal Nov 18 10:00 slot (17:00Z) has the same UTC date, so it is rejected. The whole next day is lost.
- The mirror case: early-morning overrides for organizers ahead of UTC (Asia/Kolkata before 05:30, JST before 09:00) wipe out the previous day.
- Repro case 4.
- Also, `dayjs(date.start).add(...).format()` formats in the server's local timezone, but `slotStartTime` is UTC. On any server not running in UTC, the date strings will not match.

**4. `packages/lib/slots.ts:206-207` vs `212-224`: the override's offset is corrected, but the day it lands on is not.**
- `activeOverrides` still treats the stored wall-clock value (organizer local time, saved as if it were UTC) as a real instant when picking the invitee day.
- The new `startTime`/`endTime` are taken modulo 24h with no day carry.
- Example: Asia/Kolkata organizer, override D 02:00–04:00 IST, UTC invitee.
  - The override should show on D-1 at 20:30Z.
  - It lands on day D as `startTime` 1230 (20:30). Finding 3's check then drops it.
- An override whose start wraps but whose end does not gives `startTime > endTime`. Example: +6 organizer, 05:00–08:00 local, UTC invitee, gives 23:00 → 02:00, and the override's availability disappears.
- This is reasoned from the code; I did not execute it.

**5. `apps/web/test/lib/getSchedule.test.ts:788-804`: the new test cannot catch any of the above.**
- It reuses the +5:30 day window (`plus1 18:30Z – plus2 18:29Z`) with `timeZone` set to +6:00. The window does not match the +6 day.
- It has one fixed host, no bookings, no round-robin, and an override in the middle of the day.
- The branch is `fix/round-robin-date-override`, yet no test exercises round-robin or loose hosts.
- Needed: overrides plus busy times, a timezone-crossing case, and multiple hosts.

### Minor

- **`slots.ts:114`:** `dayjs(a) === dayjs(b)` compares object identity, so it is always false. The intended "unavailable all day" branch (start == end) is dead code. `getSlots` masks this in practice.
- **`slots.ts:124`:** only `slotStartTime.isAfter(end)` is checked. A slot that starts inside the override but ends after it is accepted.
- **`packages/lib/slots.ts:212-213`:** `dayjs(override.start.toString())` parses `Date.prototype.toString()` output, which is non-ISO and depends on the engine. `dayjs(override.start)` is enough. If `override.timeZone` is undefined (the type makes it optional), `.tz(undefined)` silently uses the process timezone. Only `getSchedule` passes overrides today, so this is latent.
- **`slots.ts:107`:** the offset comes from the stored UTC-labelled time, not the actual local time, so it can be wrong on DST-transition dates.
- **Spec gap:** there is no spec. The title promises a timezone fix. The patch also adds new enforcement of working hours and overrides in `checkIfIsAvailable`, which the title does not mention and which causes findings 1–3.

### Files reviewed / not reviewed

I reviewed all four files in the patch:
- `apps/web/test/lib/getSchedule.test.ts`
- `packages/lib/slots.ts`
- `packages/trpc/server/routers/viewer/slots.ts`
- `packages/types/schedule.d.ts` (just the optional `timeZone` field; no issue)

None were skipped. I read `packages/core/getUserAvailability.ts` and `packages/lib/availability.ts` for context only.

**Not checked:** I did not run the real `getSchedule` tests (no dependencies installed). Findings 1–4 are confirmed at the predicate level, and their full end-to-end effect is reasoned.
