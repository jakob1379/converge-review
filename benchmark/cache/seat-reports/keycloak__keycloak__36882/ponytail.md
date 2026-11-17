## Over-engineering review: keycloak PR 36882 (rolling-updates feature flag)

What this change does: it adds a preview feature flag, `ROLLING_UPDATES`. The `update-compatibility metadata` and `update-compatibility check` commands now refuse to run unless that flag is on, and they exit with code 4. The recreate exit code changes from 4 to 3, which now matches the existing docs table. Docs, the operator custom image and the tests are updated to turn the flag on.

The patch is small and adds almost nothing extra. I found one minor duplication. Nothing is Critical or Important.

### Should fix (Minor)

1. **The same feature check is pasted into both commands** (`quarkus/runtime/src/main/java/org/keycloak/quarkus/runtime/cli/command/UpdateCompatibilityCheck.java:46-50` and `quarkus/runtime/src/main/java/org/keycloak/quarkus/runtime/cli/command/UpdateCompatibilityMetadata.java:46-50`)
   - **Severity:** Minor
   - **What this is:** The block "if the flag is off, print an error, exit with `FEATURE_DISABLED` and return" appears word for word in both `run()` methods. Both classes extend `AbstractUpdatesCommand`, which already holds their shared helpers.
   - **Problem:** The two copies must always change together, and any new update command has to remember to copy it a third time. The new one-line helper `printFeatureDisabled()` (`AbstractUpdatesCommand.java:83-85`) has no other caller. It exists only to serve these two copies.
   - **Fix:** Put the check in one method in `AbstractUpdatesCommand`, for example `boolean isRollingUpdatesDisabled()`, which prints the error, calls `picocli.exit(FEATURE_DISABLED)` and returns true. Each `run()` then starts with `if (isRollingUpdatesDisabled()) return;`, and `printFeatureDisabled()` goes away.
   - **Evidence:** `grep -rn printFeatureDisabled --include=*.java .` shows only the definition and the two copies. The two blocks in the diff are identical. This is reasoned. No test fails, because behavior does not change.
   - **If we skip it:** About 5 extra lines, and the two copies can drift apart.

Verdict: Ship.
Lean: about -5 lines possible.

### Files not reviewed

None. I read all 11 files in the patch, with the surrounding source for the Java files. For the docs files (`advanced-configuration.adoc`, `update-compatibility.adoc`, `kc.adoc`), the Dockerfile and the two test files, I only checked for extra or duplicated content and found none.

### Outside my role (not counted as findings)

- `docs/guides/operator/advanced-configuration.adoc` says the Operator "will fail" without the feature. The patch adds no feature check in `operator/src/main`, so I could not find what would fail.
- `UpgradeTest` overwrites any features the CR (Keycloak custom resource) already enabled, because it calls `setEnabledFeatures(List.of(...))`.

Not checked: I ran no build or tests, as instructed.
