I reviewed the change with `mattpocock-skills:code-review` against fixed point c22f76867f (head daffb05b5a, 2 commits, 28 files). You told me not to spawn agents, so I ran the skill's two axes myself instead of through its usual sub-agents. The repo's written standards are in `CONTRIBUTING.md`, `PR-CHECKLIST.md` and `docs/tests-development.md`. `js/CODING_GUIDELINES.md` does not apply because no JS is touched.

## Standards

**1. Important: the new integration-test matcher accepts any grant, so the event tests check nothing about the grant.**
- **Where:** `testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/AssertEvents.java:476-487`, method `isAccessTokenId`.
- **Standard breached:** `CONTRIBUTING.md` asks for a "functional/integration test" and `PR-CHECKLIST.md` asks for "sufficient test coverage".
- **Evidence:** the matcher has two bugs.
  - It reads `substring(3, 5)`. The grant code sits at indices 4–5, so this reads the last character of the token-type code plus the first character of the grant code.
  - The test is inverted: `if (... .equals(expectedGrantShortcut)) return false;`.
  - Index 3 is always `t` (`rt`/`lt`), and no grant code tested here starts with `t` (`ac`, `rt`, `ci`, `dg`). So the check never rejects anything, and every token ID with a UUID suffix passes.
  - This makes the four updated expectations (`expectCodeToToken`, device, `expectRefresh`, `expectAuthReqIdToToken`) vacuous about the grant type.
- **Reproduction:** `jshell -q <bench>/work/keycloak__keycloak__37634.scratch/matcher_check.jsh`. The script copies the matcher logic word for word; it does not run the real class. It prints `true` for `onrtrt:` when `ac` is expected, `onrtna:` when `rt` is expected, and `onrtzz:` when `ci` is expected.
- **Fix:** compare `substring(4, 6)` and return `false` when it is not equal.

**2. Minor: the new unit test uses `org.junit.Assert`.**
- **Where:** `services/src/test/java/org/keycloak/protocol/oidc/encode/DefaultTokenContextEncoderProviderTest.java:1004-1053`.
- **Standard breached:** `docs/tests-development.md` says to use `MatcherAssert.assertThat` and to "avoid as much to use … `org.junit.Assert.*`".
- **Evidence:** every assertion is `Assert.assertEquals`, with actual and expected swapped, so failure messages would read backwards.

**3. Minor: a refactor unrelated to the feature.**
- **Where:** `services/src/main/java/org/keycloak/protocol/oidc/TokenManager.java:864-869`.
- **Standard breached:** `CONTRIBUTING.md` says "Do not format or refactor code that is not directly related to your contribution."
- **Evidence:** the typo rename `requestedAucienceClients` → `requestedAudienceClients`.
- **Borderline case:** `server-spi-private/.../OAuth2GrantType.java:99-116` deletes the public `Context(Context)` copy constructor. Nothing in the repo calls it (checked with grep), but removing it is not needed for this feature.

**4. Minor: no upgrade or release notes.**
- **Standard breached:** `PR-CHECKLIST.md` asks for "updates to release notes and upgrade guide if applicable", and `CONTRIBUTING.md` says "Includes documentation".
- **Evidence:** the access token `jti` and the `token_id` event detail change from a bare UUID to `<ss><tt><gg>:<uuid>`. Anyone who parses `jti` as a UUID will see this. `OAuth2GrantTypeFactory` also gains a new abstract method, `getShortcut()`, with no default, so custom grant factories stop compiling. Because `OAuth2GrantTypeSpi.isInternal()` is true, this is only Minor. `docs/documentation/upgrading/topics/changes/changes-26_2_0.adoc` mentions neither change.

**5. Minor: commit format.**
- **Standard breached:** `CONTRIBUTING.md` requires one commit per PR and a closing line of exactly `Closes #1234` ("please only use the above formats").
- **Evidence:** there are 2 commits. ee2491268a uses lowercase `closes #37118`. daffb05b5a has no issue link.

**6. Minor: the javadoc contradicts the code.**
- **Where:** `server-spi-private/.../OAuth2GrantTypeFactory.java:29-33`.
- **Evidence:** the javadoc says the shortcut is "usually like 3-letters". But `DefaultTokenContextEncoderProvider.java:74-76` throws unless the context is exactly 6 characters (2+2+2), and `encodeTokenId` (`:101-117`) never checks length. A custom grant that follows the javadoc and uses 3 letters would encode a token ID that cannot be decoded.
- **Why only Minor:** `getTokenContextFromTokenId` has no production caller yet, only the unit test. Once something decodes these IDs, this becomes Important.

**Smell baseline:** nothing worth reporting. The `GRANT_SHORTCUT` constant is declared on some factories and inlined as a literal on others, which is cosmetic.

## Spec

There is no spec, so I skipped this axis as the skill directs. The checks below are reasoned against the commit subject only ("Encoding context to access token IDs").

**S1. Important: client-credentials tokens never get the `cc` code.**
- **Where:** `services/src/main/java/org/keycloak/protocol/oidc/grants/ClientCredentialsGrantType.java:140-141` (file not in the patch).
- **Evidence:** this grant builds its token through `responseBuilder(...).generateAccessToken()`, not `createTokenResponse`. Nothing sets `Constants.GRANT_TYPE`, so the encoder falls back to `na` and the ID looks like `trrtna:<uuid>` or `onrtna:<uuid>`. The patch registers `cc` and its own unit test uses `trltcc:1234` as the client-credentials example, yet no production path ever emits `cc`.
- **Same problem elsewhere:** the UMA permission grant (`AuthorizationTokenService.java:358`, code `pg` never emitted), V1/federated/impersonation token exchange (`AbstractTokenExchangeProvider.java:410`) and implicit/hybrid (`OIDCLoginProtocol.java:272`) all produce `na`.
- **Status:** reasoned, not run. A test that would fail: in `ClientCredentialsGrantTest`, assert that `oauth.verifyToken(accessToken).getId().substring(4, 6)` equals `"cc"`.

## Other observation (outside both axes)

`services/.../encode/AccessTokenContext.java:207` contains `Objects.requireNonNull(grantType, "Null rawTokenId not allowed")`, a copy-paste slip. The null check runs on `grantType` again, so `rawTokenId` is never checked.

## Coverage

I reviewed all 28 files in the patch. Nothing was skipped. I reviewed the two commits as one combined diff; I could not inspect daffb05b5a on its own because fetching its objects needs network access, which the sandbox blocks.

**Summary:** Standards has 6 findings; the worst is the matcher (1), which lets the event tests pass regardless of grant. Spec has 1 finding against the commit intent; the worst is that client-credentials, UMA, and legacy token-exchange tokens are encoded as grant `na`.

I did not compile anything or run the real test suites, and the matcher proof runs a copy of the logic. The risk to flag is that the PR's integration tests look green but do not verify the feature.
