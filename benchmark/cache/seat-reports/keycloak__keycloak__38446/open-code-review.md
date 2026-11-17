## Review: ce2dcc537b "Create recovery keys in user storage or local"

I ran OCR delegate in commit mode and used its Java rule set. I reviewed the whole patch with surrounding source as context. I edited nothing. No spec was given, so I measured the change against existing SPI contracts and the documented intent of the files it touches. I ran no builds or tests, so every finding below is reasoned from the code, not observed in a run.

### Findings

**1. Important. `server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java:125-130`**
- **Claim:** When user storage accepts the new codes, the old local recovery-codes credential is never deleted, and its codes still log the user in.
- **Evidence:**
  - Only the local branch calls `RecoveryAuthnCodesCredentialProvider.createCredential`. That method (services/.../credential/RecoveryAuthnCodesCredentialProvider.java:36-41) is the only place that deletes the previous credential. The federated branch at line 125 returns without any cleanup.
  - At login, `UserCredentialManager.isValid` (model/storage/.../UserCredentialManager.java:59-80) asks the federated validator first. If that fails, it falls through to the local `RecoveryAuthnCodesCredentialProvider.isValid`, which checks the old stored credential.
  - That validator only compares against the old credential's next unused code. It ignores which code number the form asked for. So an old code still works after the user regenerates.
  - This is the normal upgrade path. Before this patch, every federated user's codes were stored locally (in fed-storage). The first regeneration after upgrading goes to the provider and leaves the old codes valid. Users who regenerate because their codes leaked stay exposed.
- **Test sketch (not run):** In `BackwardsCompatibilityUserStorageTest`:
  - Create a local recovery-codes credential for a `BackwardsCompatibilityUserStorage` user via `testingClient.server().run(s -> user.credentialManager().createStoredCredential(RecoveryAuthnCodesCredentialModel.createFromValues(oldCodes, ...)))`.
  - Run `setupRecoveryKeysForUserWithRequiredAction`.
  - Log in through the recovery-codes flow, entering `oldCodes.get(0)`.
  - Expected: invalid code. Predicted on the patched code: `appPage.assertCurrent()` passes.

**2. Important. `server-spi/src/main/java/org/keycloak/models/utils/RecoveryAuthnCodesUtils.java:56-61`, used at `RecoveryAuthnCodesFormAuthenticator.java:80` and `RecoveryAuthnCodeInputLoginBean.java:17`**
- **Claim:** Recovery-code login now calls the user storage provider's `getCredentials` for every federated user, including LDAP users. This adds a remote round trip, and the LDAP provider can throw.
- **Evidence:**
  - `getFederatedCredentialsStream()` calls `CredentialInputUpdater.getCredentials` on the storage provider (UserCredentialManager.java:130-145).
  - `LDAPStorageProvider.getCredentials` (federation/ldap/.../LDAPStorageProvider.java:1211-1215) runs an LDAP search. If the LDAP entry is missing, it throws `IllegalStateException`.
  - Before this patch, recovery-code login for imported LDAP users read only the local DB.
  - Now each challenge renders the login bean (one LDAP query) and each submit runs the authenticator (another). An imported user whose LDAP entry is gone hits an unhandled exception instead of using their local codes.
  - The code queries LDAP for a credential type LDAP never supports. A guard such as checking that the storage provider `supportsCredentialType(TYPE)` before `getFederatedCredentialsStream` would avoid this. This is reasoned; I wrote no failing test.

