OCR delegate review of range ba9688a04a..820d7fa87e: 12 of 12 files reviewed (100%). The OCR rules are the generic TS/JS checklist; the ones that matter here are "Dead Code" and "Async Handling: error handling". No spec was given, so I judged intent from the branch name: load app-store packages lazily and asynchronously. Report only. I changed nothing in the repo.

## Findings

**1. packages/app-store/index.ts:3-30. Important. The change makes the imports async but does not make them lazy.**
- **Claim:** `appStore` is an object literal of `import("./x")` calls, and those run when the module is evaluated. The first import of `@calcom/app-store` (from `getCalendar.ts`, `videoClient.ts`, `handlePayment.ts`, `deletePayment.ts`, `handleCancelBooking.ts` or `bookings.tsx`) therefore still loads and runs all 28 app packages. The only lazy part is that callers now have to `await`. The win the branch name promises (load only the app you need) never happens. The cost is that every call site became async.
- **Evidence:** I ran this repro in the scratchpad:
  ```
  store.mjs: export default { a: import("./a.mjs"), b: import("./b.mjs") }
  main.mjs:  import s from "./store.mjs"; await s.a;
  $ node main.mjs  ->  "a loaded" / "b loaded" / "only asked for a"
  ```
  Module `b` loads even though only `a` was awaited.
- **Simpler fix:** make each entry a thunk, `applecalendar: () => import("./applecalendar")`, and have callers do `await appStore[key]?.()`. The call sites stay the same shape.
- **Side effect:** a package that fails to load now rejects at startup with no handler attached, so it surfaces as an unhandledRejection instead of a synchronous import error. This part is reasoned, not shown.

**2. packages/app-store/vital/lib/reschedule.ts:125-128 and packages/app-store/wipemycalother/lib/reschedule.ts:125-128. Important. The surrounding try/catch is now dead code.**
- **Claim:** `forEach((bookingRef) => …)` became `forEach(async (bookingRef) => …)` inside `try { … } catch (error) { logger.error(...) }`. An async callback never throws synchronously, so the catch can no longer fire.
- **Before:** if `getCalendar` threw (e.g. a CalendarService constructor failing on a bad or undecryptable key), the error was caught and logged.
- **After:** it becomes an unhandled promise rejection from a fire-and-forget callback. That is never logged, and under Node's default `--unhandled-rejections=throw` it can kill the process.
- **Fix:** collect the promises (`map` + `Promise.allSettled`) or use a `for…of` loop with `await` inside the try.
- **Status:** reasoned. I have no failing test, because it needs a calendar credential whose service constructor throws.

**3. packages/trpc/server/routers/viewer/bookings.tsx:553-556. Minor. Same `forEach(async)` pattern.**
- This one has no try/catch, so nothing is lost there.
- A `getCalendar` failure was a synchronous throw that tRPC turned into an error response. It is now an unhandled rejection, and the reschedule continues silently.
- The deleteEvent/deleteMeeting promises were already fire-and-forget before this patch. Reasoned.

**4. packages/core/CalendarManager.ts:28 and 47. Minor. A `Promise` is now stored in the `calendar` field.**
- `getCalendarCredentials` now returns `calendar: Promise<Calendar | null>`, which is consumed by `await item.calendar` in `getConnectedCalendars`.
- It is correct today. The only other consumers are `apps/web/pages/api/availability/calendar.ts:83` and `packages/trpc/server/routers/viewer.tsx:340`, and both pass the value straight to `getConnectedCalendars`.
- Two things about the shape:
  - Every call to `getCalendarCredentials` starts a `getCalendar` call per credential, even for callers that never read `.calendar`.
  - Promises sit in a plain data structure. A future caller who forgets to await gets a truthy Promise, which slips past the `if (!calendar)` check.
- Side benefit: constructor errors are now caught by the try/catch in `getConnectedCalendars`, whereas before they escaped. Reasoned.

## Checked with no issues found
- **`getCalendar.ts`:** the async signature is fine.
- **`getCalendar` callers:** every one is awaited (the `CalendarManager.ts` functions, `EventManager.ts:488`, `handleNewBooking.ts:888`, `handleCancelBooking.ts:243/265/452/461/481`, and the reschedule callers above). A repo-wide grep found no caller left un-awaited.
- **Payment lookups:** `await appStore[...]` in `handlePayment.ts`, `deletePayment.ts`, `handleCancelBooking.ts:589` and `bookings.tsx:967` is correct, and an unknown key resolves to `undefined` as before.
- **`videoClient.ts`:** the async `getVideoAdapters` and its callers are fine. The serial await in the loop costs nothing once the imports have resolved.
- **`getBusyTimes.ts:137`:** this external consumer already awaited `getBusyVideoTimes`.
- **Pre-existing, not caused by this patch:** `handleCancelBooking.ts:458-468` (`forEach(async)` pushing into `apiDeletes` after `await`, which races the later `Promise.all`).

## Skipped files
None. All 12 files in the patch were reviewed.

I did not run tsc or the tests, as instructed. Findings 2 and 3 are reasoned only; finding 1 has the runnable Node repro above.
