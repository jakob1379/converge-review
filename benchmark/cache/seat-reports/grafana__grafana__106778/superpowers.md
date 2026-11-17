Code review of the Grafana alerting PR that removes ruler usage from the alert list view (`pinned.patch`, base 15e1aa8855, head 8df8503710).

Method: I loaded `superpowers:requesting-code-review` and did the review myself, with no subagent. I read the whole patch and the source around it: `useIsRuleEditable`, `useCanSilence`, `SilenceGrafanaRuleDrawer`, `groupIdentifier.fromCombinedRule`, `access-control.ts`, the v1 `RuleActionsButtons`, `DataSourceGroupLoader`, `StateView`, and the backend prom API (`api_prometheus.go` does emit `provenance`, so the new `provenance` field on `GrafanaPromRuleDTO` is real data). I installed nothing and ran no tests. Every claim below is reasoned from the code. For the Important ones I give a test that should fail on the patched code.

## Findings

1. **`public/app/features/alerting/unified/rule-list/components/RuleActionsButtons.V2.tsx:104-106` — Important. In the new list view, "Silence notifications" is shown but clicking it does nothing.**
   - Claim: `GrafanaRuleListItem` now passes only `promRule`, so `rule` is undefined. The drawer only renders when `rulerRuleType.grafana.alertingRule(rule) && showSilenceDrawer`. That is always false here: the click sets state and nothing appears.
   - Evidence: the menu item is enabled through the new prom path, `[silenceSupported, canSilenceInFolder && isAlertingRule]`. `GrafanaGroupLoader.test.tsx` asserts the item is present but never clicks it. `SilenceGrafanaRuleDrawer` only reads `rulerRule.grafana_alert.uid` (lines 21 and 44), so the prom rule's `uid` would be enough.
   - Failing test: in `GrafanaGroupLoader.test.tsx`, click More, click Silence, then `expect(await screen.findByRole('dialog')).toBeInTheDocument()`. It finds no drawer.

2. **`public/app/features/alerting/unified/components/rule-viewer/AlertRuleMenu.tsx:123` and `:165` — Important. Pause and Delete are gone from the list view for every Grafana rule, even for users who have the permissions.**
   - Claim: both menu items are still gated on `rulerRule` (`rulerRuleType.grafana.rule(rulerRule)` and `canDelete && rulerRule`). The list no longer supplies a ruler rule, so the new `grafanaPauseAbility` and `grafanaDeleteAbility` are computed and never used.
   - Evidence: `GrafanaGroupLoader.test.tsx:207` asserts `menuItems.length).toBe(4)` (silence, duplicate, copy link, export). Its `beforeEach` grants `AlertingRuleUpdate` and `AlertingRuleDelete`, and `ui.menuItems.delete` is defined at line 42 but never asserted. The test locks in the regression.
   - Delete only needs `identifier` (`showDeleteModal(identifier, groupIdentifier)`), so the `rulerRule &&` guard can go. Pause needs the ruler group, so it needs a design decision.
   - Failing test: the same test with `expect(ui.menuItems.delete().get()).toBeInTheDocument()`.

3. **`public/app/features/alerting/unified/hooks/useAbilities.ts:309-313`, used at `AlertRuleMenu.tsx:91-92` — Important. Duplicate is wrongly enabled for non-Grafana rules.**
   - Claim: when called with `skipToken` (the rule is not a Grafana rule), `useIsGrafanaPromRuleEditable(undefined)` returns `loading: false`. So `MaybeSupported` becomes `AlwaysSupported`, and Duplicate becomes `toAbility(true, AlertingRuleCreate)`, the Grafana permission.
   - `AlertRuleMenu` ORs this with the ruler result. Any user with Grafana `alert.rules:create` (Editors) now sees Duplicate on:
     - datasource rules whose source has no ruler (`isRulerAvailable=false`), which the base correctly hid;
     - Mimir/Loki rules for users without `AlertingRuleExternalWrite`.
   - Affects the v1 list (`RuleActionsButtons.tsx:110`), the rule viewer and the v2 datasource list.
   - Evidence: `RulesTable.test.tsx` hides this because it mocks `useGrafanaPromRuleAbilities` to return `[false,false]` for cloud rules.
   - Failing test: render `AlertRuleMenu` for a cloud rule from a Prometheus datasource without ruler config, `grantUserPermissions([AlertingRuleCreate])`, open More, and `expect(byRole('menuitem',{name:/duplicate/i}).query()).not.toBeInTheDocument()`.
   - Fix: return `NotSupported` across the board when `rule` is undefined.

