Ponytail review (over-engineering seat), keycloak PR head daffb05b5a vs c22f76867f

**What this change does:** Every new access token ID now starts with a 6-character code, followed by a colon and a UUID. The code records session type (on/of/tr), token type (rt/lt) and grant type (2-letter shortcut), for example `onrtac:<uuid>`. To do this, the change adds an internal `tokenContextEncoder` SPI (an SPI is Keycloak's plug-in interface) with one default provider. It also adds a required `getShortcut()` method to `OAuth2GrantTypeFactory` and sets a `grant_type` attribute on the client session context in each grant path.

Assumed load: a multi-tenant production IdP. The code runs on every token issue (`TokenManager.initToken`).

## Findings in my lane (lean / over-engineering)

1. **The encode side keeps a second map of grant shortcuts, with its own refresh logic** (`services/src/main/java/org/keycloak/protocol/oidc/encode/DefaultTokenContextEncoderProviderFactory.java:42,68,76,79,106-119`). Severity: Minor.
   - **What this is:** `grantsToShortcuts` maps a grant name to its shortcut. On a miss, `getShortcutByGrantType` asks the session factory for that grant's factory and caches the result, which handles hot-deployed grants.
   - **Problem:** `sessionFactory.getProviderFactory(OAuth2GrantType.class, grantType)` is already a map lookup, and it already sees hot-deployed factories. The cache only adds a second copy that can go stale: an undeployed grant keeps its entry. The refresh path in `getGrantTypeByShortcut` (lines 121-137) also adds entries without the duplicate-shortcut check that `postInit` runs at lines 81-85.
   - **Fix:** Encode with `((OAuth2GrantTypeFactory) sessionFactory.getProviderFactory(OAuth2GrantType.class, gt)).getShortcut()`, plus the existing `"na"` case and a null check. Keep only the reverse map `grantsByShortcuts`, which decode needs. Then `grantsToShortcuts`, its refresh branch and the two-map size check can go. Duplicate shortcuts can be detected directly while building `grantsByShortcuts`, with `putIfAbsent != null` throwing.
   - **If we skip it:** Two maps must stay in sync by hand, and the hot-deploy path quietly skips validation. Saves about 20 lines.

2. **Lookup maps built for enums of 3 and 4 values** (`DefaultTokenContextEncoderProviderFactory.java:39-40,50-61,98-104`). Severity: Minor.
   - **What this is:** `init()` builds two unmodifiable HashMaps from each enum's shortcut to its value. Two protected getters wrap them.
   - **Problem:** That is factory state and setup code just to search 3 or 4 enum constants. The lookup belongs on the enum itself. The maps also register the `UNKNOWN("un")` shortcuts, so decode accepts `ununna:x`, which `encodeTokenId` (DefaultTokenContextEncoderProvider.java:337-342) then refuses to encode.
   - **Fix:** Add `static SessionType fromShortcut(String s)` (and the same on TokenType) with `Arrays.stream(values()).filter(v -> v.shortcut.equals(s)).findFirst().orElse(null)`, and delete the maps, `init` body and getters. Either skip UNKNOWN in that lookup, or accept the asymmetry on purpose.
   - **If we skip it:** About 15 extra lines, and a decode/encode mismatch for `un`.

3. **New constant that only renames an existing one** (`server-spi-private/src/main/java/org/keycloak/models/Constants.java:206-207`). Severity: Minor.
   - **What this is:** `Constants.GRANT_TYPE = OAuth2Constants.GRANT_TYPE`.
   - **Problem:** It is the same string under a second name. The patch even uses both: `OAuth2GrantType.Context` reads `OAuth2Constants.GRANT_TYPE`, while the grants and `TokenManager` write `Constants.GRANT_TYPE`.
   - **Fix:** Delete it and use `OAuth2Constants.GRANT_TYPE` at the call sites. Saves 2 lines.

Things I looked at and did not flag:
- **The full SPI** (Spi, ProviderFactory interface, Provider interface, services files; about 140 lines) has only one implementation. But internal SPIs with a single default provider are Keycloak's normal pattern, so it is not a breach here.
- **Removing the unused `Context(Context)` copy constructor** (OAuth2GrantType.java) is a good deletion. Its only construction site is `TokenEndpoint.java:149`.
- **The decode path `getTokenContextFromTokenId` has no production caller in this patch.** Only the unit test uses it. It is the stated purpose of issue #37118, so I did not call it YAGNI.

## Outside my lane (correctness): flagging so they are not lost

4. **The test matcher never checks the grant type** (`testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/AssertEvents.java:483`). Severity: Important.
   - **Problem:** It reads the wrong characters, `substring(3,5)` where the grant is at `substring(4,6)`. The comparison is also inverted: `equals -> return false`.
   - **Result:** The check only fails when `"t"+grant[0]` equals the expected shortcut, which no real ID produces. So the four updated event expectations (code-to-token, device, refresh, CIBA) do not guard the new grant encoding at all.
   - **Failing check:** `jshell -q <bench>/work/keycloak__keycloak__37634.scratch/matcher_check.jsh` reproduces the matcher's logic. It prints `wrong grant 'cc' accepted as 'ac': true` and `wrong grant 'na' accepted as 'rt': true`.
   - **Fix:** `if (!items[0].substring(4, 6).equals(expectedGrantShortcut)) return false;`

5. **Client-credentials tokens get `na` instead of `cc`** (`services/src/main/java/org/keycloak/protocol/oidc/grants/ClientCredentialsGrantType.java:122-141`). Severity: Important. This is reasoned, not run.
   - **Problem:** This grant never calls `createTokenResponse` and never sets `Constants.GRANT_TYPE`, so `initToken` falls back to `"na"`.
   - **Why tests miss it:** The unit test `trltcc:1234` passes only because it never goes through the grant.
   - **Failing test to add:** An E2E test asserting that a client-credentials token's `jti` starts with `trrtcc:`, or the matching `CLIENT_LOGIN` event detail, would fail on this code.
   - **PermissionGrantType:** It registers `pg`, and I did not see it set the attribute either. I did not trace its token path.

6. **Wrong variable in a null check** (`services/src/main/java/org/keycloak/protocol/oidc/encode/AccessTokenContext.java:73`). Severity: Minor.
   - **Problem:** `Objects.requireNonNull(grantType, "Null rawTokenId not allowed")` checks `grantType` a second time, so a null `rawTokenId` gets through and is encoded as `"...:null"`.
   - **Fix:** Pass `rawTokenId`.

Verdict: Fix 4 and 5 first. 1-3 are optional cleanups.
Lean: about 37 lines could be removed.

Files reviewed: all 28 files in the patch, at the diff level, with surrounding source read for TokenManager.initToken, OAuth2GrantTypeBase.createTokenResponse, the ROPC, PreAuthorizedCode and ClientCredentials grant paths, TokenEndpoint context construction, and DefaultKeycloakSessionFactory hot deploy. Files not reviewed: none.

Not checked: I ran no builds or tests. I did not trace whether implicit or hybrid flow tokens from the authorization endpoint, or PermissionGrantType tokens, end up with `na`.
