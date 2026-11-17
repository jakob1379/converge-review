Correctness review of patch f3c8e8f3..02f48f77 ("Add a HTML sanitizer for translated message resources"). I loaded `open-code-review:delegate-review` and ran `ocr delegate preview --from f3c8e8f3 --to 02f48f77`. It listed 48 files, with 47 reviewable; the test file was excluded by `default_path`, but I reviewed it by hand anyway. I applied no fixes, as the brief said.

## Findings

**1. The admin and account consoles will show the raw template instead of the error message**
- Files and severity:
  - `js/apps/admin-ui/maven-resources/theme/keycloak.v2/admin/messages/messages_en.properties:3138` — Important
  - `js/apps/account-ui/maven-resources/theme/keycloak.v3/account/messages/messages_en.properties:188` — Important
- **Claim:** The patch changes `{{0}} {{1}} {{2}}` to `{0} {1} {2} {2,choice,0#values|1#value|1<values}`. These bundles are read by i18next in the React consoles, not by Java `MessageFormat`. i18next only fills in `{{n}}` placeholders and does not understand `choice`. The "attribute must have between min and max values" error will now display literally as `Attribute {0} must have at least {1} and at most {2} {2,choice,0#values|1#value|1<values}.`
- **Evidence:**
  - `js/apps/admin-ui/src/i18n/i18n.ts` and `js/apps/account-ui/src/i18n.ts` use i18next with the default `{{ }}` interpolation.
  - `js/libs/ui-shared/src/user-profile/utils.ts:74-84` calls `t(errorMessage, {...params})`.
  - `ThemeResource` serves the values unchanged, with no conversion from `{0}` to `{{0}}`.
  - Every neighbouring `error-*` key in the same admin-ui file (lines 2989-2994) and every community translation of this key (for example admin-ui `messages_es` and `messages_pl`, account-ui `messages_fr` and `messages_pl`) still uses `{{0}}`.
  - The server-side `themes/.../messages_en.properties` change is correct, because those go through `MessageFormat` and `MultiValueValidator` passes `Long` min and max values.
- **Proof:** reasoned. Reproduce by opening the admin console, configuring a `multivalued` validator with max=1 on an attribute, and submitting two values.
- **Fix:** revert the JS bundles to `{{n}}`. Use i18next plural syntax there if pluralisation is wanted.

**2. The new verifier crashes while building its error message**
- File: `misc/theme-verifier/src/main/java/org/keycloak/themeverifier/VerifyMessageProperties.java:96-111` — Important
- **Claim:** The code trims the common prefix (`start`) and common suffix (`end`) of `value` and `sanitized`, but never caps `start + end` at the shorter length. When the two overlap, `sanitized.substring(start, sanitized.length() - end)` throws `StringIndexOutOfBoundsException`.
- **When it happens:** a typical bad translation does it, such as a duplicated closing tag `<b>x</b></b>` in a key whose English value contains HTML. The sanitizer gives `<b>x</b>`, which yields start=8 and end=4.
- **Effect:**
  - The exception is a RuntimeException, so `verify()` (which only catches IOException) and the Mojo do not catch it.
  - The build fails with a stack trace instead of an "Illegal HTML in key …" message.
  - All later keys and files go unchecked. This hits exactly the class of input the tool exists to report; the sk `impersonateTitleHtml` fix in this patch is the same kind of defect.
- **Proof:** `jshell -q <bench>/work/keycloak__keycloak__37429.scratch/diffcrash.jsh` reproduces the trimming logic and prints `THROWS java.lang.StringIndexOutOfBoundsException: Range [8, 4) out of bounds for length 8`. That script hardcodes the sanitizer output `<b>x</b>`, which is reasoned: the OWASP jar is not in `~/.m2`, so the end-to-end path was not run.
- **Fix:** bound the suffix loop with `end < Math.min(value.length(), sanitized.length()) - start`.

**3. Lithuanian translation replaced with Italian text**
- Files and severity:
  - `themes/src/main/resources-community/theme/base/account/messages/messages_lt.properties:101` — Important
  - `themes/src/main/resources-community/theme/base/login/messages/messages_lt.properties:71` — Important
