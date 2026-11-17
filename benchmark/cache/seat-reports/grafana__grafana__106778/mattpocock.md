I reviewed the patch with `mattpocock-skills:code-review`, doing both axes myself as instructed. The diff is 15e1aa8855...8df8503710 (12 commits, 14 files).

## Spec
There is no spec, so the Spec axis has nothing to check. I could not judge scope creep or missing requirements against a source document.

## Standards
Sources I checked:
- `contribute/style-guides/frontend.md`, `code-comments.md`, `testing.md`
- `contribute/internationalization.md`
- `public/app/features/alerting/unified/TESTING.md`
- the alerting-specific block in `eslint.config.js` (lines 285–296)

The repo has no AGENTS.md or CLAUDE.md. The Fowler smell baseline is left out, as you asked.

1. **`public/app/features/alerting/unified/rule-list/FilterView.tsx:157`**, Important. The `'grafana'` case now returns `<GrafanaRuleListItem …>` inside `rules.map(...)` without `key={key}`.
   - Evidence: the removed `<GrafanaRuleLoader key={key} …>` had the key. The sibling cases on lines 165 and 169 still pass `key={key}`.
   - This list paginates and grows. React will warn about missing keys and may reuse the wrong row when items are added.
   - Standard: `frontend.md` says to follow the Airbnb React/JSX guide, whose rule is "always include a key prop in iterators". `react/jsx-key` is not in `eslint.config.js`, so lint will not catch it. `public/test/setupTests.ts:16-21` turns console errors into test failures on CI (`jest-fail-on-console`), so any test that renders more than one Grafana rule here would fail.
   - Reasoned, not run. `FilterView.test.tsx` only seeds Mimir/Prometheus rules, so no current test covers this path.

2. **`public/app/features/alerting/unified/hooks/useAbilities.ts:287`**, Minor. `useAllGrafanaPromRuleAbilities` is exported, but nothing outside this file uses it (grep: only call sites at :387 and :401, same file). Standard: `frontend.md` › Exports, "Export only the code that is meant to be used outside the module."

3. **`public/app/features/alerting/unified/hooks/useAbilities.ts:380`**, Minor. `export const skipToken = Symbol('ability-skip-token')` is a new module constant in camelCase. Standard: `frontend.md` › Constants, "Use ALL CAPS for constants." It mimics RTK Query's `skipToken`, which is a reasonable exception, but it is still a breach as written.

4. **`public/app/features/alerting/unified/rule-list/GrafanaRuleListItem.tsx:26`**, Minor. `export function GrafanaRuleListItem(...)` is new code with no explicit return type. The helpers this patch adds elsewhere do declare return types (`getIsProvisioned`, `getEditableIdentifier`, `useGrafanaPromRuleAbility`). Standard: `frontend.md` › Types, "Specify function return types explicitly in new code." The guide notes that lint does not enforce this.

5. **`public/app/features/alerting/unified/hooks/useAbilities.ts:289` and `:301`**, Minor. Two comment problems:
   - Line 289 ends with a stray `// duplicate` that carries no information.
   - Line 301 says "All GrafanaPromRuleDTO rules are Grafana-managed by definition", but sits above `isAlertingRule = prometheusRuleType.grafana.alertingRule(rule)`, which checks something different (alerting vs recording).
   - Standard: `frontend.md` › Code comments (follow the code comment guidelines; comments should document the code).

6. **`public/app/features/alerting/unified/hooks/useAbilities.ts:220`**, Minor. The new TSDoc `@deprecated Use {@link useAllRulerRuleAbilities} instead` points callers at a hook that hard-codes `isFederated = false` (lines 243–245, with a `TODO`). So the documented replacement does not do the same job (see O1). Standard: `code-comments.md` › Deprecate an API, "add a reason why the API is deprecated". No reason is given, and the suggested replacement is not equivalent.

7. **`public/app/features/alerting/unified/rule-list/GrafanaGroupLoader.test.tsx:42`**, Minor. `ui.menuItems.delete` is defined but never used. Lines 194–203 use only silence, copyLink, duplicate and export. `eslint.config.js:293` turns on `'unicorn/no-unused-properties': 'error'` for `public/app/features/alerting/**`, which includes test files. Reasoned: eslint is not installed in this checkout, and I believe but did not confirm that the rule checks nested properties.

8. **`public/app/features/alerting/unified/components/rules/RulesTable.test.tsx:20-29, 57-73`**, Minor. The patch mocks more of the repo's own `useAbilities` hooks (`useGrafanaPromRuleAbility`, `useGrafanaPromRuleAbilities`, `useRulerRuleAbilities`). Alerting's `TESTING.md` says permission tests should use `enableRBAC`/`grantUserPermission(s)` and MSW. The `jest.mock` itself predates this patch, but the patch adds to it. `GrafanaGroupLoader.test.tsx` in the same patch does follow the documented approach (`grantUserPermissions` plus `setFolderAccessControl`).

i18n (`public/locales/en-US/grafana.json`): the two keys removed (`alerting.rule-list.cannot-find-rule-details-for` and `alerting.rule-list.cannot-load-rule-details-for`) are no longer used anywhere in `public/app` (grep is empty). That matches what `make i18n-extract` would produce, and the patch adds no new UI strings, so nothing breaches `internationalization.md`.

## Correctness issues outside my brief
These are not standards breaches, so you can drop them, but they matter.
- **O1** (`useAbilities.ts:220-229, 243-245`): `useAllAlertRuleAbilities` (the v1 list and `RuleDetails`, through `useAlertRuleAbility`) used to compute `isFederated = isFederatedRuleGroup(rule.group)`. It now delegates to `useAllRulerRuleAbilities`, where `isFederated = false`. Rules in federated Mimir groups lose the immutability check on Update, Delete and Pause. No test covers this.
- **O2** (`useAbilities.ts:227`): `groupIdentifier.fromCombinedRule(rule)` calls `getDatasourceAPIUid`. That throws `Datasource "<name>" not found` (`utils/datasource.ts:299-307`) for a cloud rule whose data source is not registered. Before, it used `getRulesSourceName`, which does not throw. The test change in `RuleDetails.test.tsx:36,87` (registering `mimirDs`) works around this rather than fixing it.
- **O3** (`GrafanaRuleListItem.tsx:40`): the view link drops `returnTo` (the old code had `createRelativeUrl(..., { returnTo })`), while `DataSourceRuleListItem.tsx:36-42` still sets it.

## Files not reviewed
I read all 14 files in the patch. Three got only a partial check:
- `public/locales/en-US/grafana.json`: I checked only the removed hunk and whether those keys are still used.
- `public/app/types/unified-alerting-dto.ts` and `public/app/features/alerting/unified/rule-list/hooks/prometheusGroupsGenerator.ts`: small one-hunk changes, read in full but checked only against the standards above.

## Summary
Spec has 0 findings (there is no spec). Standards has 8 findings; the worst is #1, the missing `key` on `GrafanaRuleListItem` in `FilterView.tsx:157`.

I did not run eslint, tsc or jest (not installed, and you said not to). Everything above is reasoned from the source, including #1, #7 and O1–O3. O1 is the real risk to raise with the PR author.
