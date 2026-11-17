Review seat: over-engineering only (ponytail:ponytail-review). I read the patch, `packages/lib/slots.ts` (getSlots), `checkIfIsAvailable` and its three callers in `packages/trpc/server/routers/viewer/slots.ts`, and the other getSlots callers (TeamAvailabilityTimes v1/v2, slots.test.ts). I ran nothing, as instructed. Every claim below is reasoned from the code, not from a failing test.

**What this change does:** getSlots now shifts each date override from the organizer's time zone into the invitee's before turning it into minutes-of-day. `checkIfIsAvailable` gains two checks for each host. First, if that host has a date override on the slot's day, the slot must fall inside it. Second, if there is no override, the slot must fall inside the host's working hours. The PR adds `timeZone` to each flattened override and passes `organizerTimeZone` through.

**Should fix**

1. **The override check uses a mutated flag and gives the wrong answer when a day has several override ranges** (`packages/trpc/server/routers/viewer/slots.ts:103-135`, Important)
   - **What this is:** `.find()` is used as a loop with a side effect. The callback sets the outer `dateOverrideExist = true` and returns true when the slot is outside an override.
   - **Problem:** The shape is hard to follow, and it hides a bug. If a host has two override ranges on one day (9:00–10:00 and 14:00–15:00), a 9:00 slot is outside the second range. So `find` returns true and the slot is rejected, and the same happens to every slot that day. Reasoned: no test has two ranges on one day.
   - **Fix:** Drop the flag. `const dayOverrides = dateOverrides.filter(sameDay); if (dayOverrides.length) return dayOverrides.some(slotInside);`. Compute the shifted `start` and `end` once per override. Today `dayjs(date.start).add(utcOffset,"minutes")` is built four times. This saves about 10 lines and fixes the multi-range case.
   - **If we skip it:** Hosts who split a day into several override windows get no bookable slots that day.

2. **A dead equality branch** (`slots.ts:114-116`, Important)
   - **What this is:** `dayjs(a) === dayjs(b)` compares two different objects with `===`.
   - **Problem:** Two separate dayjs objects are never `===`, so this branch can never run. It looks like it handles the "unavailable all day" override (start equals end), but it does nothing.
   - **Fix:** Delete the branch (−3 lines). If the case matters, write it as `.isSame(...)` inside the rewrite from finding 1.
   - **If we skip it:** Readers think the all-day-unavailable case is handled when it is not.

3. **`end` is a copy of `start`** (`slots.ts:141-142`, Important)
   - **What this is:** In the working-hours check, `start` and `end` are both computed from `slotStartTime`.
   - **Problem:** `end` is a duplicate, and almost certainly a typo for `slotEndTime`. Example: working hours 9:00–17:00, a 60-minute event, 30-minute interval. The 16:30 slot passes the check even though it ends at 17:30. This is reachable for collective events, where another fixed host's override replaces the combined working hours in getSlots.
   - **Fix:** Use `slotEndTime` for `end`, or drop `end` and check `slotEndTime` directly.
   - **If we skip it:** A fixed host can be booked past the end of their working day.

4. **A lookup and prop that do nothing in the selected-slots path** (`slots.ts:579`, `slots.ts:585`, Minor)
   - **What this is:** The third `checkIfIsAvailable` call now looks up `userSchedule` and passes `organizerTimeZone`.
   - **Problem:** That call passes no `dateOverrides` and no `workingHours`, so both default to `[]`. `organizerTimeZone` is only read inside `dateOverrides.find`, so it is never used here. The `.find` over all users runs once per slot per user for nothing.
   - **Fix:** Delete line 579 and the `organizerTimeZone` prop (−3 lines).
   - **If we skip it:** Dead work in a loop, and readers think time zones matter in this path.

**Nice to have**

5. **The same dayjs chain is built twice for start and twice for end** (`packages/lib/slots.ts:218-223`, Minor)
   - **Fix:** Compute it once: `const s = dayjs(override.start).utc().add(offset,"minute"); startTime: s.hour()*60 + s.minute()`, and the same for end. The `.toString()` on lines 212-213 can also go: `dayjs(override.start)` takes a Date directly, so the round trip through a string adds nothing. `flatMap` (line 211) also returns a single object, so it should be `map`.

6. **The time-zone prop duplicates a field already spread in** (`slots.ts:82,93,492,517`, Minor)
   - **What this is:** `...schedule` and `...userSchedule` already pass `timeZone`, then each caller also sets `organizerTimeZone: x.timeZone`.
   - **Fix:** Have `checkIfIsAvailable` take `timeZone` and drop the explicit props (−2 to −3 lines).

7. **An inline type copies an existing one** (`slots.ts:87-90`, Minor)
   - **Fix:** `dateOverrides?: { start: Date; end: Date }[]` is the same as `TimeRange[]` from `@calcom/types/schedule`, which this PR already edits and which `lib/slots.ts` imports as `DateOverride`. Reuse it.

Also: there are two parallel ways to carry the override's time zone. getSlots reads `override.timeZone`, newly added to `TimeRange` in `packages/types/schedule.d.ts`, while `checkIfIsAvailable` takes a separate `organizerTimeZone`. Choosing one would remove the other. I am not counting this as a finding, because the per-user `dateOverrides` that reach `checkIfIsAvailable` come from `getUserAvailability` without `timeZone`.

Verdict: fix 1 and 3 first. Both look like lean issues (a flag-driven `find` and a duplicated variable) but each hides a wrong result. Then 2 and 4.
Lean: about −20 lines possible.
Not checked: whether `workingHours` in `checkIfIsAvailable` are in UTC minutes while the override check uses organizer-local time (that is the correctness seat). I also did not check the getSlots behaviour when `override.timeZone` is undefined; the other callers (TeamAvailabilityTimes) appear not to pass dateOverrides.

Files reviewed: all four in the patch. `apps/web/test/lib/getSchedule.test.ts` was only read, for over-engineering, and has no finding. It adds one +6 time-zone case and nothing for multiple override ranges on one day or for a slot that runs past working hours (findings 1 and 3). `packages/types/schedule.d.ts` is covered under finding 7 and the note above it. No file was left unreviewed.
