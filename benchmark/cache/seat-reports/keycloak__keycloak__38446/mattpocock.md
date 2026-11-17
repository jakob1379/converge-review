## Review: keycloak 85737f52b5..ce2dcc537b ("Create recovery keys in user storage or local")

I reviewed all 8 files in the patch myself, covering both axes and with no sub-agents. The standards I checked against are CONTRIBUTING.md, PR-CHECKLIST.md, docs/tests-development.md and docs/pull_request_template.md. I did not run any builds or tests, so every finding below is reasoned from the code and none comes with a failing command.

## Standards

1. **Commit message (no file:line) — Important.** The commit message has no issue link.
   - **Rule:** CONTRIBUTING.md:26 and :96-97 say "We also require that the commit message includes a link to the issue", and :115-125 say the message should end with `Closes #1234`. PR-CHECKLIST.md:6 requires a linked GitHub issue for new features or enhancements, which this is.
   - **Evidence:** `git log -1 --format=%B HEAD` contains only the subject and `Signed-off-by: rtufisi <rtufisi@phasetwo.io>`. There is no `Closes #`.

2. **Documentation (whole patch) — Important.** There are no docs, release-notes or upgrade-guide changes.
   - **Rule:** CONTRIBUTING.md:29 and :79 ("We require contributions to include relevant documentation"), and PR-CHECKLIST.md:9 ("Including updates to release notes and upgrade guide if applicable").
   - **Evidence:** All 8 files are Java and none is under `docs/`. The User Storage SPI contract changes in a way custom providers can see. If a provider's `supportsCredentialType` returns true for `recovery-authn-codes`, `updateCredential` now receives a `UserCredentialModel` whose challenge response is the plaintext JSON list of recovery codes (server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java:117-123). The local store keeps those codes hashed. Federated credentials are now also read first (server-spi/src/main/java/org/keycloak/models/utils/RecoveryAuthnCodesUtils.java:56-62). Provider authors need to be told both things, especially that they get plaintext secrets.

3. **Unrelated reformatting — Minor.**
   - **Rule:** CONTRIBUTING.md:27 and :66-68 ("Do not format or refactor code that is not directly related to your contribution").
   - **Evidence, whitespace-only re-indent:** server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java:76-85, the whole of `getConfigurableAuthenticatorFactory`.
   - **Evidence, BackwardsCompatibilityUserStorage.java** (testsuite/integration-arquillian/servers/auth-server/services/testsuite-providers/src/main/java/org/keycloak/testsuite/federation/):
     - :61, javadoc `*` changed to `* <p>`
     - :95, double space removed
     - removed imports that were unused (`Collectors`, `Pbkdf2Sha512PasswordHashProviderFactory`)
   - **Evidence, BackwardsCompatibilityUserStorageTest.java** (testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/federation/storage/):
     - :328, re-indented
     - :467-468, `new TypeReference<>() {}` split over two lines
   - **Evidence, RecoveryAuthnCodesAction.java:5:** a blank line added in the import block.

4. **BackwardsCompatibilityUserStorageTest.java:481 — Minor.** The new helper uses `org.junit.Assert.assertEquals(...)`, written as a fully qualified name.
   - **Rule:** docs/tests-development.md says "use `org.hamcrest.MatcherAssert.assertThat` where possible ... Please avoid as much to use set of assertions from `org.junit.Assert.*`".
   - **Evidence:** :462 does the same through `org.keycloak.testsuite.Assert`, which extends `org.junit.Assert` (testsuite/.../Assert.java:51). The file already used that style, so this one is a judgement call.

5. **BackwardsCompatibilityUserStorage.java:58-60 — Minor (judgement call).** The class's own javadoc says it is a 4.8.3-era provider and "Future Keycloak versions should work fine without a need to change the code of this provider".
   - **Evidence:** The patch adds features to it: a new `getCredentials` override (:231-252), `var`, and new recovery-code branches. This weakens what the backwards-compatibility test actually covers. A separate test provider would keep that coverage intact.
   - **Mitigation:** The file was already edited in March 2024 (commits c3a98ae387 and 8cbd39083e), so the rule is not strictly followed in practice.

Things I checked and found fine:
- Single commit, signed off (CONTRIBUTING.md:89, :104-111).
- It includes an Arquillian integration test (CONTRIBUTING.md:28), with no mocking framework added (:74).

## Spec

There is no spec: no issue reference and no spec file. I judged the change only against its commit subject, "Create recovery keys in user storage or local". That is implemented:
- `CredentialHelper.createRecoveryCodesCredential` tries `user.credentialManager().updateCredential` first and falls back to the local `keycloak-recovery-authn-codes` provider.
- The local `RecoveryAuthnCodesCredentialProvider` does not implement `CredentialInputUpdater`, so a local user cannot be caught by the first branch by mistake.
- The read paths prefer federated credentials: `RecoveryAuthnCodesFormAuthenticator` and `RecoveryAuthnCodeInputLoginBean` now call `RecoveryAuthnCodesUtils.getCredential`.

Correctness gap for the correctness reviewer (reasoned, outside my remit). For a federated recovery-codes credential, nothing tells user storage that a code has been used. The local `isValid` (RecoveryAuthnCodesCredentialProvider.java:99-117) removes the used code via `updateStoredCredential`. On the federated path:
- `RecoveryAuthnCodesFormAuthenticator.java:85-87` calls `removeStoredCredentialById` (local store only) when all codes are used.
- The test provider accepts any stored code, every time (BackwardsCompatibilityUserStorage.java:326-341).

So recovery codes held in user storage look reusable, and the new test (`testRecoveryKeysSetupAndLogin`) only checks a single login.

**Summary:** 5 Standards findings; the worst are the missing `Closes #` issue link and the missing docs for a User Storage SPI change that now hands providers plaintext recovery codes (both Important). For Spec, there was no spec and nothing missing against the commit subject.

## Skipped files

None. All 8 files in the patch were reviewed:
- server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java
- server-spi/src/main/java/org/keycloak/models/utils/RecoveryAuthnCodesUtils.java
- services/src/main/java/org/keycloak/authentication/authenticators/browser/RecoveryAuthnCodesFormAuthenticator.java
- services/src/main/java/org/keycloak/authentication/requiredactions/RecoveryAuthnCodesAction.java
- services/src/main/java/org/keycloak/forms/login/freemarker/model/RecoveryAuthnCodeInputLoginBean.java
- testsuite/integration-arquillian/servers/auth-server/services/testsuite-providers/src/main/java/org/keycloak/testsuite/federation/BackwardsCompatibilityUserStorage.java
- testsuite/integration-arquillian/servers/auth-server/services/testsuite-providers/src/main/java/org/keycloak/testsuite/federation/BackwardsCompatibilityUserStorageFactory.java
- testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/federation/storage/BackwardsCompatibilityUserStorageTest.java

Not checked: the upstream GitHub issue, because the network was blocked. I also did not look at the docs/documentation user-storage pages in depth.
