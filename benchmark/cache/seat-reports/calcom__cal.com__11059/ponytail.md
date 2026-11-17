Seat: ponytail-review, advisory, over-engineering only. I read the full patch and the surrounding source for every changed function. I ran no builds or tests, and no node_modules are installed. Every claim below is reasoned from the source unless it names a command.

What this change does: it adds a webhook, `/api/webhook/app-credential`, that lets a parent app push encrypted OAuth keys into a user's Cal.com credential. It also adds two helpers under `_utils/oauth/`. `refreshOAuthTokens` sends token refresh to `CALCOM_CREDENTIAL_SYNC_ENDPOINT` when sync is on. `parseRefreshTokenResponse` loosens token validation when sync is on. Ten OAuth integrations are rewired to use them, and the existing OAuth state/credential helpers move into `_utils/oauth/`.

## Findings (over-engineering lane)

1. **packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:5-11 — Important — `minimumTokenResponseSchema` does not do what its comments say.**
   - Claim: The computed keys `[z.string().toString()]` and `[z.string().optional().toString()]` are not patterns. Both turn into the plain string `"[object Object]"`, and the second one overwrites the first. So the real schema is `{ access_token: string, "[object Object]"?: unknown }`. The "any number is the expiry" rule never runs. Zod's default strip mode also drops every other field, so `expires_in`, `expiry_date` and friends are lost when sync is on.
   - Evidence: `node -e 'const s={};const o={[String(s)]:1,[String(s)]:2};console.log(o)'` prints `{ '[object Object]': 2 }`. Zod schemas do not override `toString`.
   - Fix: `z.object({ access_token: z.string() }).passthrough()`. That is one line and replaces lines 5-11.
   - Test: reasoned. Parse `{access_token:"a", expires_in: 3600}` with sync on: `expires_in` is missing from `.data`.

2. **packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:21-29 — Important — the helper both throws on failure and returns a `safeParse` wrapper, which leaves dead branches and confuses callers.**
   - Claim: It throws when `!success`, so `.success` is always true when it returns. The checks that follow are dead code:
     - zoomvideo/lib/VideoApiAdapter.ts:104-106 (`if (!parsedToken.success)`)
     - salesforce/lib/CalendarService.ts:92-94
     - office365calendar/lib/CalendarService.ts:264 (`tokenResponse.success &&`)
   - The patch also deleted Office365's `console.error` that logged why parsing failed. The new throw message has no zod error, so it is now harder to debug.
   - The wrapper shape also causes a real bug in Google: googlecalendar/lib/CalendarService.ts:97 stores `key = { success, data }` into `credential.key`, where it used to store the plain object. The next read of `credential.key` then gets the wrong shape.
   - Fix: return `.data` (that is, `.parse` semantics) and delete the dead checks. This removes about 10 lines and fixes the Google key shape.

3. **packages/app-store/salesforce/lib/CalendarService.ts:39-100 — Important — about 35 lines of hand-written token refresh that the connection never uses and that bypass the new helper.**
   - Claim: `getClient` now POSTs a refresh request, validates the reply with a new `salesforceTokenSchema` and writes it to the DB. This happens on every service construction, not when the token expires.
   - Then it builds the `jsforce.Connection` with the OLD `credentialKey.access_token`, so the fresh token is thrown away. The Connection already gets `clientId`, `clientSecret` and `refreshToken`, and jsforce 1.x refreshes on its own when a call gets a 401.
   - It is also the only integration that does not go through `refreshOAuthTokens`, so the sync endpoint, which is the point of this PR, is never used for Salesforce.
   - Fix: delete lines 39-48 and 75-100 and let jsforce refresh. If sync must cover Salesforce, wrap jsforce's refresh in `refreshOAuthTokens` the way the other integrations do.

4. **apps/web/pages/api/webhook/app-credential.ts:50 — Important — a hand-rolled metadata lookup where `getAppFromSlug` already exists, and the hand-rolled one is wrong.**
   - Claim: `appStoreMetadata` is keyed by directory name, not by slug.
   - Evidence: packages/app-store/apps.metadata.generated.ts:98 has the key `googlecalendar`, while googlecalendar/_metadata.ts:17 has the slug `"google-calendar"`. So for google-calendar, office365-calendar, zoho-bigin and others, `appStoreMetadata["google-calendar"]` is `undefined` and the webhook returns 404.
   - Fix: `getAppFromSlug(app.slug)` from packages/app-store/utils.ts:123 already does this lookup correctly. Swapping it in is one line and fixes the bug.
   - Test: reasoned. POST `appSlug: "google-calendar"` with a valid secret and get 404 "App not found. Ensure that you have the correct app slug".

