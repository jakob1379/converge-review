I loaded `mattpocock-skills:code-review` and ran both axes myself, without sub-agents. The patch is 1 commit (e944e2acf1) on base 272cfc68dc: 4 files, +274/−4. Nothing was built or run, so every finding below is reasoned from reading the code.

## Standards

Sources read: `CONTRIBUTING.md`, `PR-CHECKLIST.md`, `docs/pull_request_template.md` and `docs/tests-development.md`. I skipped `js/CODING_GUIDELINES.md` because the patch has no JS. Following your brief, I left the skill's generic Fowler smell checks out.

1. **server-spi/src/main/java/org/keycloak/models/IdentityProviderStorageProvider.java:254 — Minor (judgement call).**
   - **Rule:** `CONTRIBUTING.md` says "No changes to code not directly related to your PR". `PR-CHECKLIST.md` says "The PR does not contain changes not relevant to the GitHub Issue".
   - **Claim:** the commit is titled "Add cache for …getForLogin", but it also changes what the shared public SPI predicate `LoginFilter.getLoginPredicate()` returns. The predicate now also requires `organizationId == null || BROKER_PUBLIC`.
   - **Why it matters:** this predicate is not only used for the new cache invalidation. It is also the base filter in `IdentityProviderBean.federatedProviderPredicate()` (services/.../IdentityProviderBean.java:226). The plain `IdentityProviderBean` is the one used when organizations are off for the realm (`FreeMarkerLoginFormsProvider.java:481-485`). In that case, `getFederatedIdentityProviders` will now hide a user's already-linked IDP if it is bound to an organization and not marked public. Before the patch it was shown.
   - **Context:** this may be what was intended, since the realm-only search path already excludes org IDPs. But it is an unannounced behaviour change, and a predicate local to the Infinispan provider would have kept the cache work self-contained.

2. **server-spi/src/main/java/org/keycloak/models/IdentityProviderStorageProvider.java:216 and :151-152 — Minor.**
   - **Rule:** `CONTRIBUTING.md` asks contributions to keep relevant documentation current ("We require contributions to include relevant documentation").
   - **Claim:** two Javadoc comments are now out of date:
     - `LoginFilter` is described as the "Enum that contains all fields that are considered when deciding if a provider should be available for login". The new org/`BROKER_PUBLIC` condition is hard-coded into `getLoginPredicate()` and is not an enum entry, so `getLoginSearchOptions()` and `getLoginPredicate()` no longer encode the same criteria.
     - The `getForLogin` Javadoc still lists only enabled / not link-only / not hidden as the login criteria.

3. **testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/organization/cache/OrganizationCacheTest.java:370-535 (e.g. :404, :522) — Minor.**
   - **Rule:** `docs/tests-development.md` says "As assertion method use `org.hamcrest.MatcherAssert.assertThat` where possible … Please avoid as much to use set of assertions from `org.junit.Assert.*`".
   - **Claim:** the new `testCacheIDPForLogin` uses `assertEquals`, `assertNull` and `assertNotNull` from `org.junit.Assert` throughout.
   - **Mitigation:** the existing tests in the same file already do this, so the new test is consistent with its file.

Rules that pass:
- Single commit, ending with `Closes #32573`, with a `Signed-off-by` trailer.
- An integration test is included, matching "Includes functional/integration test", and no mocking framework is added.
- No user-facing documentation looks necessary for an internal cache.

Outside my axes, flagged for the correctness seat (reasoned):
- **OrganizationCacheTest.java:381 and :425:** `getCleanup().addCleanup(testRealm().identityProviders().get("alias")::remove)` removes the literal alias `"alias"`, not `"idp-alias-" + i`, so this cleanup does nothing. The same bug already exists at :303 and was copied from there.

## Spec

Skipped, because you said there is no spec. The commit message does reference issue #32573, but I did not fetch it: you said there is no spec, and the sandbox blocked outbound github.com.

The commit title alone is a weak stand-in for a spec. Checked against it, `getForLogin` is now cached per `FetchMode`, keyed by organization ID, with invalidation on create, update and remove. The changes beyond that title are the predicate change and the `idp.isEnabled()` re-filter in `OrganizationAwareIdentityProviderBean.java:75,80` (see Standards #1).

## Unreviewed files

None. I reviewed all 4 files:
- `model/infinispan/.../InfinispanIdentityProviderStorageProvider.java`
- `server-spi/.../IdentityProviderStorageProvider.java`
- `services/.../OrganizationAwareIdentityProviderBean.java`
- `testsuite/.../OrganizationCacheTest.java`

For the Infinispan provider, I checked it against the documented standards only; I did not check whether the cache logic is correct.

## Axes run

- **Standards:** ran; 3 findings, all Minor. The worst is #1, the unannounced change to the public `getLoginPredicate()`.
- **Spec:** did not run; no spec was supplied and the issue was not fetched.

Not checked: whether the new `getForLogin` cache logic is correct (for example, concurrent writes, or caches not being invalidated when an organization is enabled, disabled or deleted). That belongs to the correctness seat.
