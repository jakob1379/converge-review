What this change does: when a user sets up recovery codes, Keycloak now asks the user's federated storage (for example LDAP or a custom provider) to store them first, and saves them in its own database only if that storage declines. The new `CredentialHelper.createRecoveryCodesCredential` does this, following the existing `createOTPCredential` pattern. Code lookup (`RecoveryAuthnCodesUtils.getCredential`) checks federated credentials first, then local ones. The test fixture `BackwardsCompatibilityUserStorage` gained recovery-code support, and there is one new end-to-end test.

Seat: over-engineering only. Load assumed: a normal multi-user Keycloak server. Most of the production code is lean and copies the OTP pattern. The extra code is in the test fixture and the test.

## Findings

1. **Important. The fixture now also returns OTP from `getCredentials`, which nothing asked for, and this changes what an existing test covers.**
   Where: `testsuite/integration-arquillian/servers/auth-server/services/testsuite-providers/src/main/java/org/keycloak/testsuite/federation/BackwardsCompatibilityUserStorage.java:247-249` (OTP branch in the new `getCredentials`) and `:179` (`newOTP.setId(KeycloakModelUtils.generateId())`).
   - Claim: recovery codes only need the recovery-codes entry in `getCredentials`. Adding OTP, plus a generated id for it, is scope creep. It also quietly reroutes the existing test `testOTPSetupAndRemoveThroughAccountMgmtAndLogin` (Issue 19575, test file around L301-335).
   - Before the patch, `getCredentials` came from the interface default and returned nothing. Account REST therefore built the placeholder credential "otp-id" (`AccountCredentialResource.java:211-219`, `CredentialHelper.createUserStorageCredentialRepresentation`). The delete then took the legacy `credentialId.endsWith("-id")` branch in `CredentialDeleteHelper.java:75-80`.
   - After the patch, the fixture returns a real OTP credential with a generated id. The same test now takes the federated-id branch (`CredentialDeleteHelper.java:63-70`).
   - Evidence: grep finds no other test that covers "otp-id" or `createUserStorageCredentialRepresentation`, and this fixture is the only testsuite provider that overrides `getCredentials`. So the placeholder path and the "-id" fallback silently lose their only test.
   - The class Javadoc (L59-62) says this provider is meant to stay compatible with 4.8.3 "without a need to change the code". The patch changes that 4.8.3-era OTP behavior anyway.
   - Fix: drop the OTP lines in `getCredentials` (-3 lines) and the `setId` line (-1 line).
   - Reasoned. I did not run tests, per instructions. To check: put a breakpoint or log in `CredentialDeleteHelper.removeCredential` and run `BackwardsCompatibilityUserStorageTest#testOTPSetupAndRemoveThroughAccountMgmtAndLogin` before and after the patch. The before run takes the "-id" branch and the after run takes the federated-id branch.

2. **Minor. The test helper `configureBrowserFlowWithRecoveryAuthnCodes` is copied from `RecoveryAuthnCodesAuthenticatorTest` along with unused machinery.**
   Where: `testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/federation/storage/BackwardsCompatibilityUserStorageTest.java:123-143`.
   - Claim: the copy keeps the `delay` parameter, which the only caller (L243) sets to 0. It keeps the `"delayed-authenticator"` execution, which exists for timing tests and does nothing here. It keeps the alias typo `"delayed-suthenticator-config"`. And it passes `testingClient` as a parameter even though it is already a field.
   - Evidence: compare with `testsuite/.../forms/RecoveryAuthnCodesAuthenticatorTest.java:123-143`. Only that original file uses non-zero delays (1000 at L371).
   - Fix: build the flow inline with only the username-password form plus the recovery-code authenticator, no parameters. That saves about 6 lines and one unrelated authenticator dependency.

3. **Minor. Helper parameters that never vary.**
   - Where: `BackwardsCompatibilityUserStorageTest.java:410` (`setupRecoveryKeysForUserWithRequiredAction(..., boolean logoutOtherSessions)`, only called with `true`, so the `uncheckLogoutSessions` branch at L423-425 never runs).
   - Where: `BackwardsCompatibilityUserStorageTest.java:456` (`assertUserHasRecoveryKeysCredentialInUserStorage(boolean)`, only called with `true`).
   - Claim: these parameters are speculative. Evidence: grep shows a single call site for each (L249, L253).
   - Fix: drop both parameters and the dead branch (about -4 lines).

4. **Minor. `enterRecoveryCodes` is a near copy of a helper in another test.**
   Where: `BackwardsCompatibilityUserStorageTest.java:476-483`, copied from `RecoveryAuthnCodesAuthenticatorTest.java:299`.
   - Evidence: same body. It is a private instance method in a different package, so it cannot be reused as is.
   - Acceptable for a test, and listed for completeness. If it is kept, `driver` and `enterRecoveryAuthnCodePage` are already fields, so those two parameters can go.

5. **Minor. Unrelated reformatting inflates the diff.**
   - Where: `server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java:76-85`, re-indent of `getConfigurableAuthenticatorFactory` with no logic change.
   - Where: `BackwardsCompatibilityUserStorage.java:61` (Javadoc `<p>`) and `:95` (whitespace).
   - Where: `BackwardsCompatibilityUserStorageTest.java`, the `.auth(accountToken)` re-indent (~L328) and the `TypeReference<>() {\n}` split (~L466).
   - Where: `services/src/main/java/org/keycloak/authentication/requiredactions/RecoveryAuthnCodesAction.java:5` (added blank import line).
   - Evidence: whitespace-only hunks in the patch. They make review and blame noisier and change no behavior. Drop them.

No over-engineering found in the production paths:
- `CredentialHelper.createRecoveryCodesCredential` copies `createOTPCredential`. The hard-coded provider id string matches the OTP helper, since the services-module factory constant cannot be reached from server-spi-private.
- `RecoveryAuthnCodesUtils.getCredential` is a 5-line helper used in two places.
- `RecoveryAuthnCodeInputLoginBean` and `RecoveryAuthnCodesFormAuthenticator` are one-line swaps.

Outside this seat, for whoever reviews correctness: when the credential comes from user storage, `RecoveryAuthnCodesFormAuthenticator` calls `removeStoredCredentialById(recoveryCodeCredentialModel.getId())` once all codes are used. For a federated credential that call cannot remove anything. In the fixture, `RecoveryAuthnCodesCredentialModel.createFromValues` also builds the model without setting an id, so the call gets `null`. The fixture also never marks codes as used, so every login asks for code #1. I did not dig further.

Verdict: fix 1 first. The rest is lean cleanup in tests.
Lean: about -15 lines possible.

## Skipped files
None. All 8 files in the patch were reviewed:
- `server-spi-private/.../utils/CredentialHelper.java`
- `server-spi/.../models/utils/RecoveryAuthnCodesUtils.java`
- `services/.../browser/RecoveryAuthnCodesFormAuthenticator.java`
- `services/.../requiredactions/RecoveryAuthnCodesAction.java`
- `services/.../freemarker/model/RecoveryAuthnCodeInputLoginBean.java`
- `testsuite/.../federation/BackwardsCompatibilityUserStorage.java`
- `testsuite/.../federation/BackwardsCompatibilityUserStorageFactory.java`
- `testsuite/.../federation/storage/BackwardsCompatibilityUserStorageTest.java`

Not checked: no builds or tests were run, per instructions, so finding 1 is reasoned from the code paths and not shown by a failing run.
