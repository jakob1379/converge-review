I reviewed the patch myself, following the requesting-code-review skill and its reviewer template. I did not spawn a subagent. I did not run any build or test, as instructed, so every finding below is reasoned from the code rather than shown by a failing command.

The core gate is sound. `ROLLING_UPDATES` is a PREVIEW feature with the key `rolling-updates`. Both CLI subcommands check it before doing anything else. The feature profile is already set up by `PropertyMappers.sanitizeDisabledMappers()` (Picocli.java:128) before `cmd.execute`, so `Profile.isFeatureEnabled` cannot throw a null-pointer error there. Moving the recreate exit code from 4 to 3 brings the code in line with the exit-code table the guide already had, which said 3. The help approval files show the feature list as `<...>`, and `FeaturesDistTest` builds its expected list from the enum at run time, so neither needs updating.

## Findings

**1. docs/guides/operator/advanced-configuration.adoc:446-450 — Important**
- **Claim:** The new CAUTION says the Operator "will fail" if `rolling-updates` is not enabled. Nothing in the operator enforces that, so the operator's `spec.update.strategy` is not gated behind the preview feature. Either the docs are false or the gate is missing.
- **Evidence:**
  - `grep -rn "ROLLING_UPDATES\|rolling-updates" operator/src/main` finds nothing.
  - `UpgradeLogicFactory.create` (operator/src/main/java/org/keycloak/operator/upgrade/UpgradeLogicFactory.java:35-43) switches on `UpdateSpec.findUpdateStrategy` without looking at features.
  - `KeycloakSpec.getUpdateSpec` has no validation tied to features.
  - So a CR with `update.strategy: Recreate` and no features behaves exactly as before.
  - The `UpgradeTest` change (operator/src/test/java/org/keycloak/operator/testsuite/integration/UpgradeTest.java:110-115) only passes the feature through to the server. It does not test any operator gate, and no test checks that the operator fails without the feature.

**2. quarkus/tests/integration/src/test/java/org/keycloak/it/cli/dist/UpdateCommandDistTest.java:46-50 and 88-107 — Important (test gap)**
- **Claim:** The exit codes are the public contract for scripts, and the patch renumbers them, yet no test checks either new value.
- **Evidence:**
  - The guide tells users to "rely only on the exit code of the `check` command".
  - The patch changes `RECREATE_UPGRADE_EXIT_CODE` from 4 to 3 and gives 4 to `FEATURE_DISABLED` (CompatibilityResult.java:34-35).
  - `testFeatureNotEnabled` only checks the error text, not that the exit code is 4.
  - `testIncompatible` only checks error text, not that the exit code is 3.
  - The only exit-code assertion in the file is `assertEquals(0, ...)` at line 75.
  - These tests are `@RawDistOnly`, so a real process exit code is available (`result.exitCode()`). Picocli.exit hard-exits on non-zero codes outside test launch mode, so the check would be meaningful.
  - If someone later swaps the two values, nothing fails.

**3. quarkus/tests/integration/src/test/java/org/keycloak/it/cli/dist/UpdateCommandDistTest.java:46-50 — Minor**
- **Claim:** `testFeatureNotEnabled` only runs `metadata`. The separate copy of the gate in `UpdateCompatibilityCheck.run()` (UpdateCompatibilityCheck.java:46-50) is never run with the feature off.
- **Evidence:** The `@Launch({UpdateCompatibility.NAME, UpdateCompatibilityMetadata.NAME})` call is the only one without `ENABLE_FEATURE`.

**4. docs/guides/templates/kc.adoc:53 — Minor**
- **Claim:** The macro hard-codes `--features=rolling-updates` after the user's parameters. This conflicts with the guide's own rule to "include all configuration options".
- **Evidence (reasoned):**
  - A user who enables other features through `KC_FEATURES` or `keycloak.conf` gets them overridden by the CLI value, because CLI has higher priority. The metadata then describes a different feature set than the running deployment.
  - Today's metadata holds only versions (see the guide's WARNING), so nothing breaks yet. It becomes wrong once feature or config comparison lands.
  - For an `--optimized` (pre-built) image, a runtime `--features` is a build-time option and should not take effect. Following the doc would then still exit with 4, and the user actually has to rebuild with the feature.
  - The branch history points the same way: commit b1965bb9c4 "do not use custom image, it fails", followed by 5d2490d33a, which bakes the feature into Dockerfile-custom-image.
  - The guide does not mention that the feature must be part of the build.

**5. docs/guides/server/update-compatibility.adoc:132-134 — Minor**
- **Claim:** Exit code 4 is described as "Rolling Upgrade is not possible", which mixes up "tool disabled" with a compatibility verdict. The same code is also returned by `metadata`, which the table does not cover.
- **Evidence:** UpdateCompatibilityMetadata.java:46-50 exits with `FEATURE_DISABLED`. Scripts that treat any non-zero `check` result as "recreate" will silently recreate when the feature is simply off.

**6. operator/scripts/Dockerfile-custom-image:5 — Minor**
- **Claim:** The shared operator test image now builds with the `rolling-updates` preview feature on, so every operator test that uses the custom image runs with it, not just `UpgradeTest`.
- **Evidence:** `build-testing-docker-images.sh:12` builds this one image for the whole suite, and `BaseOperatorTest.getTestKeycloakDeployment` applies `customImage` to every deployment. The impact is low today because the feature changes no server behaviour beyond the CLI gate.

## Verdict
Ready to merge with fixes. The CLI gate works. Finding 1 needs a decision: either add a real operator gate, for example a status error or validation when `spec.update` is set without the feature, or drop the claim from the operator docs. Finding 2 needs exit-code assertions for 3 and 4.

Set aside as out of scope:
- Before this patch the guide already said exit code 1 means a missing or corrupt metadata file. The code actually throws `PropertyException`, which exits with 2 (usage error). That predates the patch.

## Files not reviewed
None. I reviewed all 11 files in the patch: Profile.java, both operator and server adoc guides, kc.adoc, Dockerfile-custom-image, UpgradeTest.java, AbstractUpdatesCommand.java, UpdateCompatibilityCheck.java, UpdateCompatibilityMetadata.java, CompatibilityResult.java and UpdateCommandDistTest.java.

Not checked: whether a runtime `--features` really takes effect under `--optimized` (finding 4 is reasoned from build-time option semantics and the commit history, not run).
