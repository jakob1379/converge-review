## Code review: base bc89fe00ea to head 9fde0e9068 (app credential sync)

Method: I ran the `mattpocock-skills:code-review` skill and did both axes myself, with no sub-agents. I did not run any build, typecheck or test. The one thing I executed was a zod check, `<bench>/work/calcom__cal.com__11059.scratch/zt/check.js`. It ran against a cached zod 3.25.76; the repo pins 3.21.4/3.22.2, which behave the same way here.

## Spec axis

No spec was provided, and the commits reference no issue. Nothing could be checked for spec compliance. The findings below measure the code against the intent in the commit messages: "Add webhook to send app credentials", "Upsert credentials when webhook called", "Refresh oauth token from a specific endpoint", "Add credential encryption", "Create parse token response wrapper".

### Critical

1. **packages/app-store/googlecalendar/lib/CalendarService.ts:97**
   - **Claim:** every successful Google token refresh writes a corrupted credential to the database, whether or not sync is on.
   - **Evidence:**
     - `parseRefreshTokenResponse` returns zod's whole `safeParse` result (`_utils/oauth/parseRefreshTokenResponse.ts:29`).
     - Google stores it directly: `const key = parseRefreshTokenResponse(...)`, then `data: { key }`. The stored key becomes `{success:true, data:{...}}`.
     - The next time the service is built, line 75 runs `googleCredentialSchema.parse(credential.key)`, which throws. Google Calendar then fails for every user after their first refresh.
     - Other callers unwrap the result correctly: zoom at VideoApiAdapter.ts:111, salesforce at :98, office365 at :264.
   - **Check:** `node .../zt/check.js <zod>` prints `returned shape keys: [ 'success', 'data' ]`. `grep -n "parseRefreshTokenResponse(googleCredentials" packages/app-store/googlecalendar/lib/CalendarService.ts` finds the line that stores it unwrapped.

2. **packages/app-store/salesforce/lib/CalendarService.ts:96**
   - **Claim:** `prisma` is used but never imported, so Salesforce breaks in production.
   - **Evidence:**
     - It compiles only because `packages/prisma/index.ts:6-9` declares a global `var prisma`.
     - That global is assigned only when `NODE_ENV !== "production"` (index.ts:58-59).
     - In production, `getClient` throws a ReferenceError on every construction, so `this.conn` rejects and every Salesforce operation fails.
   - **Check:** `grep -c "import prisma" packages/app-store/salesforce/lib/CalendarService.ts` returns 0.

### Important

3. **packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:5-11**
   - **Claim:** the "minimum" schema used in sync mode does not do what its comments say. It removes every field except `access_token`.
   - **Evidence:**
     - `z.string().toString()` and `z.string().optional().toString()` both evaluate to `"[object Object]"`. The two computed keys collide, and neither works as a catch-all.
     - `z.object` strips unknown keys. My check printed `{"success":true,"data":{"access_token":"a"}}` for an input that also had `expiry_date` and `refresh_token`.
   - **Consequences in sync mode:**
     - The expiry is lost. office365 gets no `expires_in`; zoom gets `expires_in` undefined, so `expiry_date` becomes NaN at VideoApiAdapter.ts:122.
     - Tokens are seen as expired, so a refresh is triggered on every call.
   - **Check:** `zt/check.js`, reasoned for the downstream effects.

4. **packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:25-27**
   - **Claim:** a missing `refresh_token` is replaced with the literal string `"refresh_token"`, in both modes.
   - **Evidence:**
     - office365's `refreshTokenResponseSchema` makes `refresh_token` optional (office365calendar CalendarService.ts:56).
     - When Microsoft omits it, line 264 spreads `data` over the stored credentials. The real refresh token is overwritten with `"refresh_token"`, and the credential cannot refresh again. Before this change the key was simply absent, so the stored token survived.
   - **Check:** reasoned.

5. **packages/app-store/_utils/oauth/refreshOAuthTokens.ts:8-15**
   - **Claim:** in sync mode this returns a fetch `Response`, but several callers expect the provider SDK's or axios's return shape. Sync refresh is broken for those apps.
   - **Evidence:**
     - Google, CalendarService.ts:94: `res?.data` is undefined, so `token.access_token` throws a TypeError.
     - hubspot, CalendarService.ts:177-192: treats the `Response` as a `HubspotToken`. `expiresIn` is undefined, so `expiryDate` becomes NaN, and the `Response` object is persisted as the key at :198.
     - zoho-bigin, CalendarService.ts:96, and zohocrm, CalendarService.ts:217: `.data.error` on a `Response` throws a TypeError.
     - Only the fetch-based adapters (lark, office365 calendar/video, webex, zoom) get a compatible shape.
   - **Check:** reasoned.

6. **packages/app-store/zoho-bigin/lib/CalendarService.ts:93**
   - **Claim:** the credential id is passed where `refreshOAuthTokens` expects a userId. In sync mode, the external endpoint gets `calcomUserId=<credential.id>` and returns tokens for the wrong user, or for none.
   - **Evidence:** the signature at refreshOAuthTokens.ts:3 is `(refreshFunction, appSlug, userId)`. bigin passes `credentialId` (line 53 is `credential.id`). Every other app passes `credential.userId`.
   - **Check:** reasoned; see `grep -n "credentialId$" packages/app-store/zoho-bigin/lib/CalendarService.ts`.

