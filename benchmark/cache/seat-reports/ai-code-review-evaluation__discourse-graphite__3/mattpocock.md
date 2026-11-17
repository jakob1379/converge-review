Code review of 5f8a130277 against base e25638dab0. Skill: mattpocock-skills:code-review. Advisory seat: spec compliance and documented standards.

**How this was run:** the skill normally starts two parallel sub-agents, one for Standards and one for Spec. Your brief forbids spawning agents, so I ran both reviews myself and kept the results separate. There is no spec, so the commit message is the spec. The standards source is `<bench>/work/ai-code-review-evaluation__discourse-graphite__3/CONTRIBUTING.md` plus the skill's code-smell checklist. No other coding-standards doc exists in the repo. I ran no tests, so every claim below is reasoned from the code.

## Spec

**S1. Important. `app/models/blocked_email.rb:12` (with `app/models/user.rb:87`).** Commit message: "block signups based on email". Changing the case of the email gets around the block.
- Signup sets `user.email = params[:email]` with no case normalisation.
- `should_block?` then does an exact `BlockedEmail.where(email: email)`, and that comparison is case-sensitive in Postgres.
- The repo already has a helper for this, `Email.downcase` in `lib/email.rb`, which only lowercases the domain part. Neither the stored value nor the lookup uses it.
- Result: if `bad@spammers.org` is blocked, `bad@SPAMMERS.org` (or `BAD@spammers.org`) passes the check.
- Failing test (add to `spec/models/blocked_email_spec.rb`): `Fabricate(:blocked_email, email: 'bad@spammers.org'); BlockedEmail.should_block?('bad@SPAMMERS.org').should be_true`. It returns false.

**S2. Important. `lib/validators/email_validator.rb:13`, `app/models/blocked_email.rb:13-17`, `app/controllers/users_controller.rb:168,172`.** Commit message: "Track stats of how many times each email address is blocked". The counts are wrong.
- `should_block?` runs inside validation and writes the counter there (`match_count += 1; save`).
- `users#create` calls `user.valid?` (line 168, which runs on every signup regardless of the hub setting), then `user.save` (line 172), so validation runs twice per attempt.
- In Rails 3.2.12, `save` runs validation inside a transaction that is rolled back when validation fails.
- **Blocked email:** the increment from `valid?` sticks and the one from `save` is rolled back, so the count of 1 depends on the stray `valid?` call. Remove that call and blocked signups stop being counted.
- **`do_nothing` email:** both increments commit, so each signup adds 2.
- **Other paths:** blocks hit through `User.create_for_email` (`save!`) or `EmailToken.confirm` (inside `User.transaction`) are rolled back and never counted.
- Suggested failing test: a controller spec that POSTs `users#create` with a `do_nothing` BlockedEmail and expects `match_count == 1`. It gets 2. Blocked counts going missing in production can't be shown under the suite's `use_transactional_fixtures`, which changes the rollback behaviour, so that part is reasoned.

**S3. Minor (scope). `app/models/user.rb:47`.** The block applies to any User save where the email changed, not just signups.
- Invite redemption (`create_for_email`) raises.
- `EmailToken.confirm` swallows the `RecordInvalid` and returns nil, so changing your email to a blocked address fails with no message.
- This may be intended, but it goes beyond "block signups", and none of it is tested.

**S4. Minor. `app/assets/javascripts/discourse/controllers/create_account_controller.js:69-72,275`.** The client remembers an address after any server-side email error, including "has already been taken" and the domain whitelist/blacklist. It then always shows the generic `user.email.invalid` text instead of the server's reason. The message is misleading for an address that is already taken. The list also lasts until a page reload, so an address unblocked in the meantime still can't be retried.

**S5. Minor. `app/models/blocked_email.rb:13-14`.** `match_count` and `last_match_at` also go up for `do_nothing` matches. The commit says "how many times each email address is blocked". The specs at `spec/models/blocked_email_spec.rb:42-44` say counting `do_nothing` is deliberate, so the commit message and the code disagree on what is counted.

## Standards

**T1. Minor. CONTRIBUTING.md §3, "Include tests".** Three parts of the change have no test:
- the new `errors` / `values` keys in the `users#create` failure JSON (`users_controller.rb:198-199`);
- the client-side `rejectedEmails` behaviour, with nothing under `test/javascripts/`;
- the end-to-end path, from a blocked email to a failed signup to updated stats.

The EmailValidator spec stubs `BlockedEmail.should_block?`, so nothing tests the combined behaviour where S2 lives.

**T2. Minor. `lib/validators/email_validator.rb:24`.** The file has no newline at the end (the patch shows `\ No newline at end of file`). CONTRIBUTING §4's whitespace rule doesn't strictly cover this, but every other file in the repo ends with one.

**T3. Suppressed. `blocked_email.rb:7,11`.** The code uses `def self.` where CONTRIBUTING §4 says to prefer `class << self`. I'm not counting it: `def self.` is the overwhelming convention in `app/models`, and §3 says "Adhere to common conventions you see in the existing code".

**T4. Judgement call (smell: misleading name). `BlockedEmail.should_block?`.** A method named like a question writes to the database (counter and timestamp). The name hides the side effect, and that hidden write is what causes S2. Splitting it into a query and a separate counter update would fix both.

## Summary
- Spec: 5 findings. The worst is S1/S2: changing the email's case gets past the block, and the block stats are both double-counted and rolled back, depending on the path.
- Standards: 2 findings (T1, T2), 1 suppressed (T3), 1 smell (T4). The worst is T1: the client change, the controller's new response keys and the full block flow have no tests.

**Files not reviewed:** none. I read all 10 files in the patch, plus `users_controller#create`, `User.new_from_params` / `create_for_email`, `EmailToken.confirm` and `lib/email.rb` for context.

I didn't run anything, and S2 depends on how Rails 3.2.12 wraps validation in a transaction during `save`.
