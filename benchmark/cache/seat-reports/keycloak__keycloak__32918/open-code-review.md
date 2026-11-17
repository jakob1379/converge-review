## Review: keycloak e944e2acf1 "Add cache for IdentityProviderStorageProvider.getForLogin" (base 272cfc68dc)

I ran OCR in commit mode (`ocr delegate preview --commit HEAD`). It picked 3 reviewable files out of 4 and returned only the generic Java checklist (typos, dead code, logic errors, performance, thread safety). No spec was supplied, so this review covers correctness only. Nothing was built or run, as benchmark mode requires, so every finding below is reasoned from the code.

### Findings

**1. model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/idp/InfinispanIdentityProviderStorageProvider.java:91-93 (and 403-418): Important**

**Claim:** The skip-invalidation check in `update()` compares the wrong "before" model. If an org-linked IDP stops qualifying for login while its organization is disabled, the login caches are not invalidated. When the org is enabled again, the cached ORG_ONLY/ALL lists still contain that IDP, and the login page shows a hidden, link-only or non-public org broker.

**Evidence:**
- `update()` takes `original` from `getById(...)` at line 91. That value goes through `createOrganizationAwareIdentityProviderModel` (lines 430-445), whose `isEnabled()` returns false when the org is disabled or the realm has organizations turned off.
- `updated` comes from the admin REST path as a plain model (`IdentityProviderResource.updateIdpFromRep` → `RepresentationToModel.toModel`, line 191).
- Sequence that breaks it:
  1. IDP X is enabled, `BROKER_PUBLIC=true`, and linked to org O. A login page loads and fills the ORG_ONLY/ALL caches with X's internal id.
  2. Org O is disabled. Nothing invalidates `cacheKeyForLogin`.
  3. The admin updates X with `hideOnLogin=true`, `linkOnly=true` or `BROKER_PUBLIC=false`. `getLoginPredicate().test(original)` is false because the wrapper reports the org as disabled. `test(updated)` is false because of the new flag. So the method returns at line 406 without invalidating.
  4. Org O is enabled again. The org update does not touch the IDP login keys.
- The cached path at lines 244-252 then returns X through `getById`. `OrganizationAwareIdentityProviderBean` (lines 74-81) re-checks only `isEnabled()`, not `hideOnLogin`, `linkOnly` or `BROKER_PUBLIC`, so X is rendered.
- Fix: evaluate the predicate on the unwrapped stored model (`idpDelegate.getById(...)`, or the raw `CachedIdentityProvider`), as `remove()` already does with `idpDelegate.getByAlias`. The other option is to always invalidate when the original has an org id.

**Suggested repro test (not run),** in the style of `OrganizationCacheTest.testCacheIDPForLogin`:
- Fill the ORG_ONLY cache with `getForLogin(ORG_ONLY, orgId)`.
- Disable the org through the admin API.
- Set `hideOnLogin=true` on `idp-alias-10`.
- Assert that `realmCache.getCache().get(cacheKeyForLogin(realm, ORG_ONLY), IdentityProviderListQuery.class)` is null. On the patched code it is still non-null.
- Re-enable the org and assert that `getForLogin(ORG_ONLY, orgId)` does not return `idp-alias-10`. On the patched code it does.

**2. model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/idp/InfinispanIdentityProviderStorageProvider.java:215, 232-241: Minor (performance)**

**Claim:** There is one `IdentityProviderListQuery` per realm and mode, keyed internally by organization id. In a realm with many organizations, each org's first `getForLogin(ALL, orgId)` on a node does two things:
- `invalidateObject` on the shared entry, which bumps its revision.
- A copy of the entire previous map into a new entry (`IdentityProviderListQuery(..., previous)` uses `putAll`).

**Evidence:**
- The entry grows with the number of orgs, and every new org costs a full map copy.
- Under concurrent logins for different orgs, each miss bumps the revision. That makes the other threads' `addRevisioned` calls fail, so caching barely works exactly when load is highest.
- Any change to a login IDP throws away the whole map for all orgs.
- `getByOrganization` uses the same pattern, but it is keyed per org, so it does not have this fan-in.
- Keying by `realm + mode + orgId` (and invalidating per mode) would avoid it.

**3. testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/organization/cache/OrganizationCacheTest.java:381, 425: Minor**

**Claim:** The cleanups register removal of an IDP with the literal alias `"alias"`, not the IDPs the test creates (`idp-alias-0` to `idp-alias-20`).

**Evidence:** `getCleanup().addCleanup(testRealm().identityProviders().get("alias")::remove)`. The 21 created IDPs are never cleaned up, and each cleanup targets an IDP that does not exist. The same bug was already there at line 303, and the patch copied it.

### Checked, no finding
- **`getLoginPredicate` change (server-spi `IdentityProviderStorageProvider.java:254`):** This also affects `IdentityProviderBean.federatedProviderPredicate` (line 226). When organizations are off, org-linked IDPs were already filtered out by the wrapper's `isEnabled`. `OrganizationAwareIdentityProviderBean` already applies an equivalent `BROKER_PUBLIC` check. I found no practical regression.
- **Model copying:** `CachedIdentityProvider` and the wrapper copy the config map (`new HashMap<>`), so a caller mutating the model cannot corrupt the cached or original view.
- **Org link/unlink and org removal:** These go through `update()`, where the wrapped `updated` model with a changed org id leads to correct invalidation.
- **`remove()`:** It uses the raw `idpDelegate.getByAlias`, which is correct. It does add an unconditional DB read, which is negligible.
- **`isEnabled()` re-check in `OrganizationAwareIdentityProviderBean.java:75` and `:80`:** This is needed and correct for the org-disabled case. It is not enough on its own (see finding 1).

### Coverage
- **Reviewed by OCR selection (3 of 3, 100%):**
  - `model/infinispan/.../InfinispanIdentityProviderStorageProvider.java`
  - `server-spi/.../IdentityProviderStorageProvider.java`
  - `services/.../OrganizationAwareIdentityProviderBean.java`
- **Excluded by OCR (`default_path`):** `testsuite/.../OrganizationCacheTest.java`. I read it anyway and reported finding 3; its assertions were not deeply validated.

### Unreviewed files
None. All 4 files in the patch were read.

Not done: nothing was compiled or tested, so finding 1 and the repro test are reasoned, not run. I did not check how Infinispan invalidation propagates across a cluster beyond `registerInvalidation`.
