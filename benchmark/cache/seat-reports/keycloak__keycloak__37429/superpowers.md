Correctness review of change.patch (f3c8e8f3..02f48f77, "Add a HTML sanitizer for translated message resources"). I loaded `superpowers:requesting-code-review` and applied its checklist myself, without dispatching a subagent. No spec was given, so I judged plan alignment against the commit title. I ran nothing through Maven, so none of these findings is backed by a failing test. Where I list a command, it is a read-only grep that shows the defect on the patched tree.

## Findings

1. **js/apps/admin-ui/maven-resources/theme/keycloak.v2/admin/messages/messages_en.properties:3138** and **js/apps/account-ui/maven-resources/theme/keycloak.v3/account/messages/messages_en.properties:188**: Important.
   - **Claim:** the patch breaks the multivalued-size validation message in the admin console and the account console. It rewrites `{{0}}/{{1}}/{{2}}` to Java MessageFormat `{0}/{1}/{2}` and adds `{2,choice,0#values|1#value|1<values}`. These bundles are rendered by i18next in the React apps, and i18next only interpolates `{{name}}` and has no choice syntax. Users will see the literal text `Attribute {0} must have at least {1} and at most {2} {2,choice,0#values|1#value|1<values}.`
   - **Evidence:**
     - `js/apps/admin-ui/src/i18n/i18n.ts:16` and `js/apps/account-ui/src/i18n.ts:27` set only `escapeValue:false`, so the default `{{ }}` delimiters apply.
     - `ThemeResource` returns the theme messages raw, with no `{n}` to `{{n}}` conversion. The only converter is `AccountConsole.convertPropValue`, which feeds the legacy `msgJSON` path, not i18next.
     - `js/libs/ui-shared/src/user-profile/utils.ts:74-85` calls `t("error-invalid-multivalued-size", {0:..,1:..,2:..})`, which needs `{{0}}`.
     - This is now the only single-brace or `choice` entry in either React bundle, while every sibling key (for example `error-invalid-length`) still uses `{{n}}`.
     - The verifier did not require this change: its own code strips the `<!-- -->` the sanitizer inserts for `{{`.
     - Check: `grep -nP '(?<!\{)\{[0-9]\}(?!\})|choice' js/apps/{admin,account}-ui/maven-resources/theme/*/*/messages/messages_en.properties`. On the patched tree the key above is the only hit in admin-ui. In account-ui it sits next to the two `recovery-codes-number-*` keys, which already used `{0}`.
   - **Fix:** revert these two files to `{{0}} … {{2}} value(s)`. The server-side base-theme change, which FreeMarker renders with MessageFormat and Long params, is fine.

2. **themes/src/main/resources-community/theme/base/login/messages/messages_lt.properties:71** and **themes/src/main/resources-community/theme/base/account/messages/messages_lt.properties:101**: Important.
   - **Claim:** the Lithuanian `loginTotpStep1` and `totpStep1` were replaced with Italian text: "Installa una delle seguenti applicazioni sul tuo cellulare:". Lithuanian users will see Italian on the OTP setup page.
   - **Evidence:** `grep -n Installa themes/src/main/resources-community/theme/base/*/messages/messages_lt.properties`. The text matches `messages_it.properties` (account line 138, login line 92).
   - **Fix:** delete the key so it falls back to English, or translate it properly.

3. **themes/src/main/resources-community/theme/base/account/messages/messages_zh_CN.properties:112**: Minor.
   - **Claim:** Simplified Chinese `totpStep1` was replaced with Traditional Chinese: 在您的手機上安裝以下應用程式之一 (手機 and 應用程式 are Traditional forms).
   - **Evidence:** the login zh_CN equivalent (`login/messages_zh_CN.properties:123`) uses Simplified: 在您的移动设备中安装以下任意一个应用.

