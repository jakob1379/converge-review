I loaded superpowers:requesting-code-review and did the review myself, without spawning a reviewer, as instructed. There was no spec, so I judged the patch against what the change is plainly for: a webhook that pushes app credentials into Cal.com, plus a "sync endpoint" mode for refreshing OAuth tokens. I ran no project builds or tests. The one repro is `<bench>/work/calcom__cal.com__11059.scratch/repro.cjs`, run with `NODE_PATH=/tmp/jobnet.J5gF/node_modules node repro.cjs`. It borrows a zod 4.6.7 install found under `/tmp` (the repo has no `node_modules`), while the repo pins zod ^3.22. `safeParse` and `toString` behave the same way in both on these points, but I didn't run it against 3.22 itself.

## Findings

1. **`packages/app-store/googlecalendar/lib/CalendarService.ts:97` — Critical.** Google credentials get corrupted on the first token refresh in the default (non-sync) mode.
   - Claim: `const key = parseRefreshTokenResponse(googleCredentials, googleCredentialSchema)` returns the whole `safeParse` result, not the parsed data. Before the patch this was `googleCredentialSchema.parse(...)`, which returned the data. So the database stores `{success:true,data:{...}}`. The next `GoogleCalendarService` constructor calls `googleCredentialSchema.parse(credential.key)` (line 75), and that throws a ZodError.
   - Result: the user's Google Calendar breaks after an ordinary token expiry, whether or not sync is configured.
   - Evidence: the repro prints `google key written to DB: {"success":true,"data":{...}}` and then `next GoogleCalendarService constructor parse throws: ZodError`.

2. **`packages/app-store/salesforce/lib/CalendarService.ts:96` — Critical.** Salesforce is broken in production.
   - Claim: the new `prisma.credential.update(...)` uses `prisma`, but the file never imports it. It type-checks only because `packages/prisma/index.ts:6-9` declares `var prisma` globally. At runtime, `globalThis.prisma` is set only when `NODE_ENV !== "production"` (`packages/prisma/index.ts:58-60`).
   - Result: in production every `getClient` fails with a ReferenceError or TypeError, so `this.conn` rejects and every Salesforce operation fails.
   - Evidence: the import list at lines 1-20 has no prisma import. Reasoned; not executed.

3. **`packages/app-store/salesforce/lib/CalendarService.ts:75-107` — Important.** Even once prisma is imported, the Salesforce refresh is wrong in several ways:
   - It sends a refresh-token request to Salesforce every time the service is constructed (every booking), whether or not the token has expired.
   - The refreshed token is written to the database, but the connection is still built with the stale `credentialKey.access_token` at line 104.
   - It bypasses `refreshOAuthTokens`, so in sync mode it still calls Salesforce directly. The response is then validated against the sync-mode minimal schema, which strips most fields.
   - `response.statusText !== "OK"` is fragile: statusText can be empty, for example over HTTP/2. `response.ok` is the reliable check.
   - The URL is hard-coded to `login.salesforce.com`, so sandbox orgs get a 400.
   - Evidence: reasoned from the code.

4. **`packages/app-store/_utils/oauth/refreshOAuthTokens.ts:8-15` — Critical (sync mode).** In sync mode the helper returns a raw fetch `Response`, but four callers expect a different shape:
   - Google, `CalendarService.ts:94`: `res?.data` is undefined, so `token.access_token` throws a TypeError. The catch swallows it (the message is not `invalid_grant`) and returns the stale token.
   - HubSpot, `CalendarService.ts:192`: the `Response` object is treated as a HubspotToken. `expiresIn` is undefined, and the `Response` gets written as the credential key.
   - Zoho CRM, `CalendarService.ts:217`, and Zoho Bigin, `CalendarService.ts:96`: `tokenInfo.data.error` throws a TypeError.
   - Result: credential sync can't work for these four integrations.
   - Evidence: reasoned. The fetch `Response` type has no `.data`. The original callers returned an axios, gaxios or SDK object.

5. **`packages/app-store/_utils/oauth/refreshOAuthTokens.ts:8-14` — Important (security/design).** The POST to the sync endpoint has no authentication: no shared secret header, no signature. It also never checks `response.ok`.
   - Result: the parent app can't tell Cal.com apart from anyone else asking for user X's tokens. An error response from the endpoint gets parsed as if it were tokens.
   - Evidence: reasoned from the code.

6. **`packages/app-store/zoho-bigin/lib/CalendarService.ts:93` — Important.** The code passes `credentialId` where `refreshOAuthTokens` expects a userId.
   - Result: in sync mode the endpoint receives `calcomUserId=<credential id>` and returns tokens for whichever user happens to have that id. It is a cross-user mix-up, hidden for now only because of the crash in finding 4.
   - Evidence: the signature is `refreshOAuthTokens(fn, appSlug, userId)`, and every other caller passes `credential.userId`.

