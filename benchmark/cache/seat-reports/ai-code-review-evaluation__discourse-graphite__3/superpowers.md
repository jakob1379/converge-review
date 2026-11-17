Code review of 5f8a130277 against base e25638dab0, done with `superpowers:requesting-code-review`.

The skill normally hands the review to a subagent. You said not to spawn agents, so I applied its reviewer template myself. I ran no tests and wrote nothing to the repo. Rails 3.2.12 gems are not installed here, so every Rails-internals claim below is reasoned, not executed.

**Verdict:** Not ready to merge. Blocking works for exact-case matches. But the stats this commit says it tracks are wrong on most code paths, and blocking can be bypassed by changing letter case.

## Important

**1. `lib/validators/email_validator.rb:13` and `app/models/blocked_email.rb:11-18`: blocked attempts are mostly never counted (spec gap: "Track stats of how many times each email address is blocked")**
- `should_block?` writes `match_count` and `last_match_at` from inside a validator.
- In Rails 3.2, `save`/`save!` run validations inside `with_transaction_returning_status`. When validation fails, that raises `ActiveRecord::Rollback`, which undoes the BlockedEmail update made in the same transaction.
- A `:block` match is exactly the case where validation fails, so the stats write is rolled back.
- `UsersController#create` survives only by accident. It calls `user.valid?` outside a transaction (`users_controller.rb:166`) before `user.save`, so one increment sticks.
- Two other paths lose the stats completely:
  - `User.create_for_email` (`user.rb:102`, `save!`).
  - `EmailToken.confirm` (`email_token.rb:46-53`). This is `User.transaction` plus `save!`, rescued as `RecordInvalid`. It also shows the user a silent nil failure.
- The model spec calls `should_block?` directly, outside any save, so it cannot catch this.
- Reasoned. A test that should fail on this patch:
  ```ruby
  be = Fabricate(:blocked_email, email: 'x@y.com')
  User.create_for_email('x@y.com') rescue nil
  be.reload.match_count.should == 1   # expected 0 on patched code
  ```

**2. Same lines: `:do_nothing` matches are counted twice per signup**
- `create` runs validations twice: `valid?` at line 166, then `save`.
- Both increments persist when validation passes.
- Any other `valid?` call on a user whose email changed also bumps the counter.
- Side effects in a validator make the counts meaningless. The write belongs at the signup call site, outside the save transaction.
- Reasoned. Test: POST `/users` with an email that has a `:do_nothing` record, then expect `match_count == 1` (the patch gives 2).

**3. `app/models/blocked_email.rb:12`: blocking can be bypassed by changing case**
- `where(email: email)` is an exact, case-sensitive match in Postgres.
- `User.new_from_params` (`user.rb:87`) stores `params[:email]` raw, with no `Email.downcase` and no strip.
- So if `spam@x.com` is blocked, `Spam@x.com` or `spam@X.COM` gets through.
- The domain blacklist in the same validator is case-insensitive (it builds the regexp with the ignore-case flag), so the two checks behave inconsistently.
- Reasoned. Test:
  ```ruby
  Fabricate(:blocked_email, email: 'spam@x.com')
  Fabricate.build(:user, email: 'Spam@X.com').should_not be_valid   # passes validation on patched code
  ```

**4. Tests: the important contracts are untested**
- `email_validator_spec.rb` stubs `BlockedEmail.should_block?`, a class this patch owns. That breaches the user's documented "never mock things you own" rule.
- No integration test covers any of these:
  - `UsersController#create` returning the new `errors`/`values` JSON keys.
  - The stats persisting through a real `User#save`.
  - Case handling.
- An integration test going through `User#save`, or better a POST to `/users`, would have exposed findings 1–3.

## Minor

- **`blocked_email.rb:14-16`: lost updates under concurrency.** `match_count += 1; save` is read-modify-write, so concurrent signups drop counts. Use `BlockedEmail.where(id: record.id).update_all(["match_count = match_count + 1, last_match_at = ?", Time.zone.now])`. This also avoids `save` re-running the uniqueness query.
- **`create_account_controller.js:274-276`: misleading client message.** Any server-side email error, including "has already been taken" and the domain whitelist/blacklist errors, adds the email to `rejectedEmails`. The form then shows the generic "invalid email" text instead of the real reason. Blocking resubmit is still correct; only the message is wrong.
- **`create_account_controller.js:17`: shared array.** `rejectedEmails: Em.A([])` sits on the class prototype, so every instance shares it. That is harmless only because the controller is a singleton.
- **`users_controller.rb:198-199`: leaky JSON.** `errors: user.errors.to_hash` exposes every attribute error as structured JSON, while the client only needs `email`. Low risk, since it echoes the requester's own input.
- **`email_validator.rb`: missing trailing newline** (shows as "No newline at end of file" in the patch).

## Plan alignment

- **Done:** BlockedEmail model and migration; validation moved into `EmailValidator`, with the whitelist/blacklist logic kept intact; the signup form remembers rejected emails.
- **Covered by existing tests:** the moved whitelist/blacklist behaviour, via `spec/models/user_spec.rb:487-530`, which goes through `User`.
- **Broken:** stats tracking (findings 1 and 2).

## Declined to judge

- No admin UI or API for managing BlockedEmail. The commit doesn't claim one.
- Blocking also applies to email changes (`email_changed?`), not only signup. That looks intentional and is consistent with the domain blacklist.
- The `EmailValidator` name could clash with gems. I checked: `Gemfile.lock` has no such gem, and `lib/validators/` is on the autoload path (`config/application.rb:36`).

## Files not reviewed

None. I reviewed all 10 files in the patch. The fabricator and locale changes are trivial and had no findings.

The highest risk is the counter being lost on rollback (finding 1). I did not verify it by running code, only from Rails 3.2 transaction semantics.
