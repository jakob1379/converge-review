I reviewed the patch with `mattpocock-skills:code-review`, covering both axes myself without sub-agents. I found 12 issues: 4 on the Spec axis and 8 on the Standards axis.

**Assumptions**
- There is no spec. I used the PR title "FEATURE: per-topic unsubscribe option in emails" as the implicit spec: an email link that stops notifications for that one topic.
- The only documented standard in the repo is `CONTRIBUTING.md`, sections "Code" and "Coding Conventions". There is no CODING_STANDARDS file and nothing in docs/.
- Range is 56abd247e1..6669a2d94d; the diff is not empty.
- I ran nothing. Every finding is reasoned from the code. The failing tests below are proposals and were not executed.

## Spec (implicit: per-topic unsubscribe from emails)

1. **app/controllers/topics_controller.rb:105-107 — Important.**
   - **Claim:** `unsubscribe` crashes with a 500 when the logged-in user has no `TopicUser` row for the topic.
   - **Evidence:** `tu = TopicUser.find_by(...)` can return nil, and the next line calls `tu.notification_level` without a nil check. This happens when a mention or quote email goes to someone who never opened the topic, or when someone else opens a forwarded email.
   - **Proposed failing test** (spec/controllers/topics_controller_spec.rb):
     ```ruby
     describe 'unsubscribe' do
       it 'works without a TopicUser row' do
         log_in(:coding_horror)
         topic = Fabricate(:topic)
         get :unsubscribe, topic_id: topic.id, slug: topic.slug
         expect(response).to be_success
       end
     end
     ```
     Expected failure: `NoMethodError: undefined method 'notification_level' for nil:NilClass`.

2. **app/controllers/topics_controller.rb:107-111 and config/locales/client.en.yml:985 — Important.**
   - **Claim:** the action is a toggle, not an unsubscribe, and running it again changes state again.
   - **Evidence:** a level above regular (tracking or watching) drops to regular; any other level, including regular, goes to muted. So a watching user who clicks the link goes to regular on the first click and to muted on a reload or second click.
   - **Copy mismatch:** after the first click the page says "You will stop receiving notifications for {{title}}", but a user at regular still gets notified for replies and mentions. The copy does not match the state that was set.

3. **config/routes.rb:440-441 with the `unsubscribe` action — Important.**
   - **Claim:** the change of notification state happens on a GET with no token.
   - **Evidence:** the routes are plain `get`, and the action calls `tu.save!`.
     - Because it is a GET, Rails' CSRF protection is skipped. Any page can hit the URL (for example with an image tag), and if the visitor is logged in, their notification level for that topic changes.
     - The email link carries no per-user token, unlike the digest's `email/unsubscribe/:key` route at routes.rb:202.
   - Reasoned; no test given.

4. **app/controllers/topics_controller.rb:27 and app/controllers/application_controller.rb:97-104 — Minor.**
   - **Claim:** a logged-out user who clicks the email link is sent to `/` with no message and no return to the unsubscribe page, so the feature silently does nothing for them.
   - **Evidence:** the action is behind `ensure_logged_in`. For an HTML GET, `NotLoggedIn` is handled by `redirect_to path("/")`.

## Standards (CONTRIBUTING.md plus the smell baseline)

5. **Patch-wide, spec/ — Important.**
   - **Breach:** CONTRIBUTING.md §3, "Include tests, and ensure they pass".
   - **Evidence:**
     - There are no tests for `TopicsController#unsubscribe`, `Topic#unsubscribe_url`, the new email footer text, or the new Ember route.
     - The only spec change (spec/components/email/message_builder_spec.rb:171-172) adds `unsubscribe_url:` to keep an existing test from breaking and asserts nothing about it.

6. **app/models/topic_user.rb (8-12, 62-64, 113, 125, 194, 218), app/assets/javascripts/discourse/routes/topic-from-params.js.es6 (whole hunk), app/views/email/notification.html.erb, app/mailers/user_notifications.rb:310, lib/email/message_builder.rb:24-38 — Minor.**
   - **Breach:** CONTRIBUTING.md §2, "one feature or bug-fix per branch", and the note under §4 that style changes are welcome only "in the context of pull requests that also refactor code, fix bugs, improve functionality".
   - **Evidence:**
     - topic_user.rb and topic-from-params.js.es6 have no functional change at all; they are pure reformatting inside a feature PR.
     - The other three files mix reformatting into small functional edits, which makes those edits harder to spot.

7. **app/models/topic_user.rb:10-12 — Minor.**
   - **Breach:** CONTRIBUTING.md §3, "Adhere to common conventions you see in the existing code".
   - **Evidence:** the rewritten `tracking` scope moves the chained `.where` to a 3-space indent, below the scope body, and the arguments to an arbitrary 5-space indent. The rest of the file uses 2-space nesting. The new layout is worse than the original.

8. **config/routes.rb:439 and 442 — Minor.**
   - **Claim:** an unrelated behaviour change is hidden inside a route reorder.
   - **Evidence:** the `post_number: /\d+/` constraint was dropped from both `summary` routes, and `moderator-liked` was moved. None of this relates to unsubscribe, and the commit message does not mention it. This is the same §2 "one feature per branch" breach as finding 6.

9. **config/routes.rb:440-441 — Minor.**
   - **Breach:** CONTRIBUTING.md §4, "use spaces … around `{` and before `}`".
   - **Evidence:** `constraints: {topic_id: /\d+/}` has no inner spaces. The neighbouring lines do the same, so this follows local precedent but breaks the written rule.

10. **app/assets/javascripts/discourse/controllers/topic-unsubscribe.js.es6:5 and app/assets/javascripts/discourse/templates/topic/unsubscribe.hbs:3 — Minor.**
    - **Claim:** possible Mysterious Name. `stopNotificiationsText` is misspelled ("Notificiations"), and the typo is now spread across the controller and template.

11. **app/assets/javascripts/discourse/controllers/topic-unsubscribe.js.es6:9 — Minor.**
    - **Breach:** §3, existing conventions.
    - **Evidence:** the module ends with `})` and no semicolon, unlike every sibling `.js.es6` controller.

12. **config/locales/server.en.yml:1852-1855 and lib/email/message_builder.rb:67, 90 — Minor.**
    - **Claim:** hidden coupling (judgement call).
    - **Evidence:** the shared `unsubscribe_link` string now needs `%{unsubscribe_url}`. So `MessageBuilder`'s public option `add_unsubscribe_link: true` quietly requires a new `unsubscribe_url:` option, or it hits I18n's missing-interpolation handling. The existing spec had to be patched (message_builder_spec.rb:172), which shows the contract changed.
    - **Also:** the `List-Unsubscribe` header (message_builder.rb:107) still points at user preferences, not the per-topic URL.

**Summary:** Spec has 4 findings; the worst is the nil-`TopicUser` 500 (finding 1). Standards has 8; the worst is that the new endpoint and model method have no tests, breaching CONTRIBUTING.md "Include tests" (finding 5).

## Unreviewed files
I reviewed all 18 files in the patch.
- **Lightly reviewed:** app/assets/stylesheets/common/base/topic.scss (12 lines of CSS, nothing to flag) and app/assets/javascripts/discourse/views/topic-unsubscribe.js.es6 (3-line view, nothing to flag).
- **Not checked:** I did not run any tests or render the Ember/Handlebars template.
- **Not compared:** I did not check other-language locale files for the changed `unsubscribe_link` key, because they are outside the patch.
