I ran OCR delegate-review in range mode (`--from 30f804af45 --to HEAD`, merge_base 30f804af45). It found 9 files and marked 6 reviewable; it excluded the 3 testsuite files (`default_path`). I took the rules from `ocr delegate rule`, reviewed the code directly, and edited nothing. No builds or tests were run, so the findings below come from reading the code plus grep.

## Findings

1. **services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernameForm.java:47 — Critical. The patched code does not compile.**
   - **Claim:** `UsernameForm.authenticate` calls `isConditionalPasskeysEnabled()` with no arguments. The second commit ("Add user parameter requirement…") changed the only declaration to `protected boolean isConditionalPasskeysEnabled(UserModel user)` (UsernamePasswordForm.java:160). No no-arg overload exists anywhere, so `services` fails to compile with "method isConditionalPasskeysEnabled in class UsernamePasswordForm cannot be applied to given types".
   - **Evidence:** `grep -rn "isConditionalPasskeysEnabled" --include=*.java .` finds one declaration (UsernamePasswordForm.java:160, which takes a `UserModel`) and the zero-arg call site at UsernameForm.java:47.
   - **Failing command:** `mvn -pl services -DskipTests compile` (not run, by instruction).
   - **Fix:** `!isConditionalPasskeysEnabled(context.getUser())`.

2. **services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernamePasswordForm.java:160-162 (used at :115 and :137) — Critical. Conditional passkeys no longer work on a normal first-factor login.**
   - **Claim:** the new predicate is `webauthnAuth != null && webauthnAuth.isPasskeysEnabled() && user != null`. Before the patch, `fillContextForm` ran only when the user was not yet set (the `else` branch in `authenticate`, and `context.getUser() == null` in `challenge`). That is exactly the normal passkey login case. The new `user != null` clause reverses this: passkey setup now runs only during re-authentication.
   - **Consequences on a fresh login page:**
     - `ENABLE_WEBAUTHN_CONDITIONAL_UI` is not set, so `login.ftl:16` renders `autocomplete="username"` and `passkeys.ftl` renders no `webauth` form.
     - `AUTH_CHALLENGE_NOTE` is never stored, so a passkey assertion posted to `action()` cannot verify against a server challenge.
   - **Evidence:** the patch's own test contradicts the predicate. `PasskeysUsernamePasswordFormTest.passwordLoginWithNonDiscoverableKey` (testsuite/.../PasskeysUsernamePasswordFormTest.java:141-145) opens a fresh login form with no user and asserts `getUsernameAutocomplete()` is `"username webauthn"` and that `//form[@id='webauth']` exists. `webauthnLoginWithDiscoverableKey`, `passwordLoginWithExternalKey` (:195) and the reauth tests (:237, :359, initial login step) make the same assumption.
   - **Failing test:** `mvn -f testsuite/integration-arquillian/tests/base -Dtest=PasskeysUsernamePasswordFormTest test` would fail once finding 1 is fixed (not run). The same applies to `PasskeysUsernameFormTest` and `PasskeysOrganizationAuthenticationTest` for their first-login steps.
   - **Fix:** drop the `user != null` term. The re-authentication path already handles a set user through `shouldShowWebAuthnAuthenticators` returning false and through `USERNAME_HIDDEN`.

3. **services/src/main/java/org/keycloak/authentication/authenticators/util/AuthenticatorUtils.java:125-133 — Minor. The same check now exists twice.**
   - **Claim:** `setupReauthenticationInUsernamePasswordFormError` re-implements `AbstractUsernameFormAuthenticator.isUserAlreadySetBeforeUsernamePasswordAuth` (AbstractUsernameFormAuthenticator.java:257-260) by parsing the same auth note itself. To do that, it widens `USER_SET_BEFORE_USERNAME_PASSWORD_AUTH` from `protected` to `public` and makes the generic `util` package import from `browser`.
   - **Evidence:** both helpers do `Boolean.parseBoolean(authSession.getAuthNote(USER_SET_BEFORE_USERNAME_PASSWORD_AUTH))`. This is reasoned: there is no functional bug, only a risk that the two copies drift apart.

4. **services/src/main/java/org/keycloak/authentication/authenticators/browser/WebAuthnConditionalUIAuthenticator.java:65 — Minor. The override has no `@Override`.**
   - **Claim:** `shouldShowWebAuthnAuthenticators` overrides `WebAuthnAuthenticator.shouldShowWebAuthnAuthenticators` (WebAuthnAuthenticator.java:128) without the annotation. The sibling override `fillContextForm` (line 41) has it. If the parent signature is ever renamed, this override silently stops taking effect, and authenticators would then be listed on the conditional UI during re-authentication.
   - **Evidence:** reasoned, from the source.

## Files not reviewed

The three testsuite files below were excluded by OCR's `default_path` filter. I read them only as evidence for finding 2 and did not review them as changed code:
- testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/webauthn/passwordless/PasskeysOrganizationAuthenticationTest.java
- testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/webauthn/passwordless/PasskeysUsernameFormTest.java
- testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/webauthn/passwordless/PasskeysUsernamePasswordFormTest.java

Coverage: 6 of 6 reviewable files reviewed, 6 of 9 total. No spec was given, so there is no spec-gap analysis.

The fresh-login regression in finding 2 is reasoned from the code, the templates and the patch's own test assertions. I did not confirm it by running anything.
