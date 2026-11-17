Review of keycloak__keycloak__36882 (pinned.patch, 11 files, +70/-18), reviewed against base 1b28ac610d. I confirmed that `git diff base...HEAD` is byte-identical to pinned.patch. The commits are c698590195 "Feature flag: rolling-updates" (Closes #36840), b1965bb9c4, 5d2490d33a, a44563d5c1 and 62bf98939e. I did not run any builds or tests.

## Standards

Standards docs found:
- `CONTRIBUTING.md`: one commit per PR, "Closes #N" as the last line, sign-off, functional or integration tests, documentation included, and no unrelated changes.
- `PR-CHECKLIST.md`: sufficient test coverage, and docs including release notes and the upgrade guide "if applicable".
- `quarkus/CONTRIBUTING.md`: how to run tests and build the docs only, no code rules.

There is no CODING_STANDARDS, AGENTS.md or CLAUDE.md in the repo.

1. **docs/guides/operator/advanced-configuration.adoc:446-450 — Important (reasoned).**
   - **Claim:** The new CAUTION block says "the feature `rolling-updates` must be enabled. Otherwise, the {project_name} Operator will fail." Nothing in the operator enforces this, so the documentation is inaccurate (CONTRIBUTING: "Includes documentation").
   - **Evidence:**
     - Neither `ROLLING_UPDATES` nor `rolling-updates` appears anywhere under `operator/src/main`. The operator only reads `spec.update.strategy`: `UpdateSpec.findUpdateStrategy`, then `UpgradeLogicFactory`, which has only the AlwaysRecreate and RecreateOnImageChange implementations.
     - In the patched `operator/src/test/java/org/keycloak/operator/testsuite/integration/UpgradeTest.java:104-106`, `createInitialDeployment(null)` returns before the feature is enabled. The `null` parameter in `upgradeStrategy()` (line 50) is still expected to pass, so the operator's own test assumes it works without the flag.
   - **How to show it fails:** add an operator test that sets `spec.update.strategy` with no `features.enabled` and expect a failure. It will not fail.

2. **quarkus/tests/integration/src/test/java/org/keycloak/it/cli/dist/UpdateCommandDistTest.java:46-50 — Minor.**
   - **Claim:** Test coverage of the new gate is incomplete (PR-CHECKLIST: "sufficient test coverage").
   - **Evidence:**
     - Only `metadata` is tested with the feature off. The guard in `check` (UpdateCompatibilityCheck.java:46-50) is not tested.
     - The documented exit code `4` is never asserted, and the recreate path's change from code 4 to 3 has no exit-code assertion either. Only `exitCode()==0` is checked, at line 75.

3. **docs/guides/server/update-compatibility.adoc:132-134 — Minor.**
   - **Claim:** Exit code 4 is described as "Rolling Upgrade is not possible. The feature `rolling-updates` is disabled."
   - **Evidence:** The same code is returned by `metadata` (UpdateCompatibilityMetadata.java:48), where the result says nothing about whether a rolling upgrade is possible. The row describes a precondition failure as an upgrade verdict, which misleads automation that branches on 3 versus 4.

4. **quarkus/runtime/src/main/java/org/keycloak/quarkus/runtime/compatibility/CompatibilityResult.java:31-35 — Minor.**
   - **Claim:** `RECREATE_UPGRADE_EXIT_CODE` changes from 4 to 3, which is a behaviour change bundled into a feature-flag commit (CONTRIBUTING: "No changes to code not directly related to your PR").
   - **Evidence:** It is defensible and low-risk. The base docs already said 3, so this is really a bug fix aligning the code with the docs. The command was added in 588e60e058 on 2025-01-24 and is unreleased (999.0.0-SNAPSHOT). It still deserves a mention in the PR or commit description.

5. **Commit history — Minor.**
   - **Claim:** There are 5 commits ("feedback", "fix test failure", and so on), and only the first ends with `Closes #36840`.
   - **Evidence:** CONTRIBUTING requires "One commit per PR" and an issue link as the last line. The breach goes away if the PR is squashed on merge.

6. **No release-note entry — Minor.**
   - **Claim:** A new preview feature (`Profile.java:136`) and a behaviour change to a CLI command (it now fails unless `--features=rolling-updates` is passed) have no release-note entry.
   - **Evidence:** PR-CHECKLIST says to update the release notes "if applicable". I found no hit under `docs/documentation/release_notes`. Whether it applies is arguable, because the command itself is unreleased.

Baseline smells (judgement calls, not violations):
- **Possible Duplicated Code:** the same 5-line guard (`isFeatureEnabled`, `printFeatureDisabled`, `exit(FEATURE_DISABLED)`, `return`) appears at UpdateCompatibilityCheck.java:46-50 and UpdateCompatibilityMetadata.java:46-50. It could be a single helper in `AbstractUpdatesCommand`, next to the new `printFeatureDisabled()`.
- **Possible Mysterious Name:** `FEATURE_DISABLED` (CompatibilityResult.java:35) drops the `_EXIT_CODE` suffix that its siblings `ROLLING_UPGRADE_EXIT_CODE` and `RECREATE_UPGRADE_EXIT_CODE` use.

## Spec

No spec was provided. The commit references #36840, but I did not fetch it, as instructed, so this axis was not run against an issue. Intent inferred from the commits and diff: put the preview `update-compatibility` CLI and the operator's rolling-update strategy behind a new `rolling-updates` preview feature.

- **Partial against that inferred intent (Important, reasoned):** only the CLI is gated. The operator's `spec.update` is not, yet the docs claim it is (see Standards finding 1). Either the operator gate is missing, or the operator CAUTION block and the test changes in UpgradeTest.java:110-115 are cosmetic. I can't tell which the issue intended without reading #36840.
- **Not asked for:** the exit code 4-to-3 renumbering (Standards finding 4) and baking the feature into `operator/scripts/Dockerfile-custom-image:5`, which now applies to every operator CI test using the custom image.

## Summary

- **Standards:** 6 findings and 2 smells. The worst is that the operator docs claim a failure the code never raises.
- **Spec:** no spec, so I report one inferred gap (the operator is not gated) and 2 out-of-scope changes.

## Files not reviewed

None. I reviewed all 11 files. The two docs files (`update-compatibility.adoc`, `kc.adoc`) were checked for accuracy, not rendered.

I did not verify that `Profile` is always initialised before `run()` in the update commands. If it isn't, `Profile.isFeatureEnabled` would throw a NullPointerException, but the new dist test should catch that in CI.