7. **packages/app-store/zoomvideo/lib/VideoApiAdapter.ts:92**
   - **Claim:** the slug sent to the sync endpoint is `"zoomvideo"`, but the app's slug is `"zoom"` (`zoomvideo/_metadata.ts:16`).
   - **Evidence:** the webhook keys credentials by `appMetadata.slug` (app-credential.ts:63-65, 87-88). The two halves of the sync protocol therefore disagree on how to name Zoom. The other hard-coded slugs (google-calendar, hubspot, lark-calendar, office365-calendar, msteams, webex, zoho-bigin, zohocrm) match their config.
   - **Check:** `grep -n slug packages/app-store/zoomvideo/_metadata.ts` returns `slug: "zoom"`.

8. **packages/app-store/salesforce/lib/CalendarService.ts:75-110**
   - **Claim:** this contradicts the sync intent.
   - **Evidence:**
     - Salesforce now makes a direct refresh request on every `getClient()`. It does not go through `refreshOAuthTokens`, so it never calls the sync endpoint.
     - In sync mode it is still parsed with the stripping minimum schema (finding 3).
     - The new token is saved, but the connection at :106 is still built from the stale `credentialKey.access_token`.
     - `parseRefreshTokenResponse` already throws on failure, so the `!accessTokenParsed.success` branch at :92 can never run.
   - **Check:** reasoned.

### Minor

9. **apps/web/pages/api/webhook/app-credential.ts:31 and :57**
   - **Claim:** bad input to the webhook returns an unhandled 500 instead of a 4xx.
   - **Evidence:** `schema.parse(req.body)` and `JSON.parse(symmetricDecrypt(...))` throw on a malformed body, a bad ciphertext or a wrong key. A commit titled "Change to safe parse" exists, but this endpoint still uses `.parse`.

10. **apps/web/pages/api/webhook/app-credential.ts:24-27**
    - **Claim:** the endpoint does not check the HTTP method, and it compares the secret with `!==` rather than a constant-time comparison.
    - **Evidence:** reasoned. It is a credential-write endpoint, so this is a hardening gap.

11. **packages/app-store/_utils/oauth/refreshOAuthTokens.ts:8**
    - **Claim:** Cal.com sends no secret or authentication to `CALCOM_CREDENTIAL_SYNC_ENDPOINT`, so the parent app cannot verify the caller before handing out tokens.
    - **Evidence:** reasoned. This only matters if the intent is a two-way authenticated sync.

12. **packages/lib/constants.ts:103-104**
    - **Claim:** `APP_CREDENTIAL_SHARING_ENABLED` evaluates to `string | undefined`, not a boolean.
    - **Evidence:** it works when used for truthiness, but the name implies a boolean.

13. **packages/app-store/zoho-bigin/api/add.ts:17**
    - **Claim:** this is a change outside the feature's scope.
    - **Evidence:** `appConfig.slug` was replaced with the hard-coded string `"zoho-bigin"`. The value is identical, but the next line still uses `appConfig`, so the swap only adds drift risk.

## Standards axis

These are the only documented-standard issues I found, and none are hard violations.

- **Minor:** `packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:13` and `refreshOAuthTokens.ts:3` add `any` (`response: any`, `() => any`). The `plugin:@typescript-eslint/recommended` ruleset in `packages/config/eslint-preset.js` warns on this, and lint tooling already enforces it, so it is noted only.
- **packages/app-store/CONTRIBUTING.md, "Others" #4:** says "no env variables should be added by an app". I judged this not breached. The four new `CALCOM_*` variables are platform-level and live in `packages/lib/constants.ts` and `_utils`, not inside an individual app. They are registered in `turbo.json` `globalEnv` and documented in `.env.example`.
- I found no `consistent-type-imports` or `unused-imports` violations in the patch. The new imports, including salesforce's `z` and the moved oauth helpers, are all used.

## Files not reviewed

None were skipped. I reviewed all 40 files in the patch. The import-only path updates were checked mechanically:
- the `add.ts` and `callback.ts` files of googlecalendar, hubspot, larkcalendar, office365calendar, office365video, salesforce, zoho-bigin, zohocrm and zoomvideo
- the callbacks of stripepayment, tandemvideo and webex
- the three renamed `_utils/oauth/*` files

## Standards sources found

- `<bench>/work/calcom__cal.com__11059/CONTRIBUTING.md` (setup, build, lint and PR process only)
- `<bench>/work/calcom__cal.com__11059/packages/app-store/CONTRIBUTING.md`
- `<bench>/work/calcom__cal.com__11059/.eslintrc.js`, which points to `packages/config/eslint-preset.js`

There is no AGENTS.md, CLAUDE.md or `.cursor` rules file in the repo.

## Summary

- **Spec axis:** 13 findings measured against inferred intent. Worst: Google refresh stores the `safeParse` wrapper as the credential key, breaking Google Calendar for all users after the first refresh.
- **Standards axis:** 1 minor, tooling-enforced finding. Worst: `any` in the new oauth helpers.

The type-level claims are reasoned from source, since nothing was compiled; a typecheck would be needed to confirm them.
