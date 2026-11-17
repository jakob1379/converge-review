## Code review: keycloak 7fd37690c4..4def149a50, "Fix NPE when accessing group concurrently" (Closes #40368)

**How I ran it.** I invoked `mattpocock-skills:code-review` and ran both of its axes myself. The skill wants parallel sub-agents, but your brief forbids spawning agents, so your brief won. The fixed point resolves and the diff is non-empty: one commit, 4 files, +51/−11. I did not fetch issue #40368, so the only intent I used is the commit title, as you said. Standards sources were `CONTRIBUTING.md` and `docs/tests-development.md`, plus the skill's code-smell baseline. Nothing was built or run.

**Spec in one line.** When a cached group is deleted while a list request is being served, `modelSupplier.get()` returns null and `getSubGroupsCount()` throws an NPE. The patch null-guards that one method.

## Standards

1. **Important: the fix breaks the documented `GroupModel` contract.** `model/infinispan/src/main/java/org/keycloak/models/cache/infinispan/GroupAdapter.java:275`
   - **Claim:** `getSubGroupsCount()` can now return `null`.
   - **Evidence:** the interface Javadoc at `server-spi/src/main/java/org/keycloak/models/GroupModel.java:293-297` says: "@return The number of groups beneath this group. Never returns {@code null}."
   - **Effect:** the null flows through `GroupUtils.populateSubGroupCount` (`services/.../utils/GroupUtils.java:90`) into `GroupRepresentation.subGroupCount`. The admin UI checks `subGroupCount !== 0` in `GroupPickerDialog.tsx:324,379` and `Group.tsx:127`, and uses `subGroupCount!` at `GroupPickerDialog.tsx:119`. So `null` reads as "has subgroups" there.
   - **Fix:** return `0L`, which keeps the contract, or update the Javadoc.
   - This claim is reasoned. A model-level test that deletes the group and then calls `getSubGroupsCount()` on a stale cached adapter, expecting non-null, would fail. I did not write or run it.

2. **Minor: changes unrelated to the fix.** `services/src/main/java/org/keycloak/utils/GroupUtils.java:98-110` deletes the unused private `groupMatchesSearchOrIsPathElement`. `model/infinispan/.../entities/CachedGroup.java:61` adds `@Override`. Neither is needed for the fix. `CONTRIBUTING.md` says "No changes to code not directly related to your PR" and "Do not format or refactor code that is not directly related to your contribution."

3. **Minor, judgement call: Mysterious Name.** `tests/base/.../GroupTest.java:121`: `groupUuuids` has three u's.

## Spec

1. **Important: only one of four identical NPE sites is fixed.** `GroupAdapter.java:256, 262, 268`
   - **Claim:** the three `getSubGroupsStream(...)` overloads still do `return modelSupplier.get().getSubGroupsStream(...)` with no null check. They hit the same NPE when the group is deleted concurrently.
   - **Evidence:** one is reachable from REST at `services/.../admin/GroupResource.java:180` (`group.getSubGroupsStream(search, exact, -1, -1)`, the sub-groups endpoint).
   - The intent is "accessing group concurrently", not "counting subgroups concurrently", so this is a partial fix. The claim is reasoned. A copy of the new test that calls `managedRealm.admin().groups().group(id).getSubGroups(...)` in the reader loop would be the reproducer. I did not run it.

2. **Minor: the regression test is racy and can miss the bug.** `tests/base/.../GroupTest.java:117-158` (`createMultiDeleteMultiReadMulti`)
   - The reader thread is never joined. After `deletedAll.set(true)` the assertion runs at once, so an exception from a request still in flight can land after `assertThat` and go unseen.
   - The thread can also outlive the test and run against the realm during cleanup.
   - Whether it reproduces the bug depends on timing, so it can pass on the unpatched code.
   - **Fix:** keep the `Thread` reference and call `join()` before asserting.
   - Reasoned. I traced that the test's call path (`groups(null, 0, MAX, true)` → `populateGroupHierarchyFromSubGroups` → `populateSubGroupCount`, with `subGroupsCount` defaulting to true) does reach the fixed method.

3. **Scope creep:** the `GroupUtils` dead-code removal and the `CachedGroup` `@Override`, as in Standards item 2.

**Summary.** Standards: 3 findings; the worst is that `getSubGroupsCount()` can now return null against the documented never-null contract. Spec: 3 findings; the worst is the three `getSubGroupsStream` overloads that still NPE under the same race.

**Files not reviewed:** none. All 4 patch files were reviewed.

Not checked: issue #40368 itself, and whether `LazyLoader` (used by `cached.getSubGroups`, `getAttributes` and `getRoleMappings`) handles a null model on the same race. Both claims above are reasoned; I wrote and ran no tests.