4. **`public/app/features/alerting/unified/hooks/useAbilities.ts:222-228` and `:243-245` — Important. Federated Mimir rules show Edit again in the v1 list.**
   - Claim: `useAllAlertRuleAbilities(CombinedRule)` used to compute `isFederated = isFederatedRuleGroup(rule.group)`. It now delegates to `useAllRulerRuleAbilities`, which hardcodes `isFederated = false`. Update, Delete, Pause and Restore stop being blocked for groups with `source_tenants`.
   - Still-live consumers: `components/rules/RuleActionsButtons.tsx:57` (Edit button), `RuleDetailsButtons.tsx`, `GrafanaRuleQueryViewer.tsx`.
   - Failing test: a v1 `RulesTable` test without the `useAbilities` mock, a cloud rule whose `group.source_tenants=['t1']`, and `AlertingRuleExternalWrite` granted. Expect no Edit button; the button appears.

5. **`public/app/features/alerting/unified/rule-list/GrafanaRuleListItem.tsx:40` — Important. Opening a Grafana rule from the list loses the user's filters when they come back.**
   - Claim: the old item built the view link with `createRelativeUrl(..., { returnTo })`; the new one drops `returnTo`. `DataSourceRuleListItem.tsx:36-42` still passes it, so the two list item types now behave differently.
   - Evidence: the deleted `GrafanaRuleLoader.tsx` (patch line 1222) had `{ returnTo }`.
   - Failing test: assert the rule link `href` contains `returnTo=` in `GrafanaGroupLoader.test.tsx`.

6. **`public/app/features/alerting/unified/rule-list/FilterView.tsx:157` — Important. The new Grafana list item is rendered without a React key.**
   - Claim: the `case 'grafana'` branch renders `<GrafanaRuleListItem …>` with no `key`; the old `GrafanaRuleLoader` had `key={key}`. React logs a missing-key `console.error`.
   - `public/test/setupTests.ts:16-21` turns on `jest-fail-on-console` under `process.env.CI`. Any FilterView test that renders Grafana rules should therefore fail in CI. Without stable keys, per-row state (open menu, modals) can also attach to the wrong rule as filter results stream in.
   - Command: `CI=true yarn jest public/app/features/alerting/unified/rule-list/FilterView.test.tsx` (not run).

7. **`public/app/features/alerting/unified/hooks/useAbilities.ts:301` and `:324-329` — Minor. Grafana recording rules lose actions in the new list.**
   - Claim: the comment says all `GrafanaPromRuleDTO` rules are Grafana-managed, but the code uses `prometheusRuleType.grafana.alertingRule`. So ModifyExport, Pause, Restore and DeletePermanently are NotSupported for recording rules.
   - The ruler path it replaces used `rulerRuleType.grafana.rule`, which includes recording rules. Result: Export no longer appears for Grafana recording rules in the new list.
   - Should likely be `prometheusRuleType.grafana.rule(rule)`; keep the alerting-only check for Silence.

8. **`public/app/features/alerting/unified/hooks/useAbilities.ts:227` — Minor. Ability checks can now throw during render when a rule's datasource is not registered.**
   - Claim: `useAllAlertRuleAbilities` now calls `groupIdentifier.fromCombinedRule`, which calls `getDatasourceAPIUid`. That throws `Datasource "<name>" not found` when the name is not registered; the old `getRulesSourceName` path never threw.
   - Evidence: `RuleDetails.test.tsx` had to switch its fixture to `{ rulesSource: mimirDs }` for this reason.
   - Low production risk, since v1 CombinedRules come from configured datasources, but this is a new throw path inside a hook.

9. **Test coverage — Minor.**
   - `RulesTable.test.tsx` mocks every ability hook, including the new prom path. The OR-merge logic in `AlertRuleMenu` and `RuleActionsButtons.V2`, `useAllGrafanaPromRuleAbilities` and `useIsGrafanaPromRuleEditable` are never exercised unmocked there. That is how findings 3 and 4 slip through.
   - The mocks for `useGrafanaPromRuleAbility` in the Grafana "Edit" tests do nothing, because v1 `RuleActionsButtons` never calls it.
   - `GrafanaGroupLoader.test.tsx` is the only real integration coverage. It never clicks Silence or Duplicate and it asserts the Pause/Delete regression (finding 2).
   - The Creating/Deleting tests were deleted along with the feature, which is consistent with the PR. `GrafanaRuleListItem`'s `operation` prop now has no caller.

## Files not reviewed

None were skipped. Every file in the patch was reviewed:
- `AlertRuleMenu.tsx`
- `RuleDetails.test.tsx`
- `RulesTable.test.tsx`
- `useAbilities.ts`
- `FilterView.tsx`
- `GrafanaGroupLoader.test.tsx`
- `GrafanaGroupLoader.tsx`
- `GrafanaRuleListItem.tsx`
- `GrafanaRuleLoader.tsx` (deleted)
- `RuleActionsButtons.V2.tsx`
- `prometheusGroupsGenerator.ts`
- `utils/rules.ts`
- `unified-alerting-dto.ts`
- `public/locales/en-US/grafana.json` (I checked that the two removed keys have no remaining references)

Not checked: I ran no type-check, lint or jest, as instructed. Every failure claim above is reasoned, not observed. I also did not confirm that the base `eslint.config.js` turns on `react/jsx-key`, so the lint side of finding 6 is unconfirmed.
