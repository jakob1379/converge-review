## Correctness review: 2FA backup codes (cal.com, base efa6d464a3 to head 54486a059c)

I loaded the `superpowers:requesting-code-review` skill and did the review myself, as instructed, without dispatching a subagent. There is no spec, so I judged against the feature's own claims: codes are single-use, they work for login and for disabling 2FA, and they are shown once when 2FA is enabled. I ran nothing except a one-line `node -e` check, and I wrote no files.

**Verdict: not ready to merge.** One Critical and three Important findings below.

### Critical

**C1. A backup code plus a dummy `totpCode` logs a user in without the password.**
- **Where:** `packages/features/auth/lib/next-auth-options.ts:131` (the new branch), together with the existing gate at about `:119`.
- **Claim:** The password check only runs when no TOTP code is sent: `if (user.password && !credentials.totpCode) { verifyPassword… }`. The new backup-code branch is checked first and never looks at `totpCode`. So a request with any non-empty `totpCode`, any password and one valid `backupCode`:
  1. skips the password check, because `totpCode` is truthy;
  2. enters `if (user.twoFactorEnabled && credentials.backupCode)`;
  3. is authorized with no TOTP check.

  The result is that one static code, often kept in a downloaded `cal-backup-codes.txt`, is enough to log in. Skipping the password when a TOTP code is present already existed before this patch, for the SAML `totpEmail` flow. But that path still required a live TOTP. This patch extends it to a static secret.
- **Evidence (reasoned; I did not run it, because no server was started):** against a running instance:
  ```
  curl -c j -b j $URL/api/auth/csrf   # take csrfToken
  curl -c j -b j -X POST $URL/api/auth/callback/credentials \
    -d "email=<user>&password=wrong&totpCode=000000&backupCode=<valid>&csrfToken=<tok>&json=true"
  ```
  Expected: a session cookie is set. Should be: `incorrect-email-password`.
- **Fix:** verify the password whenever `backupCode` is present. At minimum, change the gate to `!credentials.totpCode || credentials.backupCode`.

### Important

**I1. Codes are compared case-sensitively, and the input does not turn off auto-capitalize.**
- **Where:** `next-auth-options.ts:144`, `apps/web/pages/api/auth/two-factor/totp/disable.ts:61`, `apps/web/components/auth/BackupCode.tsx:17-26`.
- **Claim:** Codes are lowercase hex from `randomBytes(5).toString("hex")`. The server only strips `-` before `indexOf`. The `TextField` has no `autoCapitalize="off"` and the placeholder is `XXXXX-XXXXX`. iOS Safari capitalizes the first letter of a text input, so codes starting with a–f (about 37.5% of them) are rejected. That hits exactly the users who lost their authenticator.
- **Evidence:** `node -e 'const c=["abcde12345"];console.log(c.indexOf("Abcde-12345".replaceAll("-","")))'` prints `-1`.
- **Fix:** `.toLowerCase().trim()` on the server, and `autoCapitalize="off"` on the input.

**I2. Closing the enable dialog on the backup-codes step leaves the settings page showing 2FA as off.**
- **Where:** `apps/web/components/settings/EnableTwoFactorModal.tsx:135`. The parent is `apps/web/pages/settings/security/two-factor-auth.tsx:62-72`.
- **Claim:** After a successful enable, the modal now goes to `DisplayBackupCodes` instead of calling `onEnable()`. The only thing that calls `onEnable` (and so `utils.viewer.me.invalidate()`) is the Close button. Escape, an overlay click or the dialog's X go through `onOpenChange`, which only flips `open`. The switch then stays "unchecked" while 2FA is on in the database. The step also stays at `DisplayBackupCodes`, because `resetState` is not called. Before this patch, `onEnable` ran right away.
- **Evidence (reasoned):** Playwright check. In the "should allow a user to disable 2FA" test, replace `backup-codes-close` with `page.keyboard.press("Escape")`. The existing `expect(…[data-state="checked"]).toBeVisible()` should then fail.
- **Fix:** call `onEnable` when the dialog closes, or block dismissal on this step.

