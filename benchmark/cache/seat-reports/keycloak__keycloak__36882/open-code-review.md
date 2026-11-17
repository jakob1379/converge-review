I reviewed the patch through `open-code-review:delegate-review` in range mode (`1b28ac610d..HEAD`, 11 files). OCR offered 6 files for review and excluded 5 (3 docs and 2 tests). I read all 11 in the patch and checked the surrounding source. Report only: I changed nothing and wrote no files. I found no Critical issues, one Important and three Minor.

## Findings

**1. docs/guides/operator/advanced-configuration.adoc:446-450 — Important (reasoned, no failing command)**
- **Claim:** The new CAUTION block says "the feature `rolling-updates` must be enabled. Otherwise, the {project_name} Operator will fail." The operator never checks this feature, so the documented gate does not exist.
- **Evidence:**
  - Running `grep -rn "ROLLING_UPDATES\|rolling-updates" operator/src/main` finds nothing.
  - `UpgradeLogicFactory.create` (operator/src/main/java/org/keycloak/operator/upgrade/UpgradeLogicFactory.java:35-43) picks the update logic from `spec.update.strategy` alone. `Recreate` works whether or not the feature is on.
  - The only place the operator touches features is `KeycloakDistConfigurator.java:122-124`, which just passes `spec.features` to the server as options.
  - So the `UpgradeTest` change, which enables the feature in the CR, proves nothing about gating. The test would pass the same way without it.
- **Fix:** either add a check in the operator (reject or report a status error when `spec.update` is set and `rolling-updates` is not enabled), or remove the sentence from the docs.

**2. quarkus/runtime/src/main/java/org/keycloak/quarkus/runtime/compatibility/CompatibilityResult.java:34-35 — Minor**
- **Claim:** The meaning of the exit codes changes. "Recreate required" moves from 4 to 3, and 4 now means "feature disabled".
- **Evidence:**
  - Before the patch the code returned 4, but the docs table already listed 3, so the patch brings code in line with the docs.
  - Any script written against the old actual behaviour (4 = recreate) will now read "feature disabled" as "recreate". That is harmless today, since both mean "rolling update not possible", and the command is preview.
  - It is still a behaviour change and deserves a release or migration note.

**3. quarkus/tests/integration/src/test/java/org/keycloak/it/cli/dist/UpdateCommandDistTest.java:46-50 — Minor**
- **Claim:** `testFeatureNotEnabled` only checks the error message. It never checks that the exit code is 4, which is the new contract.
- **Evidence:** the test has no `assertEquals(4, ...exitCode())`. `testCompatible` shows the test harness can read exit codes. Only `update-compatibility metadata` runs without the feature; `check` without the feature is never run.

**4. UpdateCompatibilityCheck.java:46-50 and UpdateCompatibilityMetadata.java:46-50 — Minor**
- **Claim:** The gate is copied into both subcommands.
- **Evidence:**
  - Putting it once in `AbstractUpdatesCommand` would stop a future subcommand from missing it.
  - I verified the following and found no correctness problem:
    - The early `return` after `picocli.exit(...)` is needed. `Picocli.exit` (Picocli.java:203-208) does not call `System.exit` in test-launch mode.
    - `Profile.isFeatureEnabled` is safe at this point. `Profile.getInstance()` is already set by `PropertyMappers.sanitizeDisabledMappers()` before `cmd.execute` (Picocli.java:128, PropertyMappers.java:302-306), so there is no null-pointer risk.

## Other checks with no finding
- **`common/.../Profile.java:134-136`:** the enum syntax (trailing comma before `;`) is valid. `ROLLING_UPDATES` is `PREVIEW`, so it is off by default, which is what the gate needs.
- **`operator/scripts/Dockerfile-custom-image:5`:** adding `--features=rolling-updates` to the build is consistent with the rest of the patch.
- **`docs/guides/templates/kc.adoc:53`:** the macro is used only for the two `update-compatibility` examples, so the extra flag is correct in both.
- **`docs/guides/server/update-compatibility.adoc`:** the exit-code table now matches the code (3 = recreate, 4 = feature disabled).
- **`UpgradeTest.java:110-115`:** `setEnabledFeatures(List.of(...))` replaces any features the test CR already enabled. This is test-only and harmless today.

## Files not reviewed
None. OCR left out 5 of 11 files: the 3 docs (`unsupported_ext`) and `UpgradeTest.java` / `UpdateCommandDistTest.java` (`default_path`). I reviewed all 5 by hand anyway, so coverage is 11 of 11.

I did not run any builds or tests, as instructed. Every finding is reasoned from reading the code; none was confirmed by running anything.
