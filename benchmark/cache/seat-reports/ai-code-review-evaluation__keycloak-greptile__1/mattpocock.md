Code review (mattpocock-skills:code-review, both axes run inline with no sub-agents). Fixed point 30f804af45; commits under review: bba869b3d5 and 3214b188de.

## Findings

1. **services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernameForm.java:47** — **Critical** (Spec)
   - **Claim:** The patched code does not compile. `UsernameForm.authenticate` calls `isConditionalPasskeysEnabled()` with no arguments. Commit 3214b188de changed the only declaration to `isConditionalPasskeysEnabled(UserModel user)` (UsernamePasswordForm.java:160), and no overload with no arguments exists.
   - **Evidence:** `grep -rn isConditionalPasskeysEnabled --include=*.java .` returns three call sites (UsernameForm:47, UsernamePasswordForm:115 and :137) and one declaration (UsernamePasswordForm:160, which takes `UserModel`).
   - **Failing command:** `./mvnw -pl services -am compile -DskipTests`. Expected error: "method isConditionalPasskeysEnabled in class UsernamePasswordForm cannot be applied to given types".
   - **Spec breach:** The second commit says it "modifies the method signature to require a UserModel parameter" but leaves this caller unchanged.

2. **services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernamePasswordForm.java:160-161** (used at :115 and :137) — **Critical** (Spec)
   - **Claim:** `return webauthnAuth != null && webauthnAuth.isPasskeysEnabled() && user != null;` reverses the earlier behaviour.
     - Before the patch, passkey data was filled only when no user was selected: base :113 was inside the `else` (user == null) branch, and base `challenge` checked `context.getUser() == null`.
     - Now it is filled only when a user is already set. A first login to a realm with passkeys enabled no longer gets conditional-UI or webauthn data, so passkey login from the start page stops working. The fix for re-authentication breaks normal login.
   - **Evidence:** compare the base and head code of `authenticate` and `challenge(ctx, error, field)` in this file.
   - **Failing tests (once #1 is fixed):** `./mvnw -f testsuite/integration-arquillian/tests/base/pom.xml test -Dtest='PasskeysUsernamePasswordFormTest#passwordLoginWithExternalKey+webauthnLoginWithDiscoverableKey'`.
     - The first-login assertion `driver.findElement(By.xpath("//form[@id='webauth']"))` at PasskeysUsernamePasswordFormTest.java:196 should fail with NoSuchElementException.
     - Automatic discoverable-key login at :83 should fail too.
   - The new `_reauthentication` tests should also fail at their first-login step (:238).
   - This is reasoned from the code; I did not run it because builds are not allowed.

3. **UsernamePasswordForm.java:160 and UsernameForm.java:47** — **Important** (Spec)
   - **Claim:** The second commit says the new parameter gives "proper user context validation during conditional passkey checks". The method only checks that the user is not null; it never checks whether that user has a passkey (for example `user.credentialManager().isConfiguredFor(WebAuthnCredentialModel.TYPE_PASSWORDLESS)`).
   - **Result:** In a realm with passkeys enabled, a user who only has a password and re-authenticates (prompt=login):
     - gets the passkey form, and
     - in UsernameForm, no longer skips the username step.
   - **Evidence:** the test `reauthenticationOfUserWithoutPasskey` (PasskeysUsernamePasswordFormTest.java:276-279) has the comment "this user does not have passkey" and describes the case "Passkeys should not be shown during re-authentication". But it switches passkeys off for the whole realm (`setWebAuthnPolicyPasskeysEnabled(Boolean.FALSE)`), so the per-user case is never exercised and the gap is hidden.
   - This is reasoned. A failing test would be the same scenario with realm passkeys set to TRUE.

4. **services/src/main/java/org/keycloak/authentication/authenticators/util/AuthenticatorUtils.java:125-133** — **Minor** (Standards: possible duplicated code and layering)
   - **Claim:** `setupReauthenticationInUsernamePasswordFormError` repeats the auth-note parsing in `AbstractUsernameFormAuthenticator.isUserAlreadySetBeforeUsernamePasswordAuth` (AbstractUsernameFormAuthenticator.java:257-260).
   - To do that, the patch makes `USER_SET_BEFORE_USERNAME_PASSWORD_AUTH` public (AbstractUsernameFormAuthenticator.java:58, previously protected) and makes the generic `util` package statically import from `browser`.
   - This is a judgement call. CONTRIBUTING.md has no rule on it.

5. **services/src/main/java/org/keycloak/authentication/authenticators/browser/WebAuthnConditionalUIAuthenticator.java:64-67** — **Minor** (Standards, judgement call)
   - **Claim:** `shouldShowWebAuthnAuthenticators` overrides `WebAuthnAuthenticator.shouldShowWebAuthnAuthenticators` without `@Override`. The other overrides in the same file (:41 and :47) have it.
   - **Evidence:** `grep -n Override` on that file.

6. **testsuite/.../PasskeysUsernamePasswordFormTest.java:290-295 and :312-317** — **Minor** (Standards)
   - **Rule:** CONTRIBUTING.md says "Please write tests in the same way as we have written our tests."
   - **Claim:** The new tests check that an element is absent with `try { assertThat(findElement(...), nullValue()); fail(...) } catch (Exception)`. The existing suite uses `Assert.assertThrows(NoSuchElementException.class, () -> driver.findElement(...))`, as in the base PasskeysOrganizationAuthenticationTest.
   - The new tests also add `PasswordCredentialModel` and `Assert` imports, and `PasswordCredentialModel` looks unused in that file (reasoned, not compiled).

7. **Commit 3214b188de (whole change)** — **Minor** (Standards: CONTRIBUTING.md, "Submitting your PR" and "Developer's Certificate of Origin")
   - **Rules:** "One commit per PR" / "We require that you squash to a single commit"; contributors must "sign-off all commits with the `--signoff` option"; the commit message ends with "Closes #1234".
   - **Claim:** The change is two commits. The second has no `Signed-off-by` trailer and no issue link.
   - The first commit uses lowercase `closes` on two issues; CONTRIBUTING asks for the `Closes` format and discourages linking several issues.
   - **Evidence:** `git log 30f804af45..HEAD --format=%B`.

8. **Whole change** — **Minor** (Standards: CONTRIBUTING.md, "Includes documentation")
   - **Claim:** The change makes passkeys available during re-authentication (prompt=login) and changes the identity-first organization flow so passkeys stay enabled after the username is selected. No documentation was changed.
   - This is reasoned. I did not check whether existing docs already describe this.

## Files not reviewed
None. All 9 files in the patch were reviewed:
- AbstractUsernameFormAuthenticator.java
- UsernameForm.java
- UsernamePasswordForm.java
- WebAuthnAuthenticator.java
- WebAuthnConditionalUIAuthenticator.java
- AuthenticatorUtils.java
- PasskeysOrganizationAuthenticationTest.java
- PasskeysUsernameFormTest.java
- PasskeysUsernamePasswordFormTest.java

I read the test files for intent and rules. I did not trace every Selenium step.

## Axes that could not fully run
- **Spec:** There is no spec, and I did not fetch issues #41242 and #41008 (no tracker access). The commit messages and test comments/names served as the spec instead.
- **Standards:** The only documented standards are CONTRIBUTING.md and PR-CHECKLIST.md. They cover process and testing, not Java style (js/CODING_GUIDELINES.md covers only JS, which the patch does not touch). The style findings (4 and 5) are therefore judgement calls under the smell baseline.
- **Build and tests:** Nothing was compiled or run. The failure claims in findings 1 and 2 come from reading the code; the commands given should confirm them.

Not checked: OrganizationAuthenticator.java:360, which also calls `fillContextForm` and is outside the patch.
