Review seat: superpowers:requesting-code-review. The skill normally dispatches a reviewer subagent. The override said not to, so I did the review myself using the skill's reviewer template. I did not build or run anything, as instructed. Assumption: with no spec, the requirements are the commit titles and the intent stated in the new tests ("users can re-authenticate with passkeys, e.g. prompt=login; users without a passkey get no passkey UI during re-auth").

Verdict: **not ready to merge.** The patch does not compile, and once that is fixed the first-time passkey login it is meant to keep working is broken.

## Findings

1. **services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernameForm.java:47 — Critical**
   - **Claim:** The `services` module does not compile. `UsernameForm.authenticate` calls `isConditionalPasskeysEnabled()` with no arguments. The only definition is `protected boolean isConditionalPasskeysEnabled(UserModel user)` in UsernamePasswordForm.java:160, which the second commit ("Add user parameter requirement…") introduced. No overload with zero arguments exists.
   - **Evidence:** `grep -rn isConditionalPasskeysEnabled --include=*.java .` returns three call sites that pass `context.getUser()` (UsernamePasswordForm:115 and :137), this zero-argument call at UsernameForm:47, and the one-argument declaration at :160.
   - **Failing command (not run):** `./mvnw -pl services -am compile` should fail with "method isConditionalPasskeysEnabled in class UsernamePasswordForm cannot be applied to given types".
   - **Fix:** `!isConditionalPasskeysEnabled(context.getUser())`.

2. **services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernamePasswordForm.java:160-162 (used at :115 and :137) — Critical**
   - **Claim:** The `&& user != null` guard has the logic backwards. Before the patch, passkey data was filled only when the user was *not* yet identified (`context.getUser() == null`), which is the normal first login. Now `isConditionalPasskeysEnabled(null)` is false, so `webauthnAuth.fillContextForm(context)` never runs on a fresh login page or on the "invalid username" error page.
   - **Consequences:**
     - The page has no `webauth` form and no conditional-UI flag.
     - `AUTH_CHALLENGE_NOTE` is never set, so a passkey submitted to `action()` would be checked against a null or stale challenge.
     - Passkey login on the first visit to the username/password and username forms is gone. The patch fixes re-authentication by breaking authentication.
   - **Evidence:** compare the old condition `context.getUser() == null && webauthnAuth != null && webauthnAuth.isPasskeysEnabled()` (removed at old :137) with the new one at :161. The intended rule was almost certainly `currentUser == null || currentUser.credentialManager().isConfiguredFor(webauthnAuth.getCredentialType())`.
   - **Failing tests (not run; they need finding 1 fixed first):**
     - `PasskeysUsernamePasswordFormTest#passwordLoginWithExternalKey` asserts `//form[@id='webauth']` is present right after `oauth.openLoginForm()` (line 196).
     - `PasskeysUsernamePasswordFormTest#webauthnLoginWithDiscoverableKey` (:83) and `PasskeysUsernameFormTest#webauthnLoginWithDiscoverableKey` (:112) depend on conditional-UI auto-login on the first page.
     - The new `*_reauthentication` tests also fail at their first-login step before they reach re-authentication. Example: `PasskeysUsernameFormTest#webauthnLoginWithDiscoverableKey_reauthentication` expects `appPage.assertCurrent()` straight after `openLoginForm()`.
     - Command: `./mvnw -f testsuite/integration-arquillian/tests/base/pom.xml test -Dtest=PasskeysUsernamePasswordFormTest,PasskeysUsernameFormTest`.

3. **UsernamePasswordForm.java:161 together with WebAuthnConditionalUIAuthenticator.java:65-67 — Important**
   - **Claim:** During re-authentication, passkey UI is shown to users who have no passkey. That contradicts the stated intent of the new test `reauthenticationOfUserWithoutPasskey`: "Passkeys login should not be available on the page as this user does not have passkey".
   - **Why:**
     - `isConditionalPasskeysEnabled(user)` never checks the user's credentials.
     - The new `shouldShowWebAuthnAuthenticators` override returns false, which skips the old safeguard in `WebAuthnAuthenticator.fillContextForm` (:103-107): "if the user has no authenticators, return null".
   - **In UsernameForm (:47, once compiled with the user argument):** any already-identified user in a realm with passkeys enabled no longer takes the skip-the-form path. They get a form with the username hidden, even with no passkey.
   - **Evidence:** reasoned from the code above.

4. **testsuite/.../webauthn/passwordless/PasskeysUsernamePasswordFormTest.java:279-330 (`reauthenticationOfUserWithoutPasskey`) — Important (test gap)**
   - **Claim:** This test sets `setWebAuthnPolicyPasskeysEnabled(Boolean.FALSE)` (:282), so `isPasskeysEnabled()` is false and the passkey UI is hidden whatever the user has. It never covers the case its comment describes: passkeys enabled for the realm, user has no passkey. That is exactly the gap that hides finding 3.
   - **Evidence:** test body. A version with `PasskeysEnabled(TRUE)` would fail on the patched code at the second `//form[@id='webauth']` absence check (:313).

5. **WebAuthnConditionalUIAuthenticator.java:65 — Minor**
   - **Claim:** `shouldShowWebAuthnAuthenticators` overrides `WebAuthnAuthenticator.shouldShowWebAuthnAuthenticators` without `@Override`, unlike the other overrides in the same class (`fillContextForm` and `createErrorResponse` both have it).
   - **Evidence:** file lines 41, 47 and 64-67.

6. **services/src/main/java/org/keycloak/authentication/authenticators/util/AuthenticatorUtils.java:35 and :124-132; AbstractUsernameFormAuthenticator.java:58 — Minor**
   - **Claim:** The new helper repeats the logic of the existing `AbstractUsernameFormAuthenticator.isUserAlreadySetBeforeUsernamePasswordAuth` (:257-260) instead of reusing it.
   - **Claim:** It also makes the util package depend on a constant in the browser package, and widens that constant from `protected` to `public` only for this.
   - **Evidence:** diff hunks at those lines.

7. **PasskeysUsernamePasswordFormTest.java:290-296 and :311-317 — Minor**
   - **Claim:** The "element is absent" checks use `try { assertThat(findElement(...), nullValue()); fail(...) } catch (Exception)`. This works only because `AssertionError` is not an `Exception`, which makes the intent unclear. The sibling test PasskeysOrganizationAuthenticationTest already uses the clearer `Assert.assertThrows(NoSuchElementException.class, ...)`.
   - **Evidence:** the code at those lines.

Considered and set aside:
- `PasswordForm` now inherits `fillContextForm` on wrong-password errors, because the user is non-null there. `login-password.ftl` does not render passkey UI, so the only effect is a rewritten challenge note. Harmless.
- `OrganizationAuthenticator` uses its own `initialChallenge` with `user == null`, so finding 2 does not affect it.
- `IdpUsernamePasswordForm` has `webauthnAuth == null`, so it is unaffected.

## Files not reviewed
None. I reviewed all 9 files in the patch:
- AbstractUsernameFormAuthenticator.java
- UsernameForm.java
- UsernamePasswordForm.java
- WebAuthnAuthenticator.java
- WebAuthnConditionalUIAuthenticator.java
- AuthenticatorUtils.java
- PasskeysOrganizationAuthenticationTest.java
- PasskeysUsernameFormTest.java
- PasskeysUsernamePasswordFormTest.java

For the test files I checked their assertions against the patched behaviour. I did not run them.

Not checked: nothing was compiled or run, so findings 1 and 2 are backed by code reading and grep, not by observed failures. I also did not compare against the actual upstream Keycloak fix.
