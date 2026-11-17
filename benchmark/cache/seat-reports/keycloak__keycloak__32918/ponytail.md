Seat: advisory, over-engineering only (ponytail:ponytail-review, lean lens). Load assumed: a production IAM server with many concurrent logins. The login-page IDP lookup is the hot path, so adding a cache for it is justified and not over-engineering in itself.

What this change does: it caches the IDs of the identity providers that show on the login page, one cache entry per realm and FetchMode, keyed internally by org ID. The entry is invalidated on create, remove, and any update that changes whether an IDP qualifies for login or which org it belongs to. To support this, `getLoginPredicate` gains an org/broker-public clause, and the org-aware login bean checks `isEnabled()` again.

Findings:

1. model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/idp/InfinispanIdentityProviderStorageProvider.java:213-255 — Minor (lean: merge)
   - Claim: `getForLogin` copies `getByOrganization` (lines 167-211) almost line for line: the invalid-key bypass, the get/miss/add-search-key branches, `addRevisioned` with `startupRevision` or `getCurrentCounter`, and the resolve-by-id loop with its fallback on a missing ID. Only the cache key, the search key and the delegate call differ.
   - Evidence: compare the two blocks side by side. Any later fix to this caching algorithm, such as a race or revision handling, has to be made twice. The copies have already drifted: `getByOrganization` also bypasses when `isInvalid(orgId)` and `getForLogin` does not. That gap is harmless today, but it shows the two can diverge.
   - Smallest fix: one private helper, `Stream<IdentityProviderModel> cachedIdpList(String cacheKey, String searchKey, Supplier<Stream<IdentityProviderModel>> loader)`, called by both methods. That saves about 35 lines. This is reasoned; I ran no command.

2. model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/idp/InfinispanIdentityProviderStorageProvider.java:382-418 — Minor (lean: shorter form, merge)
   - Claim: `registerIDPLoginInvalidationOnUpdate` uses 28 lines, 12 of them a Javadoc that restates the code, for a single boolean condition. It also repeats the FetchMode invalidation loop from `registerIDPLoginInvalidation` (lines 385-387 vs 415-417), and it builds the stream-reduced predicate up to four times per update.
   - Evidence: the two early returns reduce to "invalidate iff `before != after || (before && !Objects.equals(orgBefore, orgAfter))`", where `before` and `after` are the predicate results for `original` and `updated`. The skip for "both qualify, same org" is deliberate and covered by test step 2 (idp-alias-0). It is also correct, because the cache stores only IDs and `getById` is invalidated separately. Keep the behaviour and shrink the code: compute `before` and `after` once, write one `if`, and move the loop into a shared `registerLoginCachesInvalidation()` that both methods call. That saves about 15 lines.

3. testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/organization/cache/OrganizationCacheTest.java:370-535 — Minor (lean: test duplication)
   - Claim: the 166-line test repeats the same "loop FetchMode and assertNull/assertNotNull" block five times (lines 393, 434, 458, 475, 511). It also repeats the same "run REALM_ONLY/ORG_ONLY/ALL and assert sizes" triple three times (lines 401-414, 482-497, 518-533).
   - Evidence: the blocks are identical apart from the expected sizes and null vs not-null. Two small static helpers, `assertLoginCaches(session, boolean present)` and `assertLoginCacheSizes(session, orgId, int realm, int org, int all)`, would cut it roughly in half. Caveat: I did not check whether `RunOnServer` lambdas in this testsuite can call static helpers on the test class. Many Keycloak tests do so, but I have not confirmed it here.
   - Also in this test: lines 381 and 425 register cleanup as `get("alias")::remove`, the literal string "alias" rather than the created alias. That cleanup does nothing. The pattern was copied from line 303, which predates this patch. This is out of my lane and not a lean issue, so I list it only for other seats.

Not lean findings, noted for other seats (I did not investigate them):
- server-spi/src/main/java/org/keycloak/models/IdentityProviderStorageProvider.java:254: the clause added to `getLoginPredicate` also changes `IdentityProviderBean.federatedProviderPredicate()` (services/src/main/java/org/keycloak/forms/login/freemarker/model/IdentityProviderBean.java:226). Private (non-broker-public) org IDPs that a user has already linked are now filtered out there. This is reasoned, and I have not verified whether it is intended.
- InfinispanIdentityProviderStorageProvider.java:100: `remove()` now calls `idpDelegate.getByAlias` on every remove, even when the cached model is available in the else branch. It costs one extra DB read on a rare admin operation, so it is minor at most.

Checked and not over-engineered: the `cacheKeyForLogin` public static helper (same pattern as `cacheKeyOrgId`, used by the test), the `isEnabled()` re-check in OrganizationAwareIdentityProviderBean.java:75 and :80 (needed because the cached path returns org-aware wrapped models whose enabled state depends on the org), and the predicate clause itself (needed so invalidation matches what the query returns).

Verdict (lean only): Ship. Nothing blocks.
Lean: about 85 lines removable (about 35 from 1, about 15 from 2, about 35+ in the test from 3).

Unreviewed files: none. All four files in the patch were reviewed, but only through the over-engineering lens. I did not check correctness, concurrency or cluster-invalidation behaviour in depth, and I ran no builds or tests, as benchmark mode requires.
