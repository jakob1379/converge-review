## Review: keycloak PR (encode context into access token IDs), c22f76867f..daffb05b5a

I ran OCR delegate mode in range mode from c22f76867f to daffb05b5a. OCR returned the generic Java checklist (logic errors, NPE, dead code, thread safety). I applied no fixes because the task is report-only. I ran one standalone jshell snippet in the scratch directory and no project builds or tests.

There is no spec, so I took issue #37118 and the commit titles as the intent: put session type, token type and grant type into the access token `jti`.

### Findings

**1. Important. `testsuite/.../AssertEvents.java:483`: the new `isAccessTokenId` matcher accepts any grant type.**
- The claim: the matcher checks the wrong characters, and its condition is inverted. The two bugs cancel out, so it passes for practically any `xxxxyy:<uuid>`. The expectations for code-to-token, device, refresh and CIBA therefore never check the grant shortcut.
- The evidence: the encoded layout is session(2) + token type(2) + grant(2), so the grant sits at `[4,6)`. The matcher reads `substring(3, 5)` and returns `false` when that equals the expected shortcut.
- Failing check, run as `jshell -q .../keycloak__keycloak__37634.scratch/ocr/matcher.jsh` with the logic copied verbatim:
  - `onrtcc:<uuid>` with expected `ac` gives **true**. A wrong grant is accepted.
  - `onrtna:<uuid>` with expected `rt` gives **true**. An unknown grant is accepted.
- If only the offset is fixed to `substring(4, 6)`, every correct token fails, because the `return false` on equality is also inverted. Both have to be fixed together.
- Consequence: the integration suite gives no evidence that real grant flows encode the right grant. Finding 2 shows that at least one of them does not.

**2. Important. `ClientCredentialsGrantType.java:140-141` (unchanged code the patch should have reached): `client_credentials` tokens are encoded with grant `na`, not `cc`.**
- The claim: `Constants.GRANT_TYPE` is set in only 5 places:
  - `OAuth2GrantTypeBase.createTokenResponse`
  - ROPC (password grant)
  - `TokenManager.refreshAccessToken`
  - `PreAuthorizedCodeGrantType`
  - `StandardTokenExchangeProvider`

  `ClientCredentialsGrantType` builds its token through `tokenManager.responseBuilder(...).generateAccessToken()` and never calls `createTokenResponse`. So `DefaultTokenContextEncoderProvider.getTokenContextFromClientSessionContext` falls back to `UNKNOWN` ("na").
- The patch still adds the shortcut `"cc"` in `ClientCredentialsGrantTypeFactory`, and its own unit test uses `trltcc:1234` as the example service-account token. Neither is ever produced in production.
- The same gap applies to these paths, which all end up as "na":
  - UMA tokens via `AuthorizationTokenService:357` (the `"pg"` shortcut is never emitted)
  - V1 token exchange via `AbstractTokenExchangeProvider:409`
  - implicit/hybrid tokens
- The evidence: `grep -rn "setAttribute(Constants.GRANT_TYPE" services/src/main` lists exactly those 5 sites. No test fails today, because `ServiceAccountTest` compares `TOKEN_ID` against `accessToken.getId()` and finding 1 hides the rest. This claim is reasoned from code; I wrote no failing test.

**3. Important. `OAuth2GrantTypeFactory.java:33` together with `DefaultTokenContextEncoderProviderFactory.java:74`: new abstract `getShortcut()` with no default and no validation.**
- The claim: any custom `OAuth2GrantTypeFactory` built against the previous API breaks server startup, and so does one that returns null:
  - An older custom jar throws `AbstractMethodError` in `postInit`, because `postInit` calls `gtf.getShortcut()` on every grant factory at startup.
  - A null return throws an NPE from `ConcurrentHashMap.put(null, …)`.
- The startup check only catches duplicate shortcuts. It does not enforce the length of 2 that decoding needs (`DefaultTokenContextEncoderProvider.java:74` requires exactly 6 prefix characters). The new Javadoc even says "usually like 3-letters shortcut". A 3-character shortcut encodes without error but makes `getTokenContextFromTokenId` throw `IllegalArgumentException`.
- Mitigation: `server-spi-private` is a private SPI, and all 10 in-repo implementers were updated. I checked this with a grep.
- This claim is reasoned; I did not build a custom provider jar.

**4. Minor. `AccessTokenContext.java:73`: copy-paste bug, so `rawTokenId` is never null-checked.**
- The line reads `Objects.requireNonNull(grantType, "Null rawTokenId not allowed")`, which re-checks `grantType`.
- A null `rawTokenId` is accepted, and `encodeTokenId` then emits `onrtna:null`.

**5. Minor. `OAuth2GrantType.java:53`, `:105`: `grantType` is fixed when the Context is constructed.**
- `grantType` is captured from `formParams` in the constructor, and `setFormParams` does not refresh it.
- No in-repo caller of `setFormParams` exists, so there is no runtime effect today. The public `Context(Context)` copy constructor was also removed from the SPI. It has no in-repo users, but it is an API removal.

**6. Minor. `DefaultTokenContextEncoderProvider.java:54` → `AbstractOIDCProtocolMapper.getShouldUseLightweightToken`.**
- The lightweight check is now called unconditionally for every access token. Before, it ran only when an OIDC mapper ran.
- It dereferences `session.getContext().getClient()` and reads the context (requesting) client, not the token's client. For example, in `PolicyEvaluationService` it reads the admin console client, which has lightweight enabled.
- This matches the existing mapper behaviour, so it is not a regression in semantics. A context with no client set would now NPE even when there are no mappers. This is reasoned; I found no concrete null-client caller.

### Coverage

| Measure | Value |
|---|---|
| total_files | 28 |
| reviewed_files | 28 |
| skipped_files | 0 |
| coverage_rate | 100% |

OCR excluded 4 files: the 2 `META-INF/services` files (unsupported extension), `DefaultTokenContextEncoderProviderTest.java` and `AssertEvents.java` (test paths). I reviewed all 4 anyway from the patch. Finding 1 comes from `AssertEvents.java`.

What I checked beyond the diff:
- Every `OAuth2GrantTypeFactory` implementer in the repo.
- Every caller of the `Context` constructor and of `createClientAccessToken`.
- Where `UseLightweightAccessTokenExecutor` fires: it runs before the token is built, so that is fine.
- The persistence of revoked-token IDs. The DB column is `VARCHAR(255)`, so the longer 43-character `jti` fits. `RevokedTokenEntity` still says `@Column(length = 36)`; that annotation is stale but outside this patch.

What I did not check: I compiled and ran nothing in the project. Findings 2, 3 and 6 are reasoned from code. Only finding 1 is backed by an executed check, at `<bench>/work/keycloak__keycloak__37634.scratch/ocr/matcher.jsh`.

The biggest risk: findings 1 and 2 together mean the main promise of the feature, grant type encoded in the `jti`, is both broken for client_credentials, UMA and V1 token exchange, and invisible to the tests.
