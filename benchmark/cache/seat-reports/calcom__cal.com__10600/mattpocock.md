Code review of the 2FA backup codes patch (mattpocock-skills:code-review, both axes done directly, no sub-agents)

Fixed point: efa6d464a38e60ceeeb88f40668c1c4ac4bfaf54 (it resolves). Patch: pinned.patch, 715 lines, 16 files, 20 commits from d1278e8980 to 54486a059c.

## Spec

There is no spec, so this axis has nothing to check against. None of the 20 commit messages references an issue. No Spec findings.

## Standards

**Sources found:**
- `CONTRIBUTING.md`: lint must pass, a full production build must pass, e2e tests via `yarn test-e2e`.
- `.github/PULL_REQUEST_TEMPLATE.md`: checklist that includes "added tests that prove my fix is effective or that my feature works".
- `.eslintrc.js` → `packages/config/eslint-preset.js`, plus the `@calcom/eslint` rules (dayjs imports, web storage, Prisma enum imports).
- `packages/config/prettier-preset.js`: printWidth 110 and an import-order rule.

The repo has no AGENTS.md, CLAUDE.md, .cursor rules or CODING_STANDARDS file. The `.claude/` folder is untracked harness config (`git ls-files .claude` is empty), so I did not treat it as a source.

**Hard violations of documented standards:** none found. Every rule the tooling can enforce (prettier, eslint, import order) is skipped as the skill directs. I could not run them because `node_modules` is absent and I was told not to install. One line to watch: `apps/web/pages/auth/login.tsx:221` has a nested ternary that is exactly 110 columns, right at printWidth.

**Findings (all judgement calls, none Critical or Important):**

1. **Minor** – `apps/web/playwright/login.2fa.e2e.ts:12`, `:110-125`
   - **Claim:** the feature's core behaviour has no tests: logging in with a backup code, a used code being rejected on second use, and disabling 2FA with a backup code.
   - **Evidence:** the patch admits this itself: `// TODO: add more backup code tests, e.g. login + disabling 2fa with backup`, `// TODO: check file content`, `// TODO: check clipboard content`. The only new e2e steps click Download, Copy and Close. This is a soft breach of the PR template checklist and the CONTRIBUTING e2e guidance.
   - It is reasoned, with no failing command. The gap matters most for the single-use consumption in `packages/features/auth/lib/next-auth-options.ts:146-156`, the security property here, and no test covers it.
   - The patch also adds a `// FIXME` (line ~50) saying the existing `expect(...isChecked()).toBeTruthy()` passes even when the switch is off. That assertion is older than this patch, but the patch documents it instead of fixing it.

2. **Minor (baseline smell: possible Mysterious Name)** – `apps/web/components/auth/BackupCode.tsx:7`
   - **Claim:** the component is declared as `export default function TwoFactor(...)` in a file called `BackupCode.tsx`, copied from `TwoFactor.tsx`. Imports work because it is a default export, but React DevTools and stack traces will show two different components as `TwoFactor`.

3. **Minor (baseline smell: possible Duplicated Code)** – `apps/web/pages/api/auth/two-factor/totp/disable.ts:47-66` and `packages/features/auth/lib/next-auth-options.ts:131-145`
   - **Claim:** the same backup-code check appears in both places: encryption-key guard, missing-codes guard, `JSON.parse(symmetricDecrypt(...))`, `replaceAll("-", "")` and `indexOf`. The two copies already behave differently on purpose: login consumes the code, disable wipes them all.
   - One shared helper in `@calcom/features/auth/lib` would keep the normalisation and validation rules in one place.

4. **Minor (repo convention, not written down)** – `apps/web/pages/auth/login.tsx:157-158`
   - **Claim:** the new `IncorrectBackupCode` and `MissingBackupCodes` messages are handled with extra `else if` branches. The file already has an `errorMessages` map at lines 73-79 for exactly this mapping, and its fallback at line 160 would cover these codes if they were added to the map.

**Outside my brief, not scored:** `apps/web/pages/api/auth/two-factor/totp/disable.ts:61` calls `req.body.backupCode.replaceAll(...)` on a request body that is never validated. A truthy value that is not a string (for example a JSON number) throws a TypeError and returns 500 instead of 400. The reasoning only; I did not run it.

**Files not reviewed:** none. I read all 16 files in the patch with their surrounding source. The migration SQL, `schema.prisma`, `packages/lib/test/builder.ts`, `packages/ui/components/form/inputs/Input.tsx` and the `en/common.json` additions are trivial and break no documented rule. The reused keys `close`, `copy`, `download` and `go_back` already exist in `en/common.json`.

**Summary:** Standards has 4 findings, all Minor judgement calls with no hard breach; the worst is that the backup-code login, single-use and disable paths are untested. Spec has 0 findings because there is no spec.

I did not run lint, prettier, the typecheck or any tests (no `node_modules`, and I was told not to install), so the formatting and type correctness of the patch are unverified.
