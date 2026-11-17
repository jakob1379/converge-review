Review of the 2FA backup-codes patch, limited to over-engineering (pinned.patch, base efa6d464 to HEAD 54486a05). I read the code around the patch in the repo. I ran nothing and edited nothing.

**What this change does:** Turning on 2FA now creates 10 backup codes. They are encrypted and stored in a new `users.backupCodes` column, then shown once with copy and download buttons. On the login page and in the "disable 2FA" dialog, a user can choose "Lost access" and type a backup code instead of the TOTP code (the 6-digit code from the authenticator app). At login a used code is set to null. Disabling 2FA clears all codes.

Assumed load: a hosted multi-tenant SaaS. None of the findings depend on scale.

No finding is Critical or Important. The extra code is small. The two real problems are a copy-pasted verification block and a leftover prop that breaks the show-password toggle.

**Should fix**

1. **Backup-code check is written twice** (`packages/features/auth/lib/next-auth-options.ts:131-151` and `apps/web/pages/api/auth/two-factor/totp/disable.ts:48-64`). Severity: Minor.
   - **What this is:** Both places check for the encryption key, check that codes exist, decrypt and `JSON.parse` them, strip dashes, then `indexOf` the code.
   - **Problem:** This is security code that must change in both places together. Changing how input is cleaned (case, whitespace) or adding a constant-time compare means two edits. Missing one makes login and disable accept different inputs. The TOTP check was already duplicated before this patch, so this follows an existing bad habit rather than starting one.
   - **Fix:** Add one helper next to `totpAuthenticatorCheck` in `@calcom/lib` that returns `{ codes, index }` or throws `ErrorCode`, and call it from both places. About 10 lines fewer.
   - **If we skip it:** The two paths drift apart the first time someone hardens one of them.
   - Evidence: reasoned, by reading the two blocks side by side.

2. **Leftover `type="password"` breaks the show-password toggle** (`apps/web/components/settings/EnableTwoFactorModal.tsx:176`). Severity: Minor.
   - **What this is:** The patch swapped `TextField` for `PasswordField` but kept `type="password"`.
   - **Problem:** `PasswordField` (`packages/ui/components/form/inputs/Input.tsx:36-39`) sets `type={isPasswordVisible ? "text" : "password"}` and then spreads `{...props}` after it. The caller's `type="password"` wins every time, so the eye button never reveals the password.
   - **Fix:** Delete the line.
   - **If we skip it:** The toggle the patch just added does nothing in this dialog.
   - Evidence: reasoned from the prop-spread order.

3. **Two error branches in `login.tsx` repeat a lookup table that already exists** (`apps/web/pages/auth/login.tsx:157-158`). Severity: Minor.
   - **What this is:** New `else if` lines map `IncorrectBackupCode` and `MissingBackupCodes` to messages.
   - **Problem:** The fallback on the next line, `errorMessages[res.error] || ...`, already handles exactly this. The `errorMessages` table sits at lines 73-79.
   - **Fix:** Add the two codes to `errorMessages` and delete both branches.
   - **If we skip it:** Error codes get mapped in two places in one file.

4. **Unrelated UI change that hurts keyboard users** (`packages/ui/components/form/inputs/Input.tsx:44-51`). Severity: Minor.
   - **What this is:** `tabIndex={-1}` on the show/hide-password button. This affects every `PasswordField` in the app.
   - **Problem:** It is outside the feature's scope. It also takes the toggle out of the tab order, so keyboard users can no longer reach it. This is an accessibility regression in a shared component.
   - **Fix:** Drop it from this PR.
   - **If we skip it:** Every password field in the app loses keyboard access to the toggle.

**Nice to have**

5. **Blob URL bookkeeping can go** (`EnableTwoFactorModal.tsx:65, 94-99, 283`). Severity: Minor.
   - **What this is:** There is a state variable for an object URL, a `Blob`, and a `revokeObjectURL`. The newest URL is never revoked on close or unmount.
   - **Fix:** Build the joined text once and use `href={"data:text/plain;charset=utf-8," + encodeURIComponent(text)}`. Reuse the same string for the clipboard at line 278, which currently re-runs `map(formatBackupCode).join("\n")`.
   - **Effect:** Removes one state variable, the Blob and the revoke call, about 6 lines.

6. **Copy-paste leftovers in the new component** (`apps/web/components/auth/BackupCode.tsx:13`).
   - The component in `BackupCode.tsx` is exported as `function TwoFactor`. Rename it to `BackupCode`.

7. **Checks that cannot fail** (`apps/web/pages/api/auth/two-factor/totp/disable.ts:48, 69`).
   - Line 36 already returns early when `!user.twoFactorEnabled`, so `user.twoFactorEnabled &&` on line 48 and `else if (user.twoFactorEnabled)` on line 69 are always true. The second one was there before the patch, but the patch rewrote that line.
   - The `CALENDSO_ENCRYPTION_KEY` check is also copied into both branches. Hoist it above the branches.
   - About 4 lines fewer.

8. **Redundant fragment** (`EnableTwoFactorModal.tsx:201, 207`). The `<>...</>` wraps a single `<div>`. Delete both lines.

9. **Comment noise in the e2e test** (`apps/web/playwright/login.2fa.e2e.ts:12, 50-51, 115, 120`). Three TODOs and a FIXME about an older test that this patch did not change. The TODO at line 12 admits that backup-code login and backup-code disable have no test. That is the actual missing test for the security path; the TODOs only label the gap. Delete the comments, or replace one of them with a backup-code login test.

Verdict: Ship after fixing 2 (one-line delete) and 4 (revert the out-of-scope change). Fix 1 before this security logic changes again.

Lean: about 30 lines could be removed.

Files reviewed: all 16 in the patch. The locale JSON, `ErrorCode.ts`, the migration, `schema.prisma` and `test/builder.ts` were trivial and had no findings. Nothing was skipped.

Not checked (outside my over-engineering seat): backup codes are compared with a plain `indexOf`, not a constant-time compare. Login has a check-then-write race, so two parallel logins could both use the same code. `EnableTwoFactorModal` does not call `resetState` when the dialog is closed with Esc or a click outside (`onOpenChange`), so the old step and password may still be there when it reopens. These are for the correctness and security reviewers.