**3. Important. `testsuite/.../federation/BackwardsCompatibilityUserStorage.java:230-250` (new `getCredentials` override)**
- **Claim:** The patch weakens the backwards-compatibility coverage this provider exists to give, including the Issue 19575 regression test.
- **Evidence:**
  - The class Javadoc (line 59) says this provider mimics a Keycloak 4.8.3 provider and should need no code changes in future versions. A 4.8.3 provider does not implement `getCredentials`.
  - Before this patch, the default empty stream made `AccountCredentialResource` (lines 212-219) build the dummy "otp-id" representation. `CredentialDeleteHelper` (lines 71-77) then deleted it through the `"-id"` backwards-compat branch.
  - Now the override returns the real OTP model, with an id added by the new `setId` at line 179. So `testOTPSetupAndRemoveThroughAccountMgmtAndLogin` (test line 302, "Issue 19575") goes through the `getFederatedCredentialsStream` branch instead.
  - I grepped the testsuite for `otp-id` and other `getCredentials(RealmModel` overrides and found no other test that covers the placeholder path. It is now untested.
  - The patch also adds `var` and post-4.8.3 APIs (`RecoveryAuthnCodesCredentialModel`, `KeycloakModelUtils`), which goes against the same Javadoc.
  - A separate test provider for recovery codes would keep this one intact. This is reasoned.

**4. Minor. `CredentialHelper.java:123` and `RecoveryAuthnCodesUtils.java:56-61`**
- **Claim:** The SPI contract for storing recovery codes in user storage is asymmetric and documented nowhere.
- **Evidence:**
  - `updateCredential` receives the raw plaintext codes as a JSON list in `challengeResponse`.
  - `getCredentials` must return a model in Keycloak's internal hashed `RecoveryAuthnCodesCredentialModel` JSON format. Otherwise `createFromCredentialModel` in the authenticator and login bean fails, and `RecoveryAuthnCodeInputLoginBean` calls `.get()` on the next code.
  - Consuming used codes is left entirely to the provider's `isValid`. Core never enforces single use for federated codes.
  - The `generatedAt` and `userLabel` values are dropped and never reach the provider.
  - The patch adds no docs or Javadoc for provider authors.

**5. Minor. `BackwardsCompatibilityUserStorage.java:325-340` and `BackwardsCompatibilityUserStorageTest.java:259, 481`**
- **Claim:** The reference provider accepts any of the 12 codes, regardless of which number was requested, and never uses one up. So the new test checks neither single-use nor "next code" behaviour. It always expects code #0.
- **Evidence:** `generatedKeys.stream().anyMatch(key -> key.equals(input.getChallengeResponse()))`, with no state change after a successful match.

**6. Minor. `RecoveryAuthnCodesFormAuthenticator.java:80-88`**
- **Claim:** The authenticator now takes the `allCodesUsed` decision from the federated model whenever one exists.
- **Evidence:**
  - When the provider reports all codes used, the code calls `removeStoredCredentialById(federatedId)` against local or fed storage. That does nothing to the provider's copy. Only adding the required action has an effect.
  - When the old local credential is the one being used up (see finding 1), its exhaustion is never seen or cleaned up, because `getCredential` returns the federated model.

**7. Minor. `BackwardsCompatibilityUserStorage.java:231-237`**
- **Claim:** The `getCredentials` override has two defects.
- **Evidence:**
  - `getMyUser(user)` is dereferenced without a null check. `getDisableableCredentialTypesStream` in the same file does check for null.
  - The returned recovery-codes model has a null id, because `createFromValues` does not copy the id generated at line 196. The account REST and `CredentialDeleteHelper` delete-by-id cannot find it.
  - `disableCredentialType` was not extended for recovery codes, so removing them from the account console silently does nothing.

### Coverage
- 8 files in the patch, 8 reviewed, 0 skipped. Coverage is 100%.
- OCR left `testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/federation/storage/BackwardsCompatibilityUserStorageTest.java` out of its reviewable list (`default_path`), but I reviewed it from the patch anyway.
- I left out the whitespace-only changes: the re-indent in `CredentialHelper.getConfigurableAuthenticatorFactory`, the Javadoc `<p>`, and the test formatting.
- I did not check: whether the new test actually passes, or how imported-LDAP users behave at runtime when LDAP is unreachable.
