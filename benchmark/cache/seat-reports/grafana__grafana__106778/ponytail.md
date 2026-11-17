What this change does: The Grafana-managed alert list view stops calling the ruler API. It renders rules from the Prometheus-style response only (`GrafanaRuleListItem` moves to its own file, and `GrafanaRuleLoader` and `matchRules` are deleted). It also adds a second set of permission hooks that work from a `GrafanaPromRuleDTO` (`useAllGrafanaPromRuleAbilities` and the hooks around it). `AlertRuleMenu` and `RuleActionsButtons.V2` now check both the ruler rule and the Prometheus rule and allow an action if either one allows it.

Role: advisory, over-engineering only. Every finding below is reasoned from reading the code and greps. None comes from a failing test, and I ran no tests, as instructed. Load assumed: a list page with about 80 rules, using the figure in the hook's own comment.

**Should fix**

1. **Pasted copy of the folder-permission check** (`public/app/features/alerting/unified/hooks/useAbilities.ts:339-378`, called at :289) — Important
   - What this is: `useIsGrafanaPromRuleEditable` plus its own result interface `IsGrafanaPromRuleEditableResult`.
   - Problem: It repeats the Grafana branch of `useIsRuleEditable` (`hooks/useIsRuleEditable.ts`): `useFolder`, then `getRulesPermissions`, then `hasPermissionInMetadata(update/delete, folder)`. The call site even says `// duplicate`. Any fix to how folder permissions are checked now has to be made in two places.
   - Fix: Have `useIsRuleEditable` (or a small shared folder-permission hook) take the folder UID and reuse it. At minimum, reuse the existing `ResultBag` type instead of the new interface. About -30 lines.
   - If we skip it: The two copies will drift. One list (old or new) will show Edit or Delete buttons the other one hides.

2. **A second copy of the whole ability table** (`public/app/features/alerting/unified/hooks/useAbilities.ts:287-337` vs `:231-285`) — Important
   - What this is: `useAllGrafanaPromRuleAbilities` builds the same 10-entry ability map as `useAllRulerRuleAbilities`. Only the inputs differ: provisioned or not, the silence pair, and "supported".
   - Problem: Both maps hold the same rules: immutable rules block Update and Delete, plugin rules block Duplicate, admin-only DeletePermanently. These rules now live in two places that must change together.
   - Fix: Pull the map into one pure function, `buildRuleAbilities({ loading, supported, isProvisioned, isPluginProvided, isGrafanaAlerting, isEditable, isRemovable, canSilence, exportAllowed, rulesSourceName })`. Both hooks then compute their inputs and call it. About -35 lines.
   - If we skip it: A permission change made in one hook only gives different answers in the old list and the new list.

3. **A homemade `skipToken` symbol where `undefined` already works** (`public/app/features/alerting/unified/hooks/useAbilities.ts:380-405`; callers `components/rule-viewer/AlertRuleMenu.tsx:73` and `rule-list/components/RuleActionsButtons.V2.tsx:57`) — Minor
   - Problem: `useAllGrafanaPromRuleAbilities` already accepts `undefined`. The new `Symbol('ability-skip-token')` is only converted back to `undefined` (`rule === skipToken ? undefined : rule`). It also uses the same name as RTK Query's `skipToken`, which this folder already imports (for example `hooks/useFolder.ts:16` and `rule-list/DataSourceRuleLoader.tsx:34`), so readers will mix the two up. The ruler hooks next to it just take `RulerRuleDTO | undefined`.
   - Fix: Type the parameter as `GrafanaPromRuleDTO | undefined`. Delete the symbol, the type and both conversions. Callers pass `... ? promRule : undefined`.

