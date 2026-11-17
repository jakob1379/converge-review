Review seat: advisory, covering spec compliance and documented standards. I applied mattpocock-skills:code-review directly, on both axes, without sub-agents.

Inputs:
- Fixed point: f3c8e8f3, head 02f48f77. The diff covers 48 files (+343/−105) and matches change.patch.
- There is no spec. The only statement of intent is the commit message: "Add a HTML sanitizer for translated message resources / Closes #37428". I did not fetch issue #37428.
- Standards sources: CONTRIBUTING.md, PR-CHECKLIST.md, docs/translation.md, docs/dependency-license-information.md, plus the conventions already in each touched file.
- I did not build or run anything. Every grep below works on the patched tree.

## Spec axis

1. **js/apps/account-ui/maven-resources/theme/keycloak.v3/account/messages/messages_en.properties:188 and js/apps/admin-ui/maven-resources/theme/keycloak.v2/admin/messages/messages_en.properties:3138 — Important**
   - **Claim:** This hunk is out of scope, and it breaks the error message in the React UIs. `error-invalid-multivalued-size` changed from i18next placeholders (`{{0}}`, `{{1}}`, `{{2}}`) to Java MessageFormat (`{0}` plus `{2,choice,0#values|1#value|1<values}`).
   - **Evidence:**
     - Both apps load these bundles into plain i18next (`js/apps/account-ui/src/i18n.ts`, `js/apps/admin-ui/src/i18n/i18n.ts`). Neither has an ICU plugin (no `i18next-icu` in package.json).
     - `ThemeResource.getLocalizationTexts` passes values through without converting them.
     - `setUserProfileServerError` in `js/libs/ui-shared/src/user-profile/utils.ts:73-84` calls `t(key, {0:…,1:…,2:…})`. With the new text it will show `{0}` and the raw `{2,choice,…}` text.
     - Every other `error-*` key in the same file still uses `{{N}}`, and so do all the community translations of this key: `grep -rn '^error-invalid-multivalued-size' js/apps/*/maven-resources-community` shows `{{0}}` in pl, nl, hr, ka and pt.
     - The change has nothing to do with HTML sanitising. It also forced the special case `|| key.equals("error-invalid-multivalued-size")` into `VerifyMessageProperties.java:124`.
   - **How to confirm:** this is reasoned and I did not run it. An i18next test such as `i18n.t('error-invalid-multivalued-size', {0:'a',1:1,2:2})` would return the literal `{0}` text.

2. **themes/src/main/resources-community/theme/base/account/messages/messages_lt.properties:101 and themes/src/main/resources-community/theme/base/login/messages/messages_lt.properties:71 — Important**
   - **Claim:** The Lithuanian `totpStep1` and `loginTotpStep1` were replaced with Italian text: "Installa una delle seguenti applicazioni sul tuo cellulare:". Lithuanian users now see Italian.
   - **Evidence:** `grep -n '^totpStep1=\|^loginTotpStep1=' themes/src/main/resources-community/theme/base/*/messages/messages_lt.properties`. The lines around them (totpStep2/3) are still Lithuanian. Compare with `messages_it.properties:138` and login `messages_it.properties:92`.

3. **themes/src/main/resources-community/theme/base/account/messages/messages_zh_CN.properties:112 — Important**
   - **Claim:** The Simplified Chinese file got a Traditional Chinese string: `在您的手機上安裝以下應用程式之一：`.
   - **Evidence:** Line 111 of the same file is `mobile=手机` (Simplified), and lines 113-114 are Simplified (`打开应用扫描二维码`). The text that went in is zh_TW wording.
   - **Note on findings 2 and 3:** CONTRIBUTING.md says "No changes to code not directly related to your PR". docs/translation.md says "Translate text accurately… Maintain consistency" and that language maintainers approve translations.

4. **misc/theme-verifier/src/main/java/org/keycloak/themeverifier/VerifyMessageProperties.java:124-126 — Minor (reasoned)**
   - **Claim:** The sanitiser can be bypassed for the allowlisted keys (`linkExpirationFormatter.timePeriodUnit*` and `error-invalid-multivalued-size`). Any `{N,choice,…}` block is replaced with `...` before sanitising, so a translation like `{0,choice,0#<img src=x onerror=…>|1#x}` passes.
   - **Impact:** Limited. Runtime `kcSanitize` still covers email bodies, but the build-time check does not do what it says for these keys.

5. **VerifyMessageProperties.java:92-99 — Minor (reasoned)**
   - **Claim:** The check compares the value to the sanitiser's re-serialised output, not to "nothing was removed". Formatting that means the same thing fails the build, so `<br/>`, `</ b>`, `</p >` and `< p>` are all rejected.
   - **Evidence:** This is why about 25 files in the patch are mechanical `<br/>` → `<br />` rewrites. Weblate translators will keep hitting these failures.

