## Review of calcom PR 8087 (techdebt/async-app-store-load): over-engineering pass

**What this change does:** `packages/app-store/index.ts` stops importing the 28 app packages statically. Each value in the `appStore` map becomes `import("./x")`, which is a Promise. The rest of the diff is fallout from that: `getCalendar`, `getVideoAdapters`, `deleteEvent` and `deleteMeeting` become async, and about 20 call sites get an `await` added.

Assumed load: a multi-user Next.js server. The intent comes from the branch name only, since there was no spec.

### Must fix

1. **Important: the imports are not lazy, so the whole PR misses its own goal** (`packages/app-store/index.ts:1-31`)
   - **What this is:** The map is meant to load app packages only when they are needed.
   - **Problem:** `import("./x")` written as an object property runs when the object is built. That happens when `index.ts` is first imported. So all 28 packages still load on first touch, exactly as before. The only thing that changes is that every lookup now returns a Promise, and that is what forced the async changes in 11 other files. Evidence: I ran a 3-file Node script with `const store = { a: import("./a.mjs"), b: import("./b.mjs") }` and read only `store.a`. It printed `a loaded` and then `b loaded`, so both modules loaded. The script is at `/tmp/claude-1000/-home-jsg--t3-scratch-2026-11-12-find-a-benchmark-for-code-61e02dff-converge-bench-work-calcom--cal-com--8087/b9bf5a2f-5ee7-4eea-9c61-743526225fb8/scratchpad/eager/main.mjs`. Run it with `node main.mjs`.
   - **Fix:** Make each entry a function: `applecalendar: () => import("./applecalendar")`. Each call site then changes from `await appStore[k]` to `await appStore[k]?.()`. The `?.` is needed because the payment paths can pass an undefined key: `paymentAppCredential?.app?.dirName` can be undefined. The call sites the PR already touched are the right ones. The other fix is to revert, if laziness is not actually wanted.
   - **If we skip it:** 20+ lines of async churn ship and the cold-load cost stays the same.

### Should fix

2. **Important (reasoned): `forEach(async …)` inside `try/catch` no longer catches errors** (`packages/app-store/vital/lib/reschedule.ts:124-139`, `packages/app-store/wipemycalother/lib/reschedule.ts:124-139`, `packages/trpc/server/routers/viewer/bookings.tsx:553`)
   - **What this is:** These loops delete calendar and video events for a booking that is being rescheduled.
   - **Problem:** Before, an error thrown while `getCalendar` set up the calendar (for example a bad credential key) was caught by the surrounding `try`. Now the error happens inside an async callback whose Promise nobody waits for, so it becomes an unhandled rejection that skips the `catch` and its log line. The returned `deleteEvent` Promise was already dropped before this change.
   - **Fix:** `await Promise.all(bookingRefsFiltered.map(async (bookingRef) => { ... }))`. This is the same number of lines and puts the errors back inside the `try`.
   - **If we skip it:** Silent unhandled rejections in the reschedule paths. Depending on how Node is configured, the process can crash.

### Nice to have

3. **Minor: dead comment with a wrong path** (`packages/app-store/index.ts:2`)
   - `// example: import("./example")` points to `./example`, but the folder is `_example` (the old comment said `./_example`). It is dead code either way. Delete it.

4. **Minor: noise in the diff** (`packages/app-store/index.ts:30`, `packages/core/CalendarManager.ts:31`)
   - `sylapsvideo` moved to the end of the map for no reason. A stray blank line was added in `getCalendarCredentials`. Neither changes behavior. Drop both to keep the diff to its real content.

5. **Minor: a Promise stored in a field that reads like a value** (`packages/core/CalendarManager.ts:28`)
   - `getCalendarCredentials` now puts a `Promise<Calendar|null>` into the `calendar` field. The only reader is `getConnectedCalendars`, which awaits it, and the three outside callers (`apps/web/pages/api/availability/calendar.ts:83`, `packages/trpc/server/routers/viewer.tsx:340,415`) only pass the list through, so this is correct. It is still an odd shape. If finding 1 is fixed with thunks, the field could hold the thunk, or `getConnectedCalendars` could call `getCalendar(credential)` itself and the field could go away.

I checked that every caller of `getCalendar`, `getVideoAdapters` and `appStore[...]` was updated. A grep across apps/ and packages/ found none missed. The `reduce` to `for` rewrite in `videoClient.ts` and the `forEach` to `for` rewrite in `handleCancelBooking.ts:477-483` are as small as an awaited loop can be, so I raised no finding on them.

Verdict: fix 1 first. Either make the imports real thunks or drop the PR, because as written it adds async churn with no laziness. Then fix 2.
Lean: about -25 lines possible if the PR is reverted instead of fixed. If it is fixed, the line count stays about the same but the change finally does what its name says.

### Skipped files
None. I reviewed all 12 files in the patch.

Not checked: whether Next.js/webpack bundling changes when the module runs (for example chunk splitting). I did not run a build or tests, as instructed. The Node demo shows the eager behavior, and webpack runs `import()` calls in an object literal the same way.
