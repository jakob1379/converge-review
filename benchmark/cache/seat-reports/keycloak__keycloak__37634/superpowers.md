Review of change.patch (keycloak__keycloak__37634: c22f76867f..daffb05b5a, "Encoding context to access token IDs" plus "Shorter encoding of access token")

The `superpowers:requesting-code-review` skill was invoked. Its normal step is to dispatch a reviewer subagent, but the caller forbade spawning agents, so I applied the skill's reviewer template (code-reviewer.md) directly. There is no spec, so I judged against issue #37118's evident intent: encode session type, token type and grant type into the access-token `jti`. Nothing was built or run against the project. One standalone jshell repro was written to the .scratch dir.

## Findings

### Important

**1. testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/AssertEvents.java:483. The new `isAccessTokenId` matcher can never fail on the grant type, so every updated assertion is vacuous.**
- **Wrong offset:** `items[0].substring(3, 5)` reads index 3-4. The grant shortcut sits at index 4-5: sessionType(2) + tokenType(2) + grant(2), so the code needs `substring(4, 6)`. The comment ("starts at 4th char") is left over from the earlier 3-letter encoding.
- **Inverted check:** the line returns `false` on a match, where it should return `false` on a mismatch.
- **Combined effect:** a token with any grant passes for any expected grant. A crafted token can fail, but only by accident. `expectCodeToToken`, `expectDeviceCodeToToken`, `expectRefresh` and `expectAuthReqIdToToken` (lines 145, 173, 182, 244) therefore verify only "something:UUID". They would not catch a wrong or "na" grant.
- **Second defect:** a prefix shorter than 5 chars throws StringIndexOutOfBoundsException instead of returning false.
- **Evidence (standalone repro of the matcher body):** run `jshell -q <bench>/work/keycloak__keycloak__37634.scratch/matcher_repro.jsh`. Output:
  - `onrtna:<uuid>` vs expected `ac` gives true
  - `ofltcc:<uuid>` vs expected `rt` gives true
- **Fix direction:** `if (!items[0].substring(4, 6).equals(expectedGrantShortcut)) return false;` plus a length guard.

**2. services/src/main/java/org/keycloak/protocol/oidc/grants/ClientCredentialsGrantType.java:140-141 (not touched by the patch). Client-credentials tokens are encoded with grant "na", not "cc".**
- Only `OAuth2GrantTypeBase.createTokenResponse`, `TokenManager.refreshAccessToken`, the ROPC grant, PreAuthorizedCode and `StandardTokenExchangeProvider` set `Constants.GRANT_TYPE`.
- `ClientCredentialsGrantType` calls `tokenManager.responseBuilder(...).generateAccessToken()` directly and never sets the attribute. `DefaultTokenContextEncoderProvider.getTokenContextFromClientSessionContext` then falls back to `UNKNOWN` ("na").
- The patch's own unit test uses `trltcc:1234` as the canonical client-credentials id, which real tokens will never produce. So the feature fails its intent for one of the most common grants.
- The same gap applies to:
  - UMA/permission grant ("pg"): `AuthorizationTokenService.java:358`
  - Legacy V1 token exchange: `AbstractTokenExchangeProvider.java:410`
- `grep -n GRANT_TYPE` on those files returns nothing.
- Reasoned: the integration test that would show it needs a running server. Asserting `isAccessTokenId("cc")` (with finding 1 fixed) in any client-credentials test, e.g. ServiceAccountTest, would fail.

### Minor

**3. services/src/main/java/org/keycloak/protocol/oidc/encode/AccessTokenContext.java:73.** The line reads `Objects.requireNonNull(grantType, "Null rawTokenId not allowed")`. It checks `grantType` a second time, so `rawTokenId` is never null-checked. A null raw id would encode to `"onrtac:null"`.

**4. server-spi-private/src/main/java/org/keycloak/protocol/oidc/grants/OAuth2GrantTypeFactory.java:33.**
- `getShortcut()` is a new abstract method with no default. Custom `OAuth2GrantTypeFactory` implementations compiled against the old interface would hit AbstractMethodError in `DefaultTokenContextEncoderProviderFactory.postInit`, which breaks server startup.
- I rated this Minor because `OAuth2GrantTypeSpi.isInternal()` returns true (unsupported for extensions).
- The removed `Context(Context)` copy constructor (OAuth2GrantType.java) has no in-repo callers. It is the same internal-SPI compat concern.

**5. Not documented: user-visible change to the `jti` format.** It goes from a bare UUID to `<2+2+2 chars>:<uuid>`, e.g. `onrtac:…`. Anything outside Keycloak that treats `jti` or event `token_id` as a UUID will break. No upgrading-guide note was added; the patch touches nothing under docs/documentation/upgrading. Reasoned.

**6. model/jpa/src/main/java/org/keycloak/models/jpa/entities/RevokedTokenEntity.java:34 (not in the patch).**
- `@Column(name="ID", length = 36)` is now shorter than access-token ids (43 chars).
- The Liquibase column is VARCHAR(255) (jpa-changelog-26.0.0.xml:60), so there is no runtime failure; the annotation is just stale.
- Worth aligning if the persisted revoked-token path stores the `jti`.

## Considered and set aside
- **NPE in `getShouldUseLightweightToken` when the session context client is null** (admin PolicyEvaluationService, KeycloakIdentity): set aside. The same call already runs in the default protocol mappers on those paths, so this is not a new risk.
- **Implicit/hybrid tokens (OIDCLoginProtocol.java:272) encoding "na":** set aside. There is no grant type there, so "na" is defensible.
- **Lightweight-token client-policy timing:** set aside. The executor fires on TOKEN_REQUEST and similar events, before token creation.
- **Unsynchronized lazy map refresh in DefaultTokenContextEncoderProviderFactory, and no collision check on hot-deploy:** set aside as a code smell. The startup collision check (map-size comparison) does catch duplicate or "na" shortcuts.

## Files not reviewed
None. All 28 files in the patch were read. The license-only and service-registration files (TokenContextEncoderProviderFactory.java, TokenContextEncoderSpi.java, the two META-INF/services files) were checked only for correct registration.

I did not compile or run any Keycloak test. Findings 1 and 3 are confirmed by reading the code, and finding 1 by the jshell repro. Finding 2 is confirmed from the call sites but not exercised against a running server.
