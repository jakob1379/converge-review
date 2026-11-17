I loaded superpowers:requesting-code-review and did the review myself, as instructed. I checked the patch against base 272cfc68dc and read the code around each change. I did not build or run anything, so every finding below is reasoned from the code. No spec was given, so I judged behaviour by what a reasonable user or admin would expect.

**Verdict: fix before merging.** The caching approach follows the existing `getByOrganization` cache and is mostly sound. One gap in cache invalidation can leave a stale login list and show the wrong identity providers on the login page.

## Findings

### 1. Important: stale login cache when an IdP is edited while its organization is disabled
**Where:** `model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/idp/InfinispanIdentityProviderStorageProvider.java:91-93` and `:403-407`

**Claim:** A hidden IdP, a link-only IdP, or an IdP whose public flag (`BROKER_PUBLIC`) was removed can still appear on the login page.

**Why it happens:**
- In `update()`, the "before" model comes from `getById()` (line 91). That method wraps the model so that `isEnabled()` returns false when the linked organization is disabled (lines 436-442).
- The "after" model comes from the admin endpoint (`IdentityProviderResource.updateIdpFromRep`, line 191) and is not wrapped. Its `isEnabled()` is the raw flag.
- So while the organization is disabled, the "before" model always fails the login check. If the edit also makes the "after" model fail it (for example `hideOnLogin=true`, `linkOnly=true`, or `BROKER_PUBLIC` removed), line 405 returns early and no cache entry is invalidated.
- The cached ID lists for `.idp.login.ORG_ONLY` and `.idp.login.ALL` were built by the JPA query, which ignores whether the organization is enabled. They still contain the IdP.
- Enabling the organization again does not touch the login cache keys either (`InfinispanOrganizationProvider.registerOrganizationInvalidation`, around lines 300-310, only invalidates the org ID, the org-ID IdP list and the domains).
- After that, `getForLogin` (lines 244-252) loads each cached ID through a fresh `getById`. The organization-aware login page bean (`OrganizationAwareIdentityProviderBean.java:75,80`) only re-checks `isEnabled()`. It does not re-check hide-on-login, link-only or `BROKER_PUBLIC`.
- Result: an IdP the admin made hidden or private is shown on the login page. This lasts until some unrelated change to a login-eligible IdP invalidates the cache, or the entry is evicted.

**Failing test (not run).** Add it to `OrganizationCacheTest`:
1. Create IdP X: enabled, `BROKER_PUBLIC=true`, then link it to orga.
2. On the server, call `getForLogin(ORG_ONLY, null)` and assert the `cacheKeyForLogin(realm, ORG_ONLY)` entry is not null.
3. Disable orga (`organizations().get(orgaId).update(rep with enabled=false)`).
4. Update X with `setHideOnLogin(true)`, or remove `BROKER_PUBLIC`.
5. Enable orga again.
6. On the server, assert that `getForLogin(ORG_ONLY, null).filter(IdentityProviderModel::isEnabled)` does not contain X.

On the patched code, the cache entry is still non-null after step 4 and step 6 returns X with `isHideOnLogin()==true`.

**Fix direction:** evaluate the "before" model on the raw, unwrapped model (`idpDelegate.getById`), the same way `remove()` already uses the raw model at line 100. Alternatively, have the bean re-apply the full login check instead of only `isEnabled()`.

### 2. Minor: public SPI behaviour change in `getLoginPredicate()`
**Where:** `server-spi/src/main/java/org/keycloak/models/IdentityProviderStorageProvider.java:254`

**Claim:** The added `getOrganizationId() == null || BROKER_PUBLIC` clause changes a public static predicate, not just the cache logic.

**Evidence:**
- The predicate is also the default `federatedProviderPredicate()` in the base login page bean (`services/src/main/java/org/keycloak/forms/login/freemarker/model/IdentityProviderBean.java:226`). That bean is used when organizations are disabled.
- When the Organization feature is off, IdPs are not wrapped (line 433 of the Infinispan provider). An IdP still linked to an organization but not marked public was previously shown to users who already have a linked identity with it. It is now hidden.
- This is probably the intended behaviour, but it is undocumented. The Javadoc on `getForLogin` (lines 151-152) and on `getFederatedIdentityProviders` (lines 202-203) still list only enabled, link-only and hide-on-login as the criteria.
- In `OrganizationAwareIdentityProviderBean.federatedProviderPredicate()` the new clause is now partly redundant.

### 3. Minor (reasoned): one cache entry per fetch mode for all organizations
**Where:** `InfinispanIdentityProviderStorageProvider.java:233-240`

**Claim:** The `ORG_ONLY` and `ALL` login caches keep the results for every organization ID in a single cache entry per mode.

**Evidence:**
- Each organization seen for the first time invalidates the entry and re-adds it with a full copy of the existing results (`IdentityProviderListQuery`'s copy constructor, `putAll(previous.searchKeys)`). That is O(number of organizations) per miss.
- The entry grows without limit as more organizations are seen.
- Any change to a login-eligible IdP clears the results for every organization at once.
- `getByOrganization` uses one key per organization and avoids this. With thousands of organizations, expect cache churn on the login path.

### 4. Minor: test cleanup does nothing
**Where:** `testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/organization/cache/OrganizationCacheTest.java:381` and `:425`

**Claim:** `getCleanup().addCleanup(testRealm().identityProviders().get("alias")::remove)` passes the literal string `"alias"`, so the IdPs the test creates are never removed.

**Evidence:** The pattern was copied from line 303. `create(idpRep).close()` never checks the response status, so a duplicate-alias conflict would also go unnoticed. This only matters if the test realm is not re-imported between tests, which I did not check.

### 5. Minor: test gap
**Where:** `OrganizationCacheTest.java:370-535` (`testCacheIDPForLogin`)

**Claim:**
- The test only asserts that cache entries exist and how many IDs they hold. It never checks what the login page actually shows.
- It does not cover a disabled organization, an organization being removed, or the `isEnabled()` re-check added in the bean. Finding 1 lives in exactly that gap.
- There is no test at the browser or login-page level for the bean change at `OrganizationAwareIdentityProviderBean.java:75,80`.

## Checked and found OK
- The test's expected counts are consistent: 5/5/10 at the start, then 6/5/11, then 5/6/11.
- Unlinking IdPs when an organization is deleted goes through `update()` and correctly invalidates the login cache.
- In `remove()`, a missing IdP (`storedIdp == null`) is safe in the new login invalidation path.
- `IdentityProviderListQuery` implements `InRealm`, so deleting a realm evicts these entries.
- `registerInvalidation` sends cluster invalidation events.

## Files not reviewed
None. I reviewed all four files in the patch:
- `model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/idp/InfinispanIdentityProviderStorageProvider.java`
- `server-spi/src/main/java/org/keycloak/models/IdentityProviderStorageProvider.java`
- `services/src/main/java/org/keycloak/organization/forms/login/freemarker/model/OrganizationAwareIdentityProviderBean.java`
- `testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/organization/cache/OrganizationCacheTest.java`
