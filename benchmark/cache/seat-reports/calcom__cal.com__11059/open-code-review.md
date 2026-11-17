Correctness review of calcom PR 11059 (bc89fe00ea..9fde0e9068), run through `open-code-review:delegate-review` in range mode. OCR listed 40 files, 39 of them reviewable. Report only: I edited nothing. node_modules is not installed and I ran no builds or tests, so every claim below is reasoned from the code and none was confirmed by a failing run.

Summary: Google Calendar (on any instance) and Salesforce (in production) break even with the new feature off. With sync turned on, most of the converted integrations break.

## Findings

**1. packages/app-store/googlecalendar/lib/CalendarService.ts:97 — Critical**
- **Claim:** Every Google Calendar credential is corrupted on its first token refresh, even with credential sync off.
- **Evidence:**
  - Before the patch, `key = googleCredentialSchema.parse(...)` returned the credential object. Now `parseRefreshTokenResponse` returns the whole `safeParse` result (`_utils/oauth/parseRefreshTokenResponse.ts:29` `return refreshTokenResponse`).
  - So `prisma.credential.update({ data: { key } })` stores `{ success: true, data: {...} }`.
  - The next `new GoogleCalendarService(credential)` runs `googleCredentialSchema.parse(credential.key)` in its constructor (line 75). That throws a ZodError because `scope`, `token_type` and the other fields are no longer at the top level.
  - Result: every Google calendar call fails after roughly an hour, and the only fix is reinstalling.
- **Fix:** store `.data`.

**2. packages/app-store/salesforce/lib/CalendarService.ts:96 — Critical**
- **Claim:** `prisma` is used but never imported, so `getClient` throws `ReferenceError: prisma is not defined` in production. Every Salesforce operation then fails, because the rejected `this.conn` is awaited by every method.
- **Evidence:**
  - `grep -n prisma packages/app-store/salesforce/lib/CalendarService.ts` finds only line 96 and no import.
  - Type-checking still passes because of `declare global { var prisma }` in `packages/prisma/index.ts`.
  - But `globalThis.prisma` is assigned only when `NODE_ENV !== "production"`, so the code works in dev and crashes in prod.

**3. packages/app-store/salesforce/lib/CalendarService.ts:73-99 — Important**
- **Claim:** `getClient` now does an unconditional token refresh against login.salesforce.com every time the service is constructed (every booking), whether or not the token has expired.
- **Problems:**
  - The fresh token is written to the DB, but jsforce is still given the stale `credentialKey.access_token` (line 104).
  - The refresh bypasses `refreshOAuthTokens`, so it ignores sync mode.
  - In sync mode, `parseRefreshTokenResponse` swaps in the minimal schema, which strips `instance_url`, `id` and the other fields. The stored key then loses `instance_url`, so the next connection has `instanceUrl: undefined`.
  - The `!accessTokenParsed.success` branch (line 91) is dead code, because `parseRefreshTokenResponse` already throws on failure.
  - `response.statusText !== "OK"` (line 86) is a fragile success check. `!response.ok` is the right test, since HTTP/2 responses have an empty statusText.

**4. packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:8,10 — Critical (sync mode)**
- **Claim:** `minimumTokenResponseSchema` does not do what its comments say.
- **Evidence:**
  - `[z.string().toString()]` is a computed key, and it evaluates to the literal string `"[object Object]"` because ZodType does not override `toString`. Line 10 produces the same key and overwrites line 8.
  - So the schema is effectively `{ access_token: string, "[object Object]"?: unknown }`.
  - `z.object` strips unknown keys, so in sync mode the parsed data contains only `access_token` plus a fake `refresh_token`. No expiry field survives.
- **Effects downstream:**
  - **Zoom (`VideoApiAdapter.ts:116-118`):** `expiry_date = Math.round(Date.now() + undefined*1000)` gives NaN, and `refresh_token` becomes the literal `"refresh_token"`. The next `zoomTokenSchema.parse` fails.
  - **Office365 calendar:** `expires_in` keeps its stale value, so it refreshes on every call.
- **Reproducing the key collapse (no deps needed):** `node -e 'class Z{}; const o={[new Z().toString()]:1,[new Z().toString()]:2}; console.log(Object.keys(o))'` prints `['[object Object]']`. Zod is not installed, so I could not run the schema itself.

