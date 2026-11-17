## Correctness review: 2FA backup codes (cal.com, efa6d464a3..54486a059c)

I ran OCR delegate mode in range mode (`--from efa6d464a3 --to HEAD`). It previewed 16 files and I reviewed all 16. Per your instructions I did not apply any fixes, even though the skill says to auto-fix; your "report only" instruction takes precedence. Every claim below is reasoned. I ran no builds or tests, and none of the findings has an executable failing test.

### Findings

**1. Important (security). `packages/features/auth/lib/next-auth-options.ts:121` and `:131`: a backup code alone logs you in, with no password.**
- **The check order:**
  - Line 121 checks the password only when `!credentials.totpCode`. That condition is older than this patch; it exists for the external-TOTP/`totpEmail` flow.
  - Line 131 is new. It takes the backup-code branch whenever `credentials.backupCode` is set, and that branch never looks at `totpCode`.
- **The attack:** POST to the credentials callback with `email`, `password=""`, any non-empty `totpCode` such as `"x"`, and one valid `backupCode`.
  - Line 121 skips the password check because `totpCode` is set.
  - Line 131 takes the backup branch, so TOTP is never verified.
  - Result: authenticated with one static 40-bit secret, the kind of thing that sits in a downloaded `cal-backup-codes.txt` or the clipboard.
- **Before the patch:** a non-empty `totpCode` still had to pass `totpAuthenticatorCheck`. The patch extends an older password-skip so it now also covers a long-lived, exfiltratable credential.
- **Reproduce** (needs a running app; reasoned only): `curl -X POST /api/auth/callback/credentials -d 'csrfToken=<t>&email=<victim>&password=&totpCode=x&backupCode=<valid>'` should return a session.
- **Fix:** require the password check whenever `backupCode` is present, or reject requests that send both `totpCode` and `backupCode`.

**2. Important (security, concurrency). `packages/features/auth/lib/next-auth-options.ts:140-156`: one backup code can be used more than once by concurrent requests.**
- The code reads `user.backupCodes`, decrypts it, finds the index, sets that slot to `null`, and writes the re-encrypted blob back.
- There is no transaction and no compare-and-swap on the old ciphertext (`updateMany where: { id, backupCodes: <old> }` and checking `count === 1` would do it).
- So N parallel logins with the same code all pass. The last write wins, which can also bring back a code that a different concurrent login had just consumed.
- The rate limit (`checkRateLimitAndThrowError`) caps how many requests get through but does not close this window.

**3. Minor. `apps/web/components/settings/EnableTwoFactorModal.tsx:135` and `:269`: closing the backup-codes dialog early leaves the settings page stale.**
- `onEnable()` (which calls `utils.viewer.me.invalidate()`) now runs only from the Close button. Before the patch it ran as soon as enable succeeded.
- If the user dismisses the dialog with Esc or an overlay click, `two-factor-auth.tsx`'s `onOpenChange` just toggles `open`. 2FA is on in the database, but the switch and badge still say disabled.
- Reopening it shows the old `DisplayBackupCodes` step, because `resetState` never ran.

**4. Minor. `apps/web/components/auth/BackupCode.tsx:21`, plus `next-auth-options.ts:144` and `disable.ts:61`: correct codes get rejected over formatting.**
- Codes are lowercase hex (`randomBytes(5).toString("hex")`).
- The comparison is an exact `indexOf` after only stripping `-`. There is no `.toLowerCase()` and no `.trim()`.
- The `XXXXX-XXXXX` placeholder invites uppercase input, and a pasted code with stray whitespace also fails as `IncorrectBackupCode`.

**5. Minor. `apps/web/public/static/locales/en/common.json:2019`, `next-auth-options.ts:136`, `disable.ts:54`: dead-end error for existing 2FA users.**
- Anyone who enabled 2FA before this migration has `backupCodes = null` and gets "No backup codes found. Please generate them in your settings."
- No UI or endpoint regenerates codes while 2FA is on. The only way out is to disable and re-enable 2FA, which means having the authenticator — exactly what someone hitting this message has lost.

**6. Minor. `apps/web/pages/api/auth/two-factor/totp/disable.ts:51` and `:61`: unhandled 500s.**
- Line 51: a missing encryption key in the new branch does `throw new Error(...)` instead of `res.status(500).json(...)`. This copies the existing TOTP branch.
- Line 61: `req.body.backupCode.replaceAll` throws a TypeError if a client sends a non-string truthy `backupCode` (number, array, object). The input is untrusted, so check `typeof === "string"` first.

### Coverage
- total_files: 16
- reviewed_files: 16
- skipped_files: 0
- coverage_rate: 100%

| File | Status |
|---|---|
| `apps/web/components/auth/BackupCode.tsx` | added, reviewed |
| `apps/web/components/auth/TwoFactor.tsx` | modified, reviewed |
| `apps/web/components/settings/DisableTwoFactorModal.tsx` | modified, reviewed |
| `apps/web/components/settings/EnableTwoFactorModal.tsx` | modified, reviewed |
| `apps/web/components/settings/TwoFactorAuthAPI.ts` | modified, reviewed |
| `apps/web/pages/api/auth/two-factor/totp/disable.ts` | modified, reviewed |
| `apps/web/pages/api/auth/two-factor/totp/setup.ts` | modified, reviewed |
| `apps/web/pages/auth/login.tsx` | modified, reviewed |
| `apps/web/playwright/login.2fa.e2e.ts` | modified, reviewed |
| `apps/web/public/static/locales/en/common.json` | modified, reviewed |
| `packages/features/auth/lib/ErrorCode.ts` | modified, reviewed |
| `packages/features/auth/lib/next-auth-options.ts` | modified, reviewed |
| `packages/lib/test/builder.ts` | modified, reviewed |
| `packages/prisma/migrations/20230804153419_add_backup_codes/migration.sql` | added, reviewed |
| `packages/prisma/schema.prisma` | modified, reviewed |
| `packages/ui/components/form/inputs/Input.tsx` | modified, reviewed |

There was no spec, so I can't report spec gaps.

### Not checked
- I did not confirm findings 1 and 2 against a running app.
- The e2e test leaves the backup-code login and disable paths untested; it has its own TODO saying so. That gap is why findings 1 and 2 would get through CI.
