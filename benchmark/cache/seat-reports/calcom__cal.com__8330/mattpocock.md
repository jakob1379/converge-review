I ran `mattpocock-skills:code-review` and did both axes myself, with no sub-agents. Diff reviewed: 93cb21f55a...ee38fd295f (11 commits on fix/round-robin-date-override). There are no node_modules, so I ran nothing. Every finding is reasoned. Two proposed failing tests, not run, are in <bench>/work/calcom__cal.com__8330.scratch/override-ignores-busy.test-snippet.ts.

## Standards

**Sources:** CONTRIBUTING.md (only says run `yarn lint` and a full build), .github/PULL_REQUEST_TEMPLATE.md, packages/config/eslint-preset.js. There is no AGENTS.md, CLAUDE.md or CODING_STANDARDS in the repo.

- **Documented standards:** I found no hard breach. The `WorkingHours` import uses `import type`, which satisfies consistent-type-imports. Nothing is left unused.
- **Minor, PR template checklist ("added tests that prove my fix is effective"):** The branch is about round-robin overrides, but the only new test (getSchedule.test.ts:788-804) covers a single fixed user in a second invitee timezone. Not tested: round-robin or non-fixed hosts, hosts in different timezones, and the new working-hours branch in `checkIfIsAvailable`. The new test also reuses the +5:30 day window (18:30Z) for the Asia/Dhaka (+6:00) invitee.
- **Baseline smells (all judgement calls):**
  - **Duplicated Code:** `dayjs(date.start).add(utcOffset, "minutes")` is rebuilt four times at viewer/slots.ts:110-123. `dayjs(override.start).utc().add(offset,"minute")` is built twice at lib/slots.ts:219-222.
  - **Mysterious Name:** the `organizerTimeZone` parameter of `checkIfIsAvailable` actually receives each host's timezone. Likewise `organizerUtcOffset` in lib/slots.ts:212 is the override owner's offset.
  - **Speculative Generality:** viewer/slots.ts:585 passes `organizerTimeZone` into a call that never passes `dateOverrides` or `workingHours`, so it does nothing.

## Spec (no spec given; intent taken from the title "use the correct timezone of user for date overrides" and the branch name)

1. **Critical – viewer/slots.ts:133-135.** When a slot falls on a day with an override and inside it, `if (dateOverrideExist) return true;` returns before `busy.every(...)`. On override days, existing bookings and calendar busy times are ignored, so people can be double-booked. Pre-patch code always ran the busy check.
   - Test: snippet 1 in the scratch file (booking at 09:30Z inside the IST override; expected slots 08:30, 10:30, 11:30). It should fail on the patch.
2. **Critical – viewer/slots.ts:107-111.** The code shifts the override to its real UTC instant, then compares the UTC date with `format("YYYY MM DD")` against the slot's UTC date.
   - For hosts east of UTC, an override on day D that starts before the UTC offset lands on UTC date D-1. An "unavailable" override (00:00-00:00) on D becomes D-1 18:30Z for IST. Every working-hours slot on D-1 is then "not within the override" and gets rejected.
   - For hosts west of UTC, override slots after UTC midnight miss the date match and fall through to the working-hours check.
   - `dayjs(date.start)` is in local mode while `slotStartTime` is UTC, so results also depend on the server's TZ.
   - Test: snippet 2 (unavailable override on plus3; expects all 8 plus2 slots). It should fail on the patch.
3. **Important – viewer/slots.ts:139-146 (working-hours check).**
   - `end` is computed from `slotStartTime` instead of `slotEndTime`, so a slot that runs past the end of working hours passes.
   - `.find` rejects the slot if it falls outside any one range on that day. Split hours on one day (e.g. 9-12 and 13-17) therefore reject valid slots in the second range.
   - This branch now runs for every fixed host, which includes all personal event types (`isFixed: !schedulingType`, line 369). So the behaviour change reaches well beyond round robin. Reasoned.
4. **Important – viewer/slots.ts:117-125.** The override containment check only rejects slots that end at or before the override start, or that start after the override end. A slot that starts before the override and ends inside it, or starts inside and runs past the end, is accepted. Reasoned.
5. **Minor – viewer/slots.ts:114.** `===` between two dayjs objects is always false, so the zero-length (unavailable day) branch is dead code.
6. **Important – lib/slots.ts:206-208 (spec gap).** The `activeOverrides` day filter still compares the raw wall-time-as-UTC `override.start` against the invitee's day without a timezone correction. Example: an IST override 02:00-05:00 on D, viewed by a UTC invitee. It is selected for day D but shifted to 20:30-23:30, so slots are emitted on D when the real instant is D-1. The fix is half-applied. Reasoned.
7. **Important – lib/slots.ts:218-223.** Wrapping with `hour()*60+minute()` gives `endTime < startTime` when the shifted override crosses the invitee's midnight. Example: IST 14:00-18:00 viewed from +12:00 becomes 20:30-00:30, which yields no slots. Before the patch there was no shift, so this regression is new. Reasoned.
8. **Minor – lib/slots.ts:212.** `override.timeZone` is optional (schedule.d.ts). When it is undefined, `.tz(undefined)` falls back to the process's local timezone, so callers that don't set it get results that depend on the host machine.

Summary: Standards has 1 documented-standard item (Minor) and 3 smells, worst being the missing round-robin test. Spec has 8 findings, worst being #1 (busy times ignored on override days, so double bookings), together with #2 (an override on one day blocks the neighbouring day).

Files not reviewed: none. All four patch files were reviewed. packages/types/schedule.d.ts only adds the optional `timeZone` field, which is covered under #8.

Not checked: I didn't run lint, build or tests, so the two test snippets have not been seen to fail. Treat #1 and #2 as high-confidence reasoning that still needs a run.
