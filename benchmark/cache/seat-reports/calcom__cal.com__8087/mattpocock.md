## Code review: PR head 820d7fa87e vs base ba9688a04a (branch techdebt/async-app-store-load)

I ran the `mattpocock-skills:code-review` skill and did both axes myself, with no sub-agents. There is no formal spec, so I took the intent from the branch name and the commit message "Async import of the appStore packages". The standards I checked against are `CONTRIBUTING.md` (asks for `yarn build` and `yarn lint` before committing, which I was told not to run), `.eslintrc.js` → `packages/config/eslint-preset.js` (no `no-floating-promises` or `no-misused-promises` rule, so tooling does not catch the async-forEach issue below), and `apps/docs/pages/developer/app-store.mdx`. The repo has no AGENTS.md, CLAUDE.md or .cursorrules.

## Spec

**1. `packages/app-store/vital/lib/reschedule.ts:125` and `packages/app-store/wipemycalother/lib/reschedule.ts:125` (Important)**
- **Claim:** The existing `try { … } catch { logger.error }` around the loop no longer catches anything. The patch changed `bookingRefsFiltered.forEach((bookingRef) => …)` to `forEach(async (bookingRef) => { const calendar = await getCalendar(...) … })`. Errors from `getCalendar` now become unhandled promise rejections instead of being logged.
- **Evidence:** `getCalendar` ends in `new CalendarService(credential)`. The CalDAV-based constructor (`packages/lib/CalendarService.ts:95`) runs `JSON.parse(symmetricDecrypt(credential.key, …))`, which throws on a corrupt or rotated key. Before the patch that throw was synchronous inside the `try` and got logged. Now it escapes the `try`.
- **Failing command** (reproduces the JS behaviour; I did not run the repo code): `node -e 'try{[1].forEach(async()=>{throw new Error("ctor failed")})}catch(e){console.log("caught")}'`. It never prints "caught" and exits with code 1 (unhandled rejection). Under Node's default `--unhandled-rejections=throw` this can take down the server process.

**2. `packages/trpc/server/routers/viewer/bookings.tsx:553` (Important)**
- **Claim:** It is the same `forEach(async …)` change in the `requestReschedule` mutation. Before, a throw from `getCalendar` failed the mutation before emails were sent and the DB was updated. Now the mutation carries on, and the error is a detached unhandled rejection.
- **Evidence:** The same pattern and the same constructor throw path as finding 1. There is no surrounding `try`.
- **Test:** Reasoned, not run. The node one-liner in finding 1 shows the mechanism.
- **Note:** `calendar?.deleteEvent` was already fire-and-forget before the patch. What regressed is only the synchronous `getCalendar` failure path.

**3. `packages/app-store/index.ts:3-30` (Important if the goal was lazy loading, otherwise Minor)**
- **Claim:** The change makes loading async but not lazy. Each `key: import("./x")` in the object literal starts its import as soon as `@calcom/app-store` is evaluated. All 28 app packages still load on the first import of the module, exactly as before. Callers only gain an `await`.
- **Evidence:** JS semantics: property initialisers run when the literal is evaluated. On-demand loading needs thunks (`key: () => import("./x")`) and `await appStore[key]?.()` at each call site.
- **Test:** Reasoned. If the intent behind "async-app-store-load" was to cut cold-start cost or memory, this does not deliver it. If the intent was only to make the API async ahead of a later change, it is consistent with that.

**4. `packages/core/CalendarManager.ts:28` (Minor)**
- **Claim:** `getCalendarCredentials` still calls `getCalendar(credential)` without `await`, so the returned items now carry `calendar: Promise<Calendar | null>`. That changes the type of an exported function's return value.
- **Evidence:** The only consumer that reads `.calendar` is `getConnectedCalendars` (line 48), and it now awaits it inside its `try`. External callers (`apps/web/pages/api/availability/calendar.ts:83`, `packages/trpc/server/routers/viewer.tsx:340` and `:415`) pass the items straight to `getConnectedCalendars`, so nothing breaks today. Any future code that reads `item.calendar` directly gets a Promise, and TS only catches that if it calls a method on it.

**Scope creep: `packages/features/bookings/lib/handleCancelBooking.ts:477-483` (Minor)**
- The old-behaviour branch was rewritten from `forEach` to a sequential `for…of` with `await getCalendar`. This is fine and needed so `apiDeletes` gets filled before it is awaited. Worth noting: `getCalendar` calls now run one after another rather than in parallel. That is negligible because the imports are already in flight.

**Missing:** No tests were added or updated for the changed async contract of `getCalendar` and `getVideoAdapters`.

## Standards

**5. `apps/docs/pages/developer/app-store.mdx:43` and `:56` (Minor)**
- **Claim:** The developer docs still say "Under `packages/app-store/index.ts`, import your app and add it under `appStore`". The file no longer has static imports; the convention is now `appname: import("./appname")`. The patch does not update the docs, so a contributor following them would add a static `import * as x` and a bare `x`. That entry would still work, because `await` on a non-promise is harmless, but it brings back the eager pattern the change removes.
- **Evidence:** I grepped the docs for `packages/app-store/index.ts`.

**6. CONTRIBUTING.md "Please be sure that you can make a full production build" and "yarn lint" (advisory, not verified)**
- I could not check this, because building and linting were out of scope. The type-level changes, such as `await appStore[...]` on a union of module-namespace promises and narrowing with `"lib" in calendarApp`, look type-correct when read, but have not been checked by the compiler.

**Smell baseline (judgement call):**
- Possible Duplicated Code: the `paymentApp = await appStore[dirName]; if (!("lib" in …"PaymentService"…))` block appears in `handleCancelBooking.ts:589`, `bookings.tsx:967`, `deletePayment.ts:16` and `handlePayment.ts:26`. It predates this PR, which only touches each copy. That is Shotgun Surgery in effect: one contract change needed 12 files.

## Summary
- **Spec:** 4 findings plus 1 scope note. The worst is the `forEach(async)` change in the vital and wipemycalother reschedule files and in `bookings.tsx`, which turns synchronous `getCalendar` errors into unhandled rejections.
- **Standards:** 2 findings plus 1 smell. The worst is the out-of-date app-store developer docs.

## Files not reviewed
None. I reviewed all 12 files in the patch. I did not run builds, lint or tests, as instructed.

I did not check whether the Next.js or webpack server bundle actually splits these `import()` calls into separate chunks. Findings 1 and 2 are the real runtime risk.