**I3. No test logs in or disables 2FA with a backup code.**
- **Where:** `apps/web/playwright/login.2fa.e2e.ts:12` (`// TODO: add more backup code tests, e.g. login + disabling 2fa with backup`).
- **Claim:** The new auth paths in `next-auth-options.ts` and `disable.ts` have no end-to-end coverage. That covers code consumption and reuse, a wrong code, the missing-codes case, and C1. The only new test clicks the download, copy and close buttons, and leaves two TODOs for checking the file and clipboard content.
- **Related:** the FIXME the patch adds at `:50` confirms the first test's `expect(locator.isChecked()).toBeTruthy()` always passes, because a Promise is truthy. The FIXME was added but the assertion was left as it is.

### Minor

- **M1. Two parallel logins can both use the same code** (`next-auth-options.ts:136-156`). It reads, decrypts, sets the used slot to `null` and writes back with no compare-and-swap or transaction, so concurrent logins with one code both succeed. Reasoned.
- **M2. Users who already had 2FA are told to do something they can't** (`common.json` `missing_backup_codes`). Their `backupCodes` column is NULL, and the message says "Please generate them in your settings", but no regenerate feature exists. The only way to get codes is to disable and re-enable 2FA. Once every code is used, the stored array is all `null`, so the user sees `IncorrectBackupCode` instead of `MissingBackupCodes`, with no count of remaining codes.
- **M3. Bad input in `disable.ts` gives a raw 500.**
  - `disable.ts:49-51` throws `new Error(ErrorCode.InternalServerError)` from an API route, while the rest of the file returns `res.status(500).json(...)`.
  - `disable.ts:61` calls `req.body.backupCode.replaceAll` without a type check, so a non-string `backupCode` also gives an unhandled 500.
- **M4. Copy can fail and still show "copied"** (`EnableTwoFactorModal.tsx:277`). `navigator.clipboard.writeText` is not awaited, so the success toast shows even if the write fails. On self-hosted plain-HTTP (non-localhost) installs, `navigator.clipboard` is undefined and the click throws.
- **M5. A test mock now has a type error that CI won't catch** (`packages/trpc/server/routers/viewer/teams/inviteMember/inviteMemberUtils.test.ts:65`). `const mockUser: User = {…}` lacks the new required `backupCodes` field. The patch updated `builder.ts` but not this file. The only `type-check` script is in `apps/web`, which doesn't include this file, so CI won't flag it. Reasoned.
- **M6. Keyboard users can no longer reach the password show/hide toggle** (`packages/ui/components/form/inputs/Input.tsx:47`). `tabIndex={-1}` removes the toggle from the tab order for every `PasswordField` in the app. This is a shared-component accessibility regression that has nothing to do with the feature.
- **M7. Download is a button inside a link** (`EnableTwoFactorModal.tsx:283`), which is invalid HTML. It works today because `Button` defaults to `type="button"`, which I checked, so it does not submit the enclosing form.

### Checked and fine

- **Login form fields:** `backupCode` and `totpCode` are only sent once registered, and both are cleared when switching modes, so TOTP logins don't accidentally take the backup branch. The zod schema uses `.passthrough()`, so `backupCode` reaches `signIn`.
- **Clearing on disable:** `disable.ts` sets `backupCodes: null` when 2FA is turned off.
- **API v1 exposure:** the user endpoints filter through `schemaUserReadPublic` (a `pick`), so the new column isn't exposed there.
- **Old `security/` folder:** `apps/web/components/security/*` has its own `TwoFactorAuthAPI`, so the new 3-argument `disable()` breaks no callers there.
- **Disable modal errors:** the change from separate `if`s to an `else if` chain also fixes an old bug where `something_went_wrong` overwrote the specific error messages.

### Files not reviewed

None. I read all 16 files in the patch. The migration (`20230804153419_add_backup_codes/migration.sql`), the `schema.prisma` line and the `builder.ts` line are trivial additions and only got a quick look.

I did not run builds, type-check or Playwright, as instructed. C1, I2 and M5 are reasoned from the code. Only the case-sensitivity point in I1 was actually executed.