7. **`packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:5-11` — Important.** The sync-mode schema is broken.
   - Claim: `[z.string().toString()]` and `[z.string().optional().toString()]` both evaluate to the literal key `"[object Object]"`. The schema is therefore just `{access_token, "[object Object]"?}`, and since zod strips unknown keys, every expiry field is dropped.
   - Downstream effects in sync mode:
     - Zoom (`VideoApiAdapter.ts:122`): `newTokens.expires_in` is undefined, so `expiry_date` becomes NaN and is stored as null. The next `zoomTokenSchema.parse` fails for good ("Zoom credential keys parsing error").
     - Office 365 calendar: `expires_in` is never updated, so the token always looks expired and the sync endpoint is called on every Graph request.
   - Evidence: the repro prints `computed keys: "[object Object]" "[object Object]"` and `sync-mode parse: {"success":true,"data":{"access_token":"a"}}` for an input that included `expires_in`, `expiry_date` and `refresh_token`.

8. **`packages/app-store/_utils/oauth/parseRefreshTokenResponse.ts:25-27` — Important.** When a response has no `refresh_token`, the helper sets it to the literal string `"refresh_token"`.
   - Office 365 calendar (line 263-264) spreads this into the stored credential and overwrites the real refresh token. Its own schema marks `refresh_token` as optional, so this can happen in the default mode too. Before the patch, a missing refresh_token left the stored one alone.
   - Zoom in sync mode (line 121) stores `"refresh_token"` the same way.
   - Result: the next real refresh fails with invalid_grant, and the credential is effectively dead, including after sync is turned off.
   - Evidence: reasoned from the code plus the repro output.

9. **`packages/app-store/office365calendar/lib/CalendarService.ts:263` — Minor.** This is a behaviour change. A failed parse used to be logged and the code carried on. Now `parseRefreshTokenResponse` throws, and the Microsoft response is no longer logged. The `tokenResponse.success &&` guard on line 264 can never be false, so it is dead code.

10. **`apps/web/pages/api/webhook/app-credential.ts:50` — Important.** The webhook rejects most apps it is supposed to serve.
    - Claim: it looks up `appStoreMetadata[app.slug]`, but `appStoreMetadata` is keyed by directory name, not slug (`apps.metadata.generated.ts:98,109,110,146`: `googlecalendar`, `office365calendar`, `office365video`, `zoomvideo`).
    - Result: the slugs `google-calendar`, `office365-calendar`, `msteams`, `zoom` and `lark-calendar` all return 404 "App not found. Ensure that you have the correct app slug". These are most of the integrations this patch wires up; only hubspot, salesforce, webex, zohocrm and zoho-bigin match.
    - Evidence: compare the generated keys with the `slug` values in each app's `_metadata.ts` / `config.json`. Reasoned; not executed.

11. **`packages/app-store/zoomvideo/lib/VideoApiAdapter.ts:92` — Minor.** It sends the appSlug `"zoomvideo"`, but the app's slug is `"zoom"` (`zoomvideo/_metadata.ts:16`). The slug sent to the sync endpoint doesn't match the one the webhook and the App table use.

12. **`apps/web/pages/api/webhook/app-credential.ts:24-27` — Minor.** The secret is compared with `!==`, which is not constant-time. There is no `req.method` check either.

13. **`apps/web/pages/api/webhook/app-credential.ts:31,57-59` — Minor.** A malformed body (zod `.parse`), a bad ciphertext or a wrong key (`symmetricDecrypt`/`JSON.parse`) throws and returns a 500 instead of a 400.

14. **`apps/web/pages/api/webhook/app-credential.ts:62-85` — Minor.** `findFirst` on userId+appId updates an arbitrary credential when a user has several for the same app, for example two Google accounts. Team credentials are ignored, and `invalid: true` is never reset on update.

15. **`packages/lib/constants.ts:103` — Minor.** `APP_CREDENTIAL_SHARING_ENABLED` is typed `string | undefined` rather than a boolean (it uses `&&` without `!!`).

16. **Patch-wide — Important (tests).** There are no tests for the new endpoint, which writes credentials and is guarded only by a shared secret, or for the shared refresh and parse helpers. An integration test of the webhook, or a single refresh round-trip per provider shape, would have caught findings 1, 4, 7 and 10.

## Not reviewed
- The `.env.example` and `turbo.json` changes got only a skim; they are config/docs and I found nothing wrong.
- The import-only edits from moving `createOAuthAppCredential`, `decodeOAuthState` and `encodeOAuthState` into `_utils/oauth/` (every `api/add.ts`, `api/_getAdd.ts`, `api/callback.ts`) were checked only by a repo-wide grep. No importer of the old paths remains.
- Lark (`larkcalendar/lib/CalendarService.ts`), Webex (`webex/lib/VideoApiAdapter.ts`) and MS Teams (`office365video/lib/VideoApiAdapter.ts`) were reviewed only for the wrapper call. They pass the `Response` to fetch-based handlers, which is compatible, but I didn't check whether a sync-endpoint response satisfies each provider's own response handler.

All of the above is static reasoning except the zod repro; none of it was compiled or run against a database.