4. **AlertRuleMenu: 10 unpacking lines and the same action list written twice** (`public/app/features/alerting/unified/components/rule-viewer/AlertRuleMenu.tsx:56-100`) — Minor
   - Problem: The same five-item action list is written twice. Each ability is then unpacked from both sources and combined by hand: 10 destructurings and 5 near-identical `||` lines. The inline arrays are also new on every render, so the `useMemo([abilities, actions])` inside `useRulerRuleAbilities` and `useGrafanaPromRuleAbilities` never reuses its result.
   - Fix: Put the action list in one module-level constant, `MENU_ACTIONS`, used by both hooks. Then write `const [canPause, canDelete, canDuplicate, canSilence, canExport] = MENU_ACTIONS.map((_, i) => ruler[i].every(Boolean) || grafana[i].every(Boolean));`. About 45 lines become about 10.

**Nice to have**

5. **Dead `operation` prop on the new GrafanaRuleListItem** (`public/app/features/alerting/unified/rule-list/GrafanaRuleListItem.tsx:22,30,60`) — Minor
   - Problem: After this patch, neither caller (`GrafanaGroupLoader.tsx:70`, `FilterView.tsx:157`) passes `operation`. The only caller that did, the Creating branch in GrafanaGroupLoader, was deleted by this patch.
   - Fix: Delete the prop and the `RuleOperation` import.

6. **Leftover null checks in GrafanaRuleListItem** (`public/app/features/alerting/unified/rule-list/GrafanaRuleListItem.tsx:41,42,45,51`) — Minor
   - Problem: `rule` is now required, but the code still writes `rule?.health`, `rule?.lastError` and `rule?.isPaused`. Inside the `prometheusRuleType.grafana.alertingRule(rule)` branch it still recomputes `promAlertingRule = rule && rule.type === PromRuleType.Alerting ? rule : undefined`. These were carried over from when `rule` was optional.
   - Fix: Use `rule.health` and the others directly, and `rule.state` and `rule.totals` in the alerting branch. Drop the `PromRuleType` import.

7. **Orphaned `RulerRuleLoadingError`** (`public/app/features/alerting/unified/rule-list/components/AlertRuleListItemLoader.tsx:24`) — Minor
   - Problem: Its only user was the deleted `GrafanaRuleLoader.tsx`. A grep of `public/app` finds no other reference.
   - Fix: Delete the export.

8. **`getIsProvisioned` helper is 11 lines for a one-line rule** (`public/app/features/alerting/unified/rule-list/components/RuleActionsButtons.V2.tsx:118-128`) — Minor
   - Fix: `const isProvisioned = rule ? isProvisionedRule(rule) : !!promRule && isProvisionedPromRule(promRule);`.
   - Related: the `logWarning` plus `return undefined` fallback in `getEditableIdentifier` (:130-150) is never reached by current callers. DataSourceRuleLoader, DataSourceGroupLoader and StateView always pass a ruler rule, and GrafanaRuleListItem always passes a Grafana Prometheus rule. It is cheap, so keep it or drop it.

**Outside my role, passing on for the correctness reviewer** (reasoned, not tested):
- `hooks/useAbilities.ts:243-245`: `useAllAlertRuleAbilities` (the old list view, used through `useAlertRuleAbility`/`useAlertRuleAbilities`) used to set `isFederated = isFederatedRuleGroup(rule.group)`. It now delegates to `useAllRulerRuleAbilities`, which hard-codes `isFederated = false`. Federated Mimir rules in the old list can now show as editable or deletable.
- `rule-list/GrafanaRuleListItem.tsx:40`: the view link no longer includes `{ returnTo }`, which the deleted GrafanaRuleLoader added. Going from the list to a rule and back loses the user's place.

Verdict: Ship after 1 and 2 if you care about lean code. Nothing here blocks the merge on over-engineering grounds alone.
Lean: about -110 lines possible.

Files not reviewed:
- `public/app/features/alerting/unified/components/rules/RuleDetails.test.tsx`, `components/rules/RulesTable.test.tsx`, `rule-list/GrafanaGroupLoader.test.tsx`: test files. I only skimmed them through grep (RulesTable.test mocks both new hooks, so collapsing `useGrafanaPromRuleAbility` or `skipToken` touches its mocks). I did not review them in depth.
- `public/locales/en-US/grafana.json`: only removes two translation keys that belonged to the deleted loader. Nothing to review for this role.

Not checked: I ran no tests or type checks, as instructed. Line numbers are from the patched checkout.