- **Claim:** `totpStep1` and `loginTotpStep1` were changed to `Installa una delle seguenti applicazioni sul tuo cellulare:`, which is Italian, in the Lithuanian bundles.
- **Evidence:** the patch diff. Lithuanian users will see Italian on the OTP setup page (`login-config-totp.ftl:10`).
- **Proof:** `grep -n "Installa" themes/src/main/resources-community/theme/base/*/messages/messages_lt.properties`. The correct value is a Lithuanian string.

**4. Simplified Chinese bundle given Traditional Chinese text**
- File: `themes/src/main/resources-community/theme/base/account/messages/messages_zh_CN.properties:112` — Minor
- **Claim:** The new `totpStep1=在您的手機上安裝以下應用程式之一：` uses Traditional characters (手機, 應用程式). Simplified would be 手机 / 应用程序.
- **Evidence:** the sibling `login/messages_zh_CN.properties:123` uses Simplified (`移动设备…应用`).

**5. A missing English file throws a RuntimeException instead of producing a validation message**
- File: `VerifyMessageProperties.java:74-80` — Minor
- **Claim:** The English counterpart's path is derived with `replaceAll` on the whole absolute path. If that file is missing (for example in a custom or extension theme that only ships non-English bundles), `verifySafeHtml` throws a RuntimeException rather than adding a message or a MojoExecutionException.
- **Related:** `replaceAll("resources-community", …)` and line 132 `getAbsolutePath().contains("email")` match on any part of the absolute path, not just the theme-relative part. A checkout directory named with "email" would turn on the RTL-style stripping for every file.

**6. Anchor-mismatch message has no key or file name, and anchors must keep their order**
- File: `VerifyMessageProperties.java:157` — Minor
- **Claim:** `"Didn't find anchor tag … in original string"` does not say which key or file failed, so the failure is hard to track down across about 180 bundles.
- **Also:** anchors are matched by order, so a valid translation that reorders the English anchors is flagged as a false positive.
- **Also:** `ANCHOR_PATTERN` `</?a[^>]*>` also matches `<abbr>`, `<area>` and `<audio …>`. Those are still flagged, just with a misleading "anchor" message.

**7. Sanitizer version hard-coded in the plugin pom**
- File: `misc/theme-verifier/pom.xml:78` — Minor
- **Claim:** The version is hard-coded as `20240325.1` instead of using the root `${owasp.html.sanitizer.version}` (`pom.xml:119`). The root `pom.xml:559` manages this artifact, so the version is redundant and will drift on the next upgrade.

## Reviewed with no findings
- **Verifier test file:** `VerifyMessagePropertiesTest.java` has no correctness issues; the new tests use `hasItem`, which is fine.
- **Test fixtures:** all six (`changedAnchor_{en,de}`, `illegalHtmlTag_en`, `noHtml_{en,de}`, `duplicateKeys_en`, renamed) are fine.
- **`admin-ui` `messages_zh_CN.properties`:** the `<NAME >` → `<NAME>` change is fine.
- **Server-side multivalued-size keys:** the `themes/.../base/{admin,login}/messages_en.properties` changes are fine. `MultiValueValidator:137` passes `Long` min and max values, and `MessageFormat` prints a null argument as "null" rather than throwing.
- **sk choice fix:** `{1,choice}` → `{2,choice}` is a correct bug fix.
- **`<br/>` → `<br />`** across ar, ca, cs, de, el, es, fa, fi, fr, hr, ka, ko, sk, th, tr, uk, zh_CN, zh_TW and en: purely cosmetic, and the runtime `KeycloakSanitizerPolicy` allows both forms.
- **Email HTML fixes:**
  - da and hu (a stray `***` prefix removed in hu)
  - fa and uk (`< p>` and `</p >` spacing fixed)
  - lt (`href=LT"` fixed)
  - nl (`</p<p>` fixed)
  - no (`<b>` removed from the plain-text body)
  - tr (`</ b>` fixed)
- **fi, sk, sv, no TOTP strings:** they now say "install one of the following applications", which matches `login-config-totp.ftl`, where the list of apps follows the string.

## Files not reviewed
None. All 48 files in the patch were reviewed, including `VerifyMessagePropertiesTest.java`, which OCR had excluded.

Coverage: total_files=48, reviewed=48, skipped=0, coverage=100%.

Not checked: I did not run Maven or the verifier itself (per instructions), so I did not confirm that the patched bundles pass the new check. Finding 2 rests on the sanitizer output I inferred for `<b>x</b></b>`, not on a run of the real sanitizer.
