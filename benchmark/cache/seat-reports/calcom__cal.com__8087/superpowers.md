## Review of calcom__cal.com__8087 (base ba9688a04a, head 820d7fa87e)

I followed the `superpowers:requesting-code-review` skill but did the review myself instead of dispatching a subagent, as you instructed. There was no spec, so I took the intent from the branch name (`techdebt/async-app-store-load`) and commit "Async import of the appStore packages": app-store packages should load lazily. I did not install dependencies, run tsc or run tests. I wrote nothing in the repo; the two repro scripts below are in the scratchpad.

Overall: every caller of `appStore[...]` and `getCalendar` that I grepped was migrated to `await`. Those were `getCalendar.ts`, `videoClient.ts`, `CalendarManager.ts`, `EventManager.ts`, `handleCancelBooking.ts`, `handleNewBooking.ts`, `deletePayment.ts`, `handlePayment.ts`, `bookings.tsx` and the vital and wipemycalother reschedule files. The only consumer of `getCalendarCredentials().calendar` is `getConnectedCalendars`, and it now awaits the value correctly. The main problem is that the change does not make anything lazy.

### Findings

**1. packages/app-store/index.ts:1-33 — Important (spec gap). The imports are async but not lazy: all 28 app packages still load as soon as `@calcom/app-store` is imported.**
- **Claim:** Each `import("./x")` in the object literal runs when `index.ts` is evaluated, so every package starts loading on first import no matter which key is used. Cold-start and memory cost stay about the same as the old static imports. The only effect is that every caller now has to await.
- **Evidence:** This follows from the language rules (property values in an object literal are evaluated when the literal is), and I reproduced it. Script `idx.mjs` = `const s={a:import("./a.mjs")}; export default s;` and `a.mjs` logs "app module evaluated". Running `node -e 'import("./idx.mjs").then(()=>setTimeout(()=>console.log("index loaded; no key accessed"),10))'` prints "app module evaluated" without any key being accessed. Scripts are in `/tmp/claude-1000/-home-jsg--t3-scratch-2026-11-12-find-a-benchmark-for-code-61e02dff-converge-bench-work-calcom--cal-com--8087/b9bf5a2f-5ee7-4eea-9c61-743526225fb8/scratchpad/`.
- **Implied fix:** Store thunks instead, e.g. `applecalendar: () => import("./applecalendar")`, and call them at the lookup sites.

**2. packages/app-store/index.ts:1-33 — Minor. If one app module fails to load, the result is now an unhandled promise rejection.**
- **Claim:** If any app package throws while loading, its `import()` promise rejects with no handler attached until some request happens to await that key. Node's default `--unhandled-rejections=throw` then kills the process. Before the patch, the same failure surfaced as an ordinary import error that the importer could catch.
- **Evidence:** Repro `idx2.mjs` = `{bad:import("./bad.mjs")}`, where `bad.mjs` throws. `node -e 'import("./idx2.mjs").then(()=>setTimeout(...))'` exits with code 1 and never prints "still alive". Whether Next.js installs its own `unhandledRejection` handler here is reasoned, not verified.

**3. packages/app-store/vital/lib/reschedule.ts:125, packages/app-store/wipemycalother/lib/reschedule.ts:125, packages/trpc/server/routers/viewer/bookings.tsx:553 — Minor. `forEach(async ...)` lets errors escape and starts deletions late.**
- **Claim:** The patch turns these callbacks into `forEach(async ...)`. Errors from `getCalendar` (such as a `CalendarService` constructor throwing) now escape the surrounding `try/catch` (reschedule.ts:124) as unhandled rejections. Calendar deletion also no longer starts synchronously before the function moves on to emails, webhooks and the response.
- **Evidence:** In the old code `deleteEvent` was not awaited either, so this is a small regression, not a new class of bug. Reasoned. A `for...of` loop with `await`, or `Promise.all(map(...))`, would match what `handleCancelBooking.ts:477-483` already does in this same patch.

**4. packages/core/CalendarManager.ts:28 — Minor. `getCalendar` promises are created and never awaited.**
- **Claim:** `getCalendarCredentials` calls `getCalendar` for every credential, including those where `app.variant !== "calendar"`, whose result is thrown away. Those promises are now never awaited, so any rejection from them becomes unhandled.
- **Evidence:** Lines 27-29. Calling `getCalendar` for discarded credentials predates the patch, but it used to throw synchronously into the caller. Reasoned.

Not in the findings, for context:
- `handleCancelBooking.ts:458-469` still uses `forEach(async ...)` and pushes into `apiDeletes` after an `await`, so those deletes are never awaited. That bug predates the patch; the patch only adds an `await getCalendar` inside it.
- There are no tests for any of these paths, before or after the patch.

### Files skipped
None. I reviewed all 12 files in the patch.

Not checked:
- `apps/api` is not part of this checkout (likely a submodule), so I could not verify whether it calls `getCalendar` or `appStore[...]` synchronously. Any such caller would break silently, because it would get a Promise where it expects a Calendar or module.
- Type-check was not run, so TypeScript narrowing on the awaited module unions is unverified.
