What this change does: it lets users re-authenticate with a passkey (for example with `prompt=login`). It does this by running the conditional-passkey form setup when a user is already known, keeping the username hidden after a failed passkey attempt, and hiding the 2FA authenticator list in the conditional-UI authenticator. It also adds about 370 lines of Arquillian tests.

My seat covers over-engineering only, but findings 1 and 2 are outside that lane. I report them anyway because they come from the extra `user` parameter this patch adds, and they block shipping.

**Findings**

1. **Critical** (outside my lane), `services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernameForm.java:47`
   - **Claim:** The patch does not compile.
   - **Evidence:** `UsernameForm` calls `isConditionalPasskeysEnabled()` with no arguments. The only declaration is the one-argument `protected boolean isConditionalPasskeysEnabled(UserModel user)` at `UsernamePasswordForm.java:160`, and no zero-argument overload exists in `UsernameForm`, its parent `UsernamePasswordForm`, or `AbstractUsernameFormAuthenticator`. The second commit ("Add user parameter requirement…") changed the signature without updating this caller. Command that shows it: `grep -rn "isConditionalPasskeysEnabled" services/src/main/java`. It lists one one-argument declaration and the zero-argument call at UsernameForm:47, so `mvn -pl services compile` will fail. I did not run the build, as instructed.
   - **Fix:** Drop the parameter (see finding 3).

2. **Critical** (outside my lane, reasoned), `services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernamePasswordForm.java:160-162`, used at :115 and :137
   - **Claim:** On a normal first login the user is still unknown, so `user != null` is false. The passkey form data (`webauthnAuth.fillContextForm`) is then no longer set up.
   - **Evidence:** Before the patch, line 137 checked `context.getUser() == null && ...`. The patch flips this to require a non-null user. The existing test `PasskeysUsernamePasswordFormTest.passwordLoginWithExternalKey` (around line 195) expects `//form[@id='webauth']` on the first-login page, where no user is set yet. I reasoned this from the code and did not run it.
   - **Fix:** Drop the user check entirely: `webauthnAuth != null && webauthnAuth.isPasskeysEnabled()`.

3. **Important** (lean), `services/src/main/java/org/keycloak/authentication/authenticators/browser/UsernamePasswordForm.java:160-162`
   - **Claim:** The new `UserModel user` parameter is unneeded. Every caller that compiles passes `context.getUser()` (:115, :137), and the null check it enables is what causes finding 2. The parameter and the null check are the whole content of the second commit, and they cause both findings 1 and 2.
   - **Evidence:** See the grep in finding 1.
   - **Fix:** Use a method with no arguments, `webauthnAuth != null && webauthnAuth.isPasskeysEnabled()`. That fixes findings 1 and 2 together and removes code.

4. **Minor** (duplication), `services/src/main/java/org/keycloak/authentication/authenticators/util/AuthenticatorUtils.java:123-133`, plus `AbstractUsernameFormAuthenticator.java:58`
   - **Claim:** The new static helper copies the auth-note parsing that already lives in `AbstractUsernameFormAuthenticator.isUserAlreadySetBeforeUsernamePasswordAuth` (:257-260). It also copies the "hide username, disable registration" attribute pair from `UsernamePasswordForm.java:99-101`. The constant `USER_SET_BEFORE_USERNAME_PASSWORD_AUTH` was widened from `protected` to `public` only so this copy can read it.
   - **Evidence:** The same `getAuthNote(USER_SET_BEFORE_USERNAME_PASSWORD_AUTH)` plus `Boolean.parseBoolean` logic now exists in two places. If the note format ever changes, both must change together.
   - **Fix:** Make the util the single source. For example, put a static `isUserSetBeforeUsernamePasswordAuth(context)` in `AuthenticatorUtils`, have the protected method delegate to it, and keep the constant non-public.

5. **Minor** (test bloat), `testsuite/integration-arquillian/tests/base/src/test/java/org/keycloak/testsuite/webauthn/passwordless/PasskeysUsernamePasswordFormTest.java:289-295` and `:310-316`
   - **Claim:** Each of these blocks spends 7 lines on a hand-rolled try / `fail` / `catch (Exception)`. Inside it, `assertThat(..., nullValue())` can never pass, because `findElement` either throws or returns a non-null element, so that assertion is dead code.
   - **Evidence:** The same patch already uses the one-line form `Assert.assertThrows(NoSuchElementException.class, () -> driver.findElement(By.xpath("//form[@id='webauth']")))` in `PasskeysOrganizationAuthenticationTest` (the lines it replaces).
   - **Fix:** Use the one-liner in both places, saving about 12 lines.

6. **Minor** (test duplication), `PasskeysUsernamePasswordFormTest.java:214-276`
   - **Claim:** `webauthnLoginWithExternalKey_reauthentication` repeats the whole first half of `passwordLoginWithExternalKey` (:173-211) line for line. Its re-authenticate-with-passkey path is also covered by `webauthnLoginWithExternalKey_reauthenticationWithPasswordOrPasskey` (:338).
   - **Evidence:** In `PasskeysOrganizationAuthenticationTest` and `PasskeysUsernameFormTest`, the two new `webauthnLoginWithDiscoverableKey_reauthentication` tests are near copies of each other. The 5-line `events.expectLogin()...TYPE_PASSWORDLESS...` block also appears about 8 times across the new tests.
   - **Fix:** Delete the :214 test, or merge its first-login event check into :338. Optionally pull the passkey-login event assertion into a helper on `AbstractWebAuthnVirtualTest`. This saves about 60 lines.

7. **Minor** (churn), `PasskeysUsernamePasswordFormTest.java:149` and `:165`
   - **Claim:** These lines switch existing `Matchers.nullValue()` calls to a static `nullValue()` import. The change has no effect on behavior and only adds diff noise.

I checked these and found nothing to report:
- The `shouldShowWebAuthnAuthenticators` hook (`WebAuthnAuthenticator.java:124-130`, overridden in `WebAuthnConditionalUIAuthenticator.java:64-67`) is the smallest way to change behavior in this class hierarchy. The override only lacks an `@Override` annotation.
- The double `fillContextForm` I suspected does not happen: `authenticate` calls the two-argument `challenge` overload, not the three-argument one.

Verdict: fix 1 and 2 first (doing 3 fixes both).
Lean: about 75 lines could go, almost all in tests.

**Files not reviewed:** none. I reviewed all 9 files in the patch. I read the three test files for structure and duplication, not to check each assertion line by line.

Not checked: I could not compile or run tests (instructed not to). Finding 1 rests on grep, and finding 2 is reasoned from the code. I did not check how the FreeMarker login template renders `//form[@id='webauth']`.