5. **packages/app-store/_utils/oauth/refreshOAuthTokens.ts:4 and parseRefreshTokenResponse.ts:14 — Minor — the same condition is written out twice.**
   - Claim: Both files test `APP_CREDENTIAL_SHARING_ENABLED && process.env.CALCOM_CREDENTIAL_SYNC_ENDPOINT` separately, and the two must change together.
   - Fix: put one boolean constant in packages/lib/constants.ts next to `APP_CREDENTIAL_SHARING_ENABLED`.
   - Related: `APP_CREDENTIAL_SHARING_ENABLED` (constants.ts:103-104) is `string | undefined`, not a boolean. Wrapping it in `!!(...)` fixes that.

6. **packages/app-store/_utils/oauth/refreshOAuthTokens.ts:13-19 plus all 8 call sites — Minor — redundant code.**
   - `const response = await refreshFunction(); return response;` inside if/else can be `return refreshFunction()`.
   - Every caller passes `async () => await fetch(...)` or `async () => await axios(...)`, where `() => fetch(...)` is enough.
   - The `refreshFunction: () => any` type also throws away the return type, which hides the fetch-vs-axios shape mismatch noted in out-of-lane item (c).

7. **packages/app-store/zoho-bigin/api/add.ts:17 — Minor — unrelated churn that duplicates a constant.**
   - Claim: The patch replaces `appConfig.slug` with the literal `"zoho-bigin"`, but `appConfig.slug` is still used at line 12 of the same file. The diff gains nothing.
   - Fix: revert the line.

8. **packages/app-store/_utils/oauth/createOAuthAppCredential.ts:6 — Minor — a needless path.**
   - The file is already inside `oauth/`, so `"../oauth/decodeOAuthState"` steps out and back in. It should be `"./decodeOAuthState"`.

9. **apps/web/pages/api/webhook/app-credential.ts:16 — Minor — dead code.** An empty `/** */` doc comment. Delete it.

## Outside my lane (stated briefly, not fully verified)

These are not over-engineering findings, but other seats should confirm them.

- a. **salesforce/lib/CalendarService.ts:96 — Critical.** `prisma` is never imported. It only resolves through `globalThis.prisma`, which packages/prisma/index.ts:58-60 sets only when `NODE_ENV !== "production"`. In production this throws a ReferenceError, and every Salesforce client creation fails.
- b. **zoho-bigin/lib/CalendarService.ts:93 — likely Important.** It passes `credentialId` as the `userId` argument to `refreshOAuthTokens`, so the sync endpoint gets a credential id labelled `calcomUserId`.
- c. **Shape mismatch when sync is on (reasoned).** `refreshOAuthTokens` returns a fetch `Response`. Callers that expect the axios or googleapis shape read `.data` and get `undefined`:
  - googlecalendar `res?.data`
  - zohocrm and zoho-bigin `.data.error`
  - hubspot, which uses the result directly as a token
- d. **app-credential.ts:61-62.** The webhook secret is checked with a plain `!==` instead of a constant-time comparison. A missing header plus an unset secret is already blocked by `APP_CREDENTIAL_SHARING_ENABLED`.

Verdict: fix 1-4 first. Lean: about 50 lines can be removed (Salesforce refresh block ~35, dead `.success` branches ~8, schema ~6, wrapper ~4).

## Unreviewed files

None are fully unreviewed. These got only a mechanical check, because they contain no logic and so give nothing to the over-engineering lane:

- .env.example
- turbo.json (env var list)
- the import-path-only edits in:
  - googlecalendar/api/{add,callback}.ts
  - hubspot/api/{add,callback}.ts
  - larkcalendar/api/{add,callback}.ts
  - office365calendar/api/{add,callback}.ts
  - office365video/api/{add,callback}.ts
  - salesforce/api/{add,callback}.ts
  - stripepayment/api/callback.ts
  - tandemvideo/api/callback.ts
  - webex/api/callback.ts
  - zoho-bigin/api/callback.ts
  - zohocrm/api/{_getAdd,callback}.ts
  - zoomvideo/api/{add,callback}.ts
- decodeOAuthState.ts and encodeOAuthState.ts (rename only)

Not checked: jsforce 1.x auto-refresh behaviour was not confirmed against its source, because node_modules is absent. Finding 3 assumes the documented behaviour.
