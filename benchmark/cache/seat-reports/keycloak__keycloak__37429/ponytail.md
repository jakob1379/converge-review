Seat: over-engineering only. Skill used: ponytail:ponytail-review. Expected load: a build-time Maven plugin that runs once per properties file (a few hundred files) on one machine, so nothing here is hot.

What this change does: It adds a check to the theme-verifier Maven plugin. For each message file, the check loads the matching English file and sanitizes every value with OWASP's HTML sanitizer. If English has no HTML, the translation may have none. If English has HTML, only br, p, strong and b are allowed, and every link (`<a>` tag) must match the English link exactly. The ~45 message-file changes fix translations that now fail this check.

All findings are Minor and advisory. None blocks the change.

1. **`verifySafeHtml` reads the file a second time and wraps errors twice.** `misc/theme-verifier/src/main/java/org/keycloak/themeverifier/VerifyMessageProperties.java:L65-80`
   - Claim: The file is already in memory as `contents` (L49). L67-71 opens it again with a FileInputStream. Both try/catch blocks turn IOException into RuntimeException, but `verify()` already turns IOException into MojoExecutionException (L52-53).
   - Fix: Change the method to `verifySafeHtml(String contents) throws IOException`. Build the bundle with `new PropertyResourceBundle(new StringReader(contents))` and the English one with `new PropertyResourceBundle(Files.newBufferedReader(Path.of(englishFile)))`. Both try/catch blocks and the `FileInputStream` import go away (about -8 lines). Errors then reach Maven as the plugin's own MojoExecutionException instead of a raw RuntimeException. Encoding stays the same, because `Files.readString` already insists on UTF-8.
   - Evidence: reasoned from reading L46-80.

2. **Unused parameter.** `VerifyMessageProperties.java:L150` (`santizeAnchors(String key, ...)`, called at L88)
   - Claim: `key` is never used in the method body. The method name also has a typo ("santize").
   - Fix: Remove the parameter and fix the name. Both are one-line edits.
   - Evidence: L150-162 has no reference to `key`.

3. **`getEnglishValue` uses an exception for control flow.** `VerifyMessageProperties.java:L164-172`
   - Claim: Nine lines plus the `MissingResourceException` import do the job of one line.
   - Fix: `bundleEnglish.containsKey(key) ? bundleEnglish.getString(key) : ""` (about -7 lines).
   - Evidence: reasoned. `ResourceBundle.containsKey` exists since Java 6, and the module targets 17.

4. **Constants are instance fields.** `VerifyMessageProperties.java:L58-63, L139`
   - Claim: `POLICY_SOME_HTML`, `POLICY_NO_HTML` and `HTML_TAGS` are named like constants but are package-private instance fields. `ThemeVerifierMojo.java:51` creates one verifier per file, so both sanitizer policies and the regex are rebuilt for every properties file. `ANCHOR_PATTERN` at L145 in the same file is already `private static final`, so the file is inconsistent with itself.
   - Fix: Make all three `private static final`.
   - Evidence: reasoned from the code.

5. **The sanitize, unescape and diff steps could be replaced by the sanitizer's own change listener.** `VerifyMessageProperties.java:L92-111` and L130, plus the `commons-text` dependency in `misc/theme-verifier/pom.xml:L80-85`
   - What the code does now: it sanitizes the value, then unescapes entities with commons-text (L95). It strips the `<!-- -->` the sanitizer inserts (L97). It unescapes the input too (L130) so the two strings can be compared. Finally it trims the common prefix and suffix by hand (L101-109) to build the error message.
   - Simpler: OWASP's `policy.sanitize(value, HtmlChangeListener, ctx)` reports discarded tags and attributes directly (`discardedTag`, `discardedAttributes`). That makes the unescape calls, the comment hack, the trim loop and the commons-text dependency unnecessary. Rough saving: -15 lines and one dependency.
   - Supporting evidence that the trim loop is fragile: it crashes when the prefix and suffix overlap. I copied L102-111 verbatim into jshell with value `"Next -><br>"` and sanitized `"Next ->"` (the plausible result for a no-HTML key). It throws `StringIndexOutOfBoundsException: Range [7, 6) out of bounds for length 7`. That stops the whole plugin instead of reporting a message. Reproduce with `jshell -q <bench>/work/keycloak__keycloak__37429.scratch/trim.jsh`.
   - Caveat: I did not check whether the sanitizer changes text in a way that discards no tag (for example a stray `<` with no closing `>`). The current string comparison would catch that and the listener would not. The listener approach is reasoned, not verified.

6. **`<scope>compile</scope>` is the default.** `misc/theme-verifier/pom.xml:L84`
   - Claim: The line has no effect. Delete it. This finding goes away if finding 5 drops commons-text.
   - Evidence: Maven's default scope is compile. The sibling `maven-core` entry does the same, so this is cosmetic.

Not over-engineering. Hardcoded dependency versions in the pom are fine, because this module has no parent and pins `commons-io` the same way. The per-key exceptions in `normalizeValue` (L117-137) are ugly but carry real data exceptions; there is no smaller form.

Outside my seat (correctness), passed on for the correctness and translation reviewers, checked against the patched files:
- `themes/src/main/resources-community/theme/base/account/messages/messages_lt.properties:101` and `themes/src/main/resources-community/theme/base/login/messages/messages_lt.properties:71`: the Lithuanian text was replaced with Italian ("Installa una delle seguenti applicazioni sul tuo cellulare:").
- `themes/src/main/resources-community/theme/base/account/messages/messages_zh_CN.properties:112`: the Simplified Chinese file now has Traditional Chinese text (手機 / 應用程式). The `login/messages_zh_CN.properties:123` entry uses Simplified forms.

Verdict (my seat): Ship. Findings 1-4 are cheap cleanups. Finding 5 is the only one that removes a dependency and a crash path.
Lean: about -30 lines and one dependency possible.

Files not reviewed: none were skipped. I read all 6 Java, pom and test-fixture files in full. I read the ~44 `.properties` translation diffs line by line for structure only. I did not judge translation quality beyond the language mix-ups above.

Not checked: I did not build or run the plugin, per instructions. So I did not confirm that the real repository files pass the new check, or the listener approach in finding 5.
