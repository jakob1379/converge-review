## Review: ce2dcc537b "Create recovery keys in user storage or local" (base 85737f52b5)

No spec was supplied, so I reviewed for correctness, security, and conformance to the existing SPI contracts. I ran no builds or tests. Every finding below is reasoned from the source; none was executed.

### Findings

**1. `server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java:125-130`: Important (security). Regenerating codes into user storage leaves the old local codes valid.**
- **Claim:** When `updateCredential` succeeds in user storage, the method returns without touching the existing local `recovery-authn-codes` credential. The local path, `RecoveryAuthnCodesCredentialProvider.createCredential` (services/.../credential/RecoveryAuthnCodesCredentialProvider.java:39-42), deletes the previous local credential first; the storage path does not.
- **Why the old codes still work:** `UserCredentialManager.isValid` (model/storage/.../UserCredentialManager.java:66-77) asks the storage validator first. If storage returns false, it falls through to the local `RecoveryAuthnCodesCredentialProvider.isValid`. So any user who had local codes before their storage provider supported this type can still log in with an old code after "regenerating".
- **Second effect, same file:** `RecoveryAuthnCodesFormAuthenticator.java:80` (`RecoveryAuthnCodesUtils.getCredential`) prefers the federated credential. In this mixed state the authenticator inspects or removes a different credential from the one that actually validated.
- **Failing test (outline, not run):** in `BackwardsCompatibilityUserStorageTest`:
  1. Create a user.
  2. Inject a local credential with `testingClient.server().run(s -> user.credentialManager().createStoredCredential(RecoveryAuthnCodesCredentialModel.createFromValues(oldCodes, now, null)))`.
  3. Run `setupRecoveryKeysForUserWithRequiredAction`.
  4. Log in with `oldCodes.get(0)`. The patched code lets this login succeed; it should be rejected.
- **Fix direction:** on the storage branch, remove any local credential of this type.

**2. `services/src/main/java/org/keycloak/forms/login/freemarker/model/RecoveryAuthnCodeInputLoginBean.java:17-21` (also `RecoveryAuthnCodesFormAuthenticator.java:80-84`): Important. The login page breaks for any storage provider that supports the type but does not mirror Keycloak's internal credential format.**
- **Claim:** Once a provider's `supportsCredentialType`/`updateCredential` accept `recovery-authn-codes`, `isConfiguredFor` reports the user as configured through storage, and the recovery-code form is rendered.
- **Case A, no `getCredentials` override:** the bean calls `credentialModelOpt.get()` on `RecoveryAuthnCodesUtils.getCredential(user)`. If the provider doesn't override `CredentialInputUpdater.getCredentials`, the default returns `Stream.empty()` (server-spi/.../CredentialInputUpdater.java:50). Nothing is stored locally either, so `get()` throws `NoSuchElementException` and the page returns 500.
- **Case B, wrong format:** `createFromCredentialModel` throws `RuntimeException` unless the provider returns `credentialData`/`secretData` in Keycloak's internal hashed format (`RecoveryAuthnCodesCredentialData`/`RecoveryAuthnCodesSecretData`).
- **Undocumented contract:** what storage receives is a JSON list of plaintext codes (`CredentialHelper.java:123`), but what it must return is Keycloak's internal hashed structure. Neither the javadoc of `CredentialHelper.createRecoveryCodesCredential` nor `CredentialInputUpdater` documents this asymmetric contract.
- **Contrast:** the authenticator handles an empty Optional (lines 90-92); the bean does not.
- **Status:** reasoned, no test run.

**3. `server-spi-private/src/main/java/org/keycloak/utils/CredentialHelper.java:123`: Minor.**
- The storage path sends only the codes. The user label and `generatedAt` from `credentialModel` are dropped, so the storage-backed credential loses metadata that the local path keeps.

**4. `testsuite/.../federation/BackwardsCompatibilityUserStorage.java:340` and `testsuite/.../storage/BackwardsCompatibilityUserStorageTest.java:241-262`: Minor (test gap).**
- The fixture accepts any of the 12 codes, in any order, and never consumes them.
- The new test performs exactly one login, so single-use is not exercised for the federated path. Neither is the "code #N" prompt, which the bean derives from the provider's model and which never advances here.
- The core delegates single-use enforcement entirely to the storage provider, and nothing in the change states that.

**5. `testsuite/.../federation/BackwardsCompatibilityUserStorage.java:217-224, 231-248, 255-263`: Minor (fixture correctness).**
- `getCredentials` rebuilds the model with `createFromValues`, which discards the stored credential id (the id is null).
- It dereferences `myUser` without a null check at line 235. Before this change, the default `getCredentials` returned an empty stream.
- Neither `disableCredentialType` nor `getDisableableCredentialTypesStream` handles recovery codes.
- Net effect: deleting the federated recovery-codes credential through the account console would fail. `CredentialDeleteHelper` matches on `credentialId.equals(c.getId())` against a null id and throws `NotFoundException`. No test covers removal.

**Checked and found fine:** the new `getCredentials` override also exposes the fixture's OTP credential to account REST. The patch adds `setId` on OTP, and `CredentialDeleteHelper` resolves federated ids through `getFederatedCredentialsStream`. The legacy `writeProperty` JSON looks deserializable as `OTPCredentialData`. I see no regression in `testOTPSetupAndRemoveThroughAccountMgmtAndLogin`, but I did not run it.

### Skipped files
None. All 8 files in the patch were reviewed:
- `server-spi-private/.../utils/CredentialHelper.java`
- `server-spi/.../models/utils/RecoveryAuthnCodesUtils.java`
- `services/.../RecoveryAuthnCodesFormAuthenticator.java`
- `services/.../RecoveryAuthnCodesAction.java`
- `services/.../RecoveryAuthnCodeInputLoginBean.java`
- `testsuite/.../BackwardsCompatibilityUserStorage.java`
- `testsuite/.../BackwardsCompatibilityUserStorageFactory.java`
- `testsuite/.../BackwardsCompatibilityUserStorageTest.java`

I left out the whitespace and indentation reformatting in `CredentialHelper` and the test file, as instructed: it is a generic smell, not a finding.

Not checked: LDAP mappers that might add `recovery-authn-codes` to `getSupportedCredentialTypes` (I didn't trace mapper code), and the git history (the partial clone could not fetch history).
