I ran OCR delegate-review in range mode (15e1aa8..8df8503). OCR listed 14 files and marked 10 reviewable. The 4 it excluded are 3 test files and the deleted GrafanaRuleLoader.tsx; I read them as context anyway. I could not run any tests because node_modules is absent and running suites was not allowed, so every finding is reasoned from the source with the evidence cited. I made no edits.

## Findings

1. **public/app/features/alerting/unified/rule-list/components/RuleActionsButtons.V2.tsx:104 — Important.** In the new list view, "Silence notifications" appears in the menu but clicking it does nothing.
   - `GrafanaRuleListItem` now renders `<RuleActionsButtons promRule={rule} …/>` with no `rule` prop.
   - `canSilence` becomes true through the new prom path (`useAbilities.ts:323`, ORed in at `AlertRuleMenu.tsx:96`), so the menu item shows.
   - `handleSilence` sets `showSilenceDrawer=true`, but the drawer only renders when `rulerRuleType.grafana.alertingRule(rule)` is true. Here `rule` is undefined, so the drawer never mounts.
   - `GrafanaGroupLoader.test.tsx` checks that the silence item is present but never clicks it, so the tests miss this.

2. **public/app/features/alerting/unified/components/rule-viewer/AlertRuleMenu.tsx:123 and :165 — Important.** In the list view, Pause and Delete can no longer appear for Grafana rules, even when the user has the permissions.
   - The new `grafanaPause` / `grafanaDelete` abilities feed `canPause` / `canDelete`.
   - The render conditions still also require `rulerRuleType.grafana.rule(rulerRule)` and `canDelete && rulerRule`. `rulerRule` is always undefined in the list view now, so these new abilities never show anything.
   - Before this patch, list items had a ruler rule and showed Pause and Delete.
   - The test confirms the loss: it grants `AlertingRuleDelete` plus folder delete (`GrafanaGroupLoader.test.tsx:58`), then asserts exactly 4 menu items with no Delete (`:207`).

3. **public/app/features/alerting/unified/hooks/useAbilities.ts:309-313, used via AlertRuleMenu.tsx:72/91 — Important.** Duplicate is offered for data-source rules where it was not before.
   - For any non-Grafana prom rule, `AlertRuleMenu` passes `skipToken`. `useAllGrafanaPromRuleAbilities(undefined)` then sets `loading=false`, so `MaybeSupported = AlwaysSupported` and `duplicateSupported = true`.
   - The resulting Duplicate ability is `[true, ctx.hasPermission(AlertingRuleCreate)]`, which is ORed into `canDuplicate`.
   - So any user with Grafana `alert.rules:create` now sees Duplicate on Mimir, Loki or Prometheus rules. This includes rules where the ruler is unavailable (the ruler path's `isRulerAvailable=false` used to hide it) and users without external-rules write permission.
   - It reaches both the old list (`components/rules/RuleActionsButtons.tsx:110` passes `rule.promRule` for cloud rules) and V2 `DataSourceRuleLoader`. It also re-enables Duplicate for plugin-provided Grafana rules when `promRule` is absent.
   - `RulesTable.test` misses it because it mocks `useGrafanaPromRuleAbilities` to `[false,false]`.

4. **public/app/features/alerting/unified/hooks/useAbilities.ts:245 (`useAllAlertRuleAbilities` → `useAllRulerRuleAbilities`) — Important.** Federated Mimir rule groups become editable and deletable in the UI.
   - Base `useAllAlertRuleAbilities` had `isFederated = isFederatedRuleGroup(rule.group)`. The patch routes it through `useAllRulerRuleAbilities`, which hardcodes `isFederated = false` (with a TODO).
   - `useAlertRuleAbility(rule, Update)` in `components/rules/RuleActionsButtons.tsx:57` now returns supported for federated (`source_tenants`) groups, so the old list view shows Edit.
   - This conflicts with `RulesGroup.tsx:69` and `RuleDetailsButtons.tsx:38`, which still treat federated groups as read-only.

5. **public/app/features/alerting/unified/rule-list/FilterView.tsx:157 — Important.** `key={key}` was dropped when `GrafanaRuleLoader` was replaced with `GrafanaRuleListItem` inside `rules.map(...)`.
   - React falls back to index keys for Grafana rows: you get a key warning, and per-row state (open menu, clone redirect, silence drawer, delete modal) can attach to the wrong rule when the filtered list changes.
   - The datasource and unknown branches still pass `key`.

6. **public/app/features/alerting/unified/hooks/useAbilities.ts:227 — Minor.** `useAllAlertRuleAbilities` now calls `groupIdentifier.fromCombinedRule`, which calls `getDatasourceAPIUid`. That function throws `Datasource "X" not found` when the rules source is not a registered data source.
   - The old path (`getRulesSourceName`) never threw, so a CombinedRule whose data source was removed or renamed now crashes the render instead of degrading.
   - Evidence: `RuleDetails.test.tsx` had to be changed to supply `rulesSource: mimirDs` to avoid exactly this throw.

7. **public/app/features/alerting/unified/hooks/useAbilities.ts:323-324 (also Pause, Restore, DeletePermanently) — Minor.** The prom variant gates on `isAlertingRule`; base gated on `isGrafanaManagedAlertRule`, which also covered Grafana recording rules. Export is now unavailable for Grafana recording rules in the list view. The comment above the line says all these rules are Grafana-managed, which does not match what the code checks.

8. **public/app/features/alerting/unified/rule-list/GrafanaRuleListItem.tsx:40 — Minor.** The `href` drops `{ returnTo: createReturnTo() }`, which the deleted `GrafanaRuleListItem` passed. Opening a rule from the list no longer leads back to the filtered list view.

No security bypass on the backend: all of the above are UI permission gates, and the server still enforces RBAC. I checked that `provenance` really is returned by the Prometheus API (`pkg/services/ngalert/api/tooling/definitions/prom.go:188`), so `isProvisionedPromRule` is reliable. `useIsGrafanaPromRuleEditable` matches `useIsRuleEditable`'s Grafana branch.

## Files not reviewed

None. All 10 reviewable files were reviewed, and I also read the 4 OCR-excluded files as context:
- `public/app/features/alerting/unified/components/rules/RuleDetails.test.tsx` (test)
- `public/app/features/alerting/unified/components/rules/RulesTable.test.tsx` (test)
- `public/app/features/alerting/unified/rule-list/GrafanaGroupLoader.test.tsx` (test)
- `public/app/features/alerting/unified/rule-list/GrafanaRuleLoader.tsx` (deleted)

`public/locales/en-US/grafana.json` (2 string keys removed with the deleted file) and `prometheusGroupsGenerator.ts` (ruler prefetch removed) were reviewed with no findings.

Coverage: 10/10 reviewable files.