6. **VerifyMessageProperties.java:150-160 — Minor**
   - **Claim:** Anchors are matched by position against the English string, so a translation that legitimately puts two links in a different order fails. The pattern `</?a[^>]*>` also matches `<abbr>`, `<area>` and `<audio>`, though the effect is only extra false positives.

7. **VerifyMessageProperties.java:157 — Minor**
   - **Claim:** The "Didn't find anchor tag … in original string" error leaves out the key and the file. Every other error from this class names the file (lines 111 and 194). A build failure from this check can't be located.

8. **themes/src/main/resources-community/theme/base/login/messages/messages_sk.properties:501 — Minor**
   - **Claim:** This changes the second `{1,choice…}` to `{2,choice…}`. It is a correct bug fix but has nothing to do with HTML (scope creep, per CONTRIBUTING "No changes to code not directly related").

## Standards axis

9. **docs/translation.md (not touched by the patch), rule introduced at VerifyMessageProperties.java:58-63 and 90-91 — Minor**
   - **Claim:** CONTRIBUTING.md requires "Includes documentation". The new rules for translators are not written down anywhere translators look:
     - HTML is allowed only where the English string has HTML.
     - Only `br`, `p`, `strong` and `b` are allowed.
     - Anchors must be byte-identical to the English ones.
   - **Evidence:** `grep -i html docs/translation.md` returns nothing.

10. **VerifyMessageProperties.java:70 and :79 — Minor**
    - **Claim:** Read failures throw `RuntimeException`. The surrounding `verify()` wraps I/O failures in `MojoExecutionException` (line 53), and the change breaks that pattern.
    - **Example:** A message file with no `_en` sibling crashes the mojo with a raw exception. The old `duplicate_keys.properties` fixture had to be renamed because of this.

11. **VerifyMessageProperties.java:58, 63, 139 vs 145 — Minor (judgement)**
    - **Claim:** `POLICY_SOME_HTML`, `POLICY_NO_HTML` and `HTML_TAGS` use constant-style names but are package-private, non-static instance fields. `ANCHOR_PATTERN` in the same change is `private static final`, so the constants are inconsistent.

12. **VerifyMessageProperties.java:150 and :164 — Minor (judgement: possible Mysterious Name / dead parameter)**
    - **Claim:** `santizeAnchors` is a typo, as is "numberic" at :94. The `key` parameter is unused in both `santizeAnchors` and `getEnglishValue`.

13. **VerifyMessageProperties.java:58, 63, 95, 130 — Minor**
    - **Claim:** `org.owasp.html.HtmlPolicyBuilder` and `org.apache.commons.text.StringEscapeUtils` are written out in full inline, while `PolicyFactory` is imported. This doesn't match the file's import style.

14. **VerifyMessageProperties.java:132 — Minor**
    - **Claim:** Email files are detected with `file.getAbsolutePath().contains("email")`. A checkout path containing "email" would apply the RTL-style stripping to every file. A `TODO` is also left in the code.

15. **misc/theme-verifier/pom.xml:75-85 — Minor**
    - **Claim:** The owasp sanitizer version `20240325.1` is hard-coded, duplicating the root `pom.xml:119` `owasp.html.sanitizer.version` property, so the two can drift.
    - **Context:** This module is standalone (no parent) and already hard-codes commons-io, so the patch follows the module's own convention.
    - **Licensing:** The plugin is build-time only (deploy is skipped), so docs/dependency-license-information.md does not apply.

16. **misc/theme-verifier/src/test/java/org/keycloak/themeverifier/VerifyMessagePropertiesTest.java:33 — Minor**
    - **Claim:** The duplicate-keys assertion was weakened from `contains` (exactly one message) to `hasItem`.
    - **Missing test:** Nothing checks the case with no false positives, for example a valid translation with allowed `<b>` or an identical anchor producing no messages. The real resources are the only check of that.
    - **Sloppy fixture:** `illegalHtmlTag_en.properties:17` is malformed (`</div` has no `>`).

**Commit or PR hygiene:** no finding. The message has `Closes #37428` and `Signed-off-by`, as CONTRIBUTING.md requires.

**Summary:**
- Spec axis: 8 findings. The worst is #1, the `{{N}}` → `{N}`/choice change that breaks error interpolation in admin-ui and account-ui. Close behind are #2 and #3, wrong-language strings in lt and zh_CN.
- Standards axis: 8 findings, all Minor. The worst is #9, the translator-facing HTML rules are undocumented.

## Files not reviewed

None. I read all 48 files at hunk level.
- The `webauthn-error-*` `<br/>` → `<br />` hunks in about 22 `login/messages_*.properties` files are mechanical. I checked them by pattern, not by reading each line semantically.
- I can't judge whether the non-Latin translations (ar, fa, ka, ko, th, el, uk) are accurate. I only checked that their markup changed.
- I did not compile or run the theme-verifier tests, as instructed, so the false-positive and bypass claims (#4, #5, #6) are reasoned, not run. The `{{0}}` regression (#1) is also reasoned from the code, not run in a UI.