4. **misc/theme-verifier/src/main/java/org/keycloak/themeverifier/VerifyMessageProperties.java:124-126**: Minor (verifier gap).
   - **Claim:** for `linkExpirationFormatter.timePeriodUnit*` and `error-invalid-multivalued-size`, the regex `\{[0-9]+,choice,[^}]*}` deletes the whole choice argument before sanitizing. Any HTML inside a translator-supplied choice branch is never checked. For example, `{2,choice,0#<img src=x onerror=..>|1#y}` passes.
   - **Evidence:** reasoned from the code; `normalizeValue` runs before `policy.sanitize`. Only those keys are exposed.

5. **VerifyMessageProperties.java:157**: Minor.
   - **Claim:** the anchor-mismatch error has neither the key nor the file: "Didn't find anchor tag X in original string". The verifier scans about 160 files and fails the build with an aggregated list, so a contributor cannot tell which file or key broke. The "Illegal HTML" message at :111 does include both.
   - **Evidence:** code at :157 compared with :111.

6. **VerifyMessageProperties.java:70, 79**: Minor.
   - **Claim:** when the file or its derived English counterpart cannot be read, the code throws a raw `RuntimeException` instead of the `MojoExecutionException` used elsewhere in `verify()`. The English path is guessed with regex replaces on the absolute path (:74-75), so a future community-only bundle with no English twin will crash the Mojo instead of reporting a validation error.
   - **Evidence:** I checked all 162 current `messages_*.properties` under the six configured resource dirs, and every one maps to an existing `_en` file, so nothing breaks today.

7. **misc/theme-verifier/src/test/java/org/keycloak/themeverifier/VerifyMessagePropertiesTest.java:30-52**: Minor.
   - **Claim:** every test is a positive detection. No test asserts that a valid bundle produces zero messages, so false positives can only show up in a full build. Valid cases include `{{0}}` (the `<!-- -->` stripping), `<1>` numeric tags, choice formats, identical anchors, the email RTL style, and `CLAIM.<NAME>`. `verifyDuplicateKeysDetected` was also loosened from `contains` to `hasItem`, so extra spurious messages no longer fail it.
   - **Evidence:** test file contents.

8. **misc/theme-verifier/src/test/resources/illegalHtmlTag_en.properties:17**: Minor.
   - **Claim:** the fixture value `Some <div>tag</div` has a malformed closing tag (missing `>`). The test still passes because `<div>` is stripped either way, but the fixture does not represent the intended case.

9. **misc/theme-verifier/pom.xml:76-85**: Minor.
   - **Claim:** the owasp sanitizer version `20240325.1` is hard-coded even though the root pom already defines `${owasp.html.sanitizer.version}` (pom.xml:119). It will drift on the next sanitizer bump. The theme-verifier pom has no parent, so the duplication may be deliberate, but nothing ties the two versions together.

## Checked, no issue found
- The sk `error-invalid-multivalued-size` fix (`{1,choice}` to `{2,choice}`) is correct.
- The sk `impersonateTitleHtml` stray `</strong>` removal is correct.
- The no `identityProviderLinkBody` change removes `<b>` from a plain-text email, which is correct.
- The hu `***emailUpdateConfirmationBodyHtml` change fixes a typo'd key; it now overrides English, which is intended.
- The lt, nl, fa, uk, tr and da email markup repairs are correct.
- The webauthn `<br/>` to `<br />` edits are cosmetic.
- `MultiValueValidator` passes Long params, so server-side `{2,choice,…}` formats correctly; a null param formats as "null" and does not throw.
- Every scanned bundle resolves to an existing English file.

## Files not reviewed
- None skipped. The webauthn `<br/>` to `<br />` edits were checked by pattern rather than by translation meaning: login messages_ar, ca, cs, de, el, es, fa, fi, fr, hr, ka, ko, th, tr, uk, zh_CN and zh_TW. I did not judge translation quality anywhere except where a string was clearly in the wrong language (findings 2 and 3).

I did not compile or run the verifier against the patched tree. Whether the head commit's resources pass the new check with zero false positives is reasoned from the code, not confirmed.