**5. packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:25-27 — Important**
- **Claim:** When a response has no `refresh_token`, the code writes the literal string `"refresh_token"` into the parsed data, and callers then persist it over the real token.
- **Evidence:**
  - Office365 calendar (`CalendarService.ts:264`) spreads `tokenResponse.data` over `o365AuthCredentials`, and `refreshTokenResponseSchema` declares `refresh_token` optional.
  - Whenever Microsoft omits it, and always in sync mode per finding 4, the stored refresh_token becomes `"refresh_token"`. Later refreshes then fail permanently with invalid_grant.
  - Zoom (line 117) copies `newTokens.refresh_token` into the key the same way in sync mode.

**6. packages/app-store/_utils/oauth/refreshOAuthTokens.ts:8-15 — Important**
- **Claim:** In sync mode the function always returns a raw fetch `Response`. Several callers expect something else from their `refreshFunction`, so sync mode crashes them or corrupts their data.
- **Affected callers:**
  - **Google (`CalendarService.ts:94`):** `res?.data` is undefined, so `token.access_token` throws a TypeError.
  - **HubSpot (`hubspot/lib/CalendarService.ts:177-198`):** the `Response` is treated as a `HubspotToken`. `expiresIn` is undefined, so `expiryDate` becomes NaN, and the `Response` object itself is written as `key`, destroying the credential.
  - **Zoho CRM (`zohocrm/lib/CalendarService.ts:217`) and Zoho Bigin (`zoho-bigin/lib/CalendarService.ts:96`):** `tokenInfo.data.error` throws a TypeError on undefined.
- **Two more problems:**
  - Nothing checks `response.ok`.
  - The comment says the endpoint should return "only the access token and expiry date", but Lark (`handleLarkError` needs `{code:0, data}`), Zoom and Webex parse provider-specific response shapes. The sync contract is inconsistent from one integration to the next.

**7. packages/app-store/zoho-bigin/lib/CalendarService.ts:93 — Important**
- **Claim:** `credentialId` is passed where `refreshOAuthTokens` expects `userId`.
- **Effect:** The sync endpoint receives a credential id as `calcomUserId` and returns tokens for the wrong user, or none. The `userId` truthiness guard is also bypassed, so team credentials go through sync too.

**8. packages/app-store/zoomvideo/lib/VideoApiAdapter.ts:92 — Important**
- **Claim:** The app slug sent to the sync endpoint is `"zoomvideo"`, but the app's real slug is `"zoom"` (`zoomvideo/_metadata.ts`).
- **Effect:** The inbound webhook (`app-credential.ts`) resolves apps by `prisma.app.slug`, so it accepts `"zoom"` only. Outbound and inbound requests use different identifiers for the same app.

**9. packages/app-store/_utils/oauth/refreshOAuthTokens.ts:8-14 — Important (security, reasoned)**
- **Claim:** The outbound sync request sends no authentication: no secret header and no signature, only `calcomUserId` and `appSlug`.
- **Effect:** As shipped, the parent application cannot verify that the caller is Cal.com. Anyone who can reach that endpoint can ask for live OAuth access tokens for any user id. The webhook secret already exists and could be sent as a header, but it is not.

**10. apps/web/pages/api/webhook/app-credential.ts:25 — Minor**
- **Claim:** The secret is compared with `!==`, which is not constant-time, so it is theoretically open to a timing attack. `crypto.timingSafeEqual` is the standard fix.

**11. apps/web/pages/api/webhook/app-credential.ts:31, 57 — Minor**
- **Claim:** `schema.parse(req.body)`, `JSON.parse(...)` and `symmetricDecrypt` (which throws on a bad key or IV) are not wrapped in error handling.
- **Effect:** Bad input returns a 500 with a stack trace instead of a 400. There is also no HTTP method restriction and no shape validation of the decrypted keys before they are written to `credential.key`.

**12. packages/app-store/office365calendar/lib/CalendarService.ts:264 — Minor**
- **Claim:** `tokenResponse.success &&` can no longer be false, because the parser now throws instead.
- **Behaviour change:** A schema mismatch used to be logged with the MS response and processing continued. Now it throws a generic error, and the diagnostic log was deleted.

## Unreviewed files

None. All 40 files in the patch were reviewed. OCR's preview excluded `.env.example` as an unsupported extension, but I read its diff in the patch file and found no correctness issues.

I did not check whether other code outside this diff still imports the old `_utils/{decode,encode}OAuthState` and `_utils/createOAuthAppCredential` paths. A grep at head found none left over.
