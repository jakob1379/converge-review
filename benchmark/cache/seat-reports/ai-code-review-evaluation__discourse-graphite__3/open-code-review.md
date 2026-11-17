## Review of 5f8a130277 (base e25638dab0): BlockedEmail and EmailValidator

I used `open-code-review:delegate-review`. Its preview ran in range mode (`--from e25638dab0 --to 5f8a130277`) and found 10 files, 8 of them reviewable. I applied no fixes: your report-only instruction overrides the skill's auto-fix step. I wrote nothing to the repo and ran no tests, so every claim below is reasoned from the code. Where a spec would fail, I name it.

### Findings

**1. Important: the email block is case-sensitive, so a change of letter case gets past it.** `app/models/blocked_email.rb:12`
- **Claim:** `BlockedEmail.where(email: email).first` is an exact, case-sensitive match on Postgres (`=`). Neither side is normalised.
- **Evidence:**
  - `User.new_from_params` assigns `params[:email]` as typed (`app/models/user.rb:87`). User has no downcase or `before_validation` hook.
  - `UsersController#change_email` lowercases only the domain (`Email.downcase` in `lib/email.rb`), so the local part keeps its case there too.
  - If `bad@spammers.org` is blocked, a signup as `Bad@spammers.org` passes.
  - The domain whitelist/blacklist next to it is case-insensitive (`Regexp.new(..., true)`), so the two checks behave differently.
- **Failing spec (reasoned):**
  `Fabricate(:blocked_email, email: 'bad@spammers.org'); BlockedEmail.should_block?('Bad@spammers.org').should be_true`
- **Fix:** store emails lowercased and stripped, and compare with `where('lower(email) = ?', email.downcase.strip)`.

**2. Important: the hit counter is updated during validation, so the stats are double-counted or silently lost.** `app/models/blocked_email.rb:13-17`, `lib/validators/email_validator.rb:13`, `app/controllers/users_controller.rb:168,172`
- **Claim:** `should_block?` saves a record every time a User with a changed email is validated. That gives wrong numbers in three ways:
  - **Double count:** `UsersController#create` calls `user.valid?` (line 168, always evaluated before `&&`) and then `user.save`, which validates again. A `do_nothing` match that signs up successfully adds 2 per attempt.
  - **Lost on rollback:** in Rails 3.2.12 (Gemfile.lock), `save` runs validations inside `with_transaction_returning_status`, which raises `ActiveRecord::Rollback` when validation fails. So when an email is actually blocked, the increment done inside `save` is rolled back.
  - **Never recorded:** `create` only records a blocked hit because of the extra `valid?` call outside the transaction. Two flows have no such call, so blocked attempts there are never counted:
    - `EmailToken.confirm` runs `save!` inside `User.transaction` and rescues `RecordInvalid`.
    - Invite redemption runs `User.create_for_email` (`save!`) inside `Invite.transaction`.
  - The commit's stated goal of tracking how many times each address is blocked is therefore unreliable.
- **Failing spec:** create `Fabricate(:blocked_email, email: e, action_type: BlockedEmail.actions[:do_nothing])`, `xhr :post, :create` with that email and valid other params, and expect `match_count` to change by 1. It changes by 2.
- **Spec limit:** transactional fixtures swallow the nested rollback, so specs cannot show the lost-on-rollback case.
- **Fix:** take the stat update out of validation, or do it outside the user's transaction with an atomic `update_all`.

**3. Minor: concurrent attempts lose counter updates.** `app/models/blocked_email.rb:14-16`
- `record.match_count += 1; record.save` is read-modify-write, so parallel signup attempts lose increments.
- `BlockedEmail.where(id: record.id).update_all(['match_count = match_count + 1, last_match_at = ?', Time.zone.now])` is atomic. It also skips the uniqueness `SELECT` that `save` runs on every check.
- The return value of `save` is ignored.

**4. Minor: the signup form treats every server email error as permanent and hides the real reason.** `app/assets/javascripts/discourse/controllers/create_account_controller.js:274-276, 69-74`
- Any `result.errors.email` adds the address to `rejectedEmails` for good, including "has already been taken" and the domain whitelist/blacklist message.
- The field then shows the generic `user.email.invalid` text, not the server's reason. A user whose address is taken is told it is "invalid".
- `rejectedEmails: Em.A([])` sits on the prototype, so all controller instances share it. This is harmless while the controller is a singleton.

**5. Minor: changing to a blocked email fails silently.** `app/controllers/users_controller.rb:265-286`
- `change_email` never checks the blocklist. It sends a confirmation email to the blocked address.
- On confirmation, `EmailToken.confirm` hits `RecordInvalid`, rescues it and returns nil, so the user sees a generic token failure with no reason.

**6. Minor: invite redemption to a blocked email raises an unhandled exception.** `app/models/user.rb:102`
- `create_for_email` calls `save!`, which raises an uncaught `RecordInvalid` for a blocked address.
- The domain blacklist already behaved this way; this change adds a second way to hit it.

### Gaps in the patch's own tests
- `spec/components/validators/email_validator_spec.rb` stubs `should_block?`, so it tests neither case handling nor how the counter behaves inside transactions.
- `spec/models/blocked_email_spec.rb` uses only lowercase emails.
- No controller spec covers the new `errors`/`values` keys in the JSON response.

No security issue in the new response fields: `values` returns only the name, username and email the user just submitted.

### Coverage
- **Total 10 files, reviewed 10.** OCR's own figures: 8 reviewable, 8 reviewed, 0 skipped, coverage 100%.
- **Reviewed:**
  - `create_account_controller.js`
  - `users_controller.rb`
  - `blocked_email.rb`
  - `user.rb`
  - `server.en.yml`
  - `db/migrate/20130724201552_create_blocked_emails.rb`
  - `lib/validators/email_validator.rb`
  - `spec/fabricators/blocked_email_fabricator.rb`
- **Excluded by OCR but read anyway** (for the test gaps above):
  - `spec/components/validators/email_validator_spec.rb` (rule `default_path`)
  - `spec/models/blocked_email_spec.rb` (rule `default_path`)
- Nothing went unreviewed.

I did not run any specs, and I did not open the Rails 3.2.12 gem source. The rollback point in finding 2 relies on how Rails 3.2 `save` handles transactions.
