I ran `open-code-review:delegate-review` in range mode (56abd247e1..6669a2d94d) and read the whole patch plus the code around it. OCR listed 18 files and marked 7 of them unreviewable: six `.js.es6` files for their file type and one spec for its path. I reviewed those 7 anyway from the patch. The skill also tries to apply fixes automatically; I skipped that because the brief says report only. No files were written and no tests were run, so every claim below is reasoned from the code. There is no spec, so there are no spec gaps to report.

## Findings

1. **app/controllers/topics_controller.rb:105-107 — Important**
   - **Claim:** `unsubscribe` crashes with a 500 (`NoMethodError` on nil) for any user who has no `topic_users` row for the topic. That is a common case for the people this email goes to.
   - **Evidence:**
     - The code is `tu = TopicUser.find_by(user_id: current_user.id, topic_id: params[:topic_id])`, followed by `tu.notification_level` with no nil check.
     - The notification email, and now the unsubscribe link, is sent for `user_mentioned`, `user_linked` and `user_invited_to_private_message` (app/mailers/user_notifications.rb:108-143). `PostAlerter` sends those without creating a `TopicUser` row.
     - `PostAlerter` itself expects the row can be missing: it calls `TopicUser.get(post.topic, user).try(:notification_level)` (app/services/post_alerter.rb:22,105).
     - Example: a user @mentioned in a topic they never opened clicks "click here" and gets a 500.
   - **Failing test (controller spec):**
     ```ruby
     it "unsubscribes a user with no TopicUser row" do
       log_in
       topic = Fabricate(:topic)
       get :unsubscribe, slug: topic.slug, topic_id: topic.id
       expect(response).to be_success
     end
     ```
     This raises `NoMethodError: undefined method 'notification_level' for nil`.
   - **Fix direction:** use `TopicUser.change(current_user, topic, notification_level: ...)`. It creates the row when it is missing.

2. **app/controllers/topics_controller.rb:113 — Important**
   - **Claim:** `tu.save!` goes around `TopicUser.change`, so the side effects every other notification-level change gets are lost:
     - No `MessageBus.publish("/topic/#{id}", notification_level_change: ...)`, so open tabs and the notifications button stay stale.
     - `notifications_reason_id` is not set to `:user_changed`, so the old "you are watching because you created/posted…" reason stays on the row.
     - `notifications_changed_at` is not stamped.
   - **Evidence:**
     - `TopicUser.change` (app/models/topic_user.rb:77-115) sets `notifications_changed_at` and `notifications_reason_id ||= :user_changed` and publishes to MessageBus.
     - The existing `set_notifications` action (topics_controller.rb:330-334) uses `TopicUser.change`.
     - The new client route has to null out `details.notificationReasonText` (routes/topic-unsubscribe.js.es6:14), which papers over the stale reason on this one page only.

3. **app/controllers/topics_controller.rb:98-115 together with config/routes.rb:440-441 — Important**
   - **Claim:** a plain GET changes state, there is no CSRF or signed token, and every visit lowers the level one more step instead of being idempotent.
   - **Evidence:**
     - The level goes watching/tracking → regular, then regular → muted.
     - A second click, a page reload, or browser history replay therefore mutes a topic the user only meant to stop watching.
     - Because it is a plain GET with `check_xhr` skipped (line 32), any third-party page can do the same to a logged-in visitor with `<img src="https://forum/t/x/123/unsubscribe">`. Two loads mute any topic the victim can see, including PMs.
   - **Fix direction:** set a fixed target level so repeat visits are idempotent. Ideally mutate on POST, or use a signed per-user token, with the GET only showing a confirmation page.

4. **app/controllers/topics_controller.rb:28 (`:unsubscribe` added to `ensure_logged_in`) — Important**
   - **Claim:** a logged-out recipient who clicks the email link is silently bounced to `/`. Nothing is unsubscribed and they are not sent back afterwards.
   - **Evidence:**
     - `rescue_from Discourse::NotLoggedIn` (application_controller.rb:97-104) runs `redirect_to path("/")` for a non-JSON GET, without saving a destination.
     - Email links are usually opened in a browser session that may not be logged in, and the link carries no token.
     - This one is reasoned only.

5. **app/assets/javascripts/discourse/controllers/topic-unsubscribe.js.es6:5-7 and config/locales/client.en.yml:985 — Minor**
   - **Claim:** the page always says "You will stop receiving notifications for <title>". The server only drops watching/tracking to regular on the first visit. At regular the user still gets notified, and emailed, for replies, mentions and quotes, so the message is false.
   - **Second case:** if the user reaches `/t/:slug/:id/unsubscribe` by navigating inside the app, the Ember route only calls `PostStream.loadTopicView` (the `/t/:id.json` endpoint). No server change happens, yet the same message is shown.

6. **app/controllers/topics_controller.rb:98-115 — Minor**
   - **Claim:** the new state-changing controller action has no tests. The only spec change in the patch (spec/components/email/message_builder_spec.rb:171-172) just passes the new `unsubscribe_url` argument so the existing spec keeps passing.
   - **Evidence:** the patch adds nothing under spec/controllers for `topics#unsubscribe`.

Checked and not reported:
- **Triple-stache in `unsubscribe.hbs`:** `fancyTitle` is already HTML-escaped on the server (topic.rb:263-264), so it is not an XSS.
- **Missing `%{unsubscribe_url}` breaking other mailers:** it cannot. `send_notification_email` is the only caller that passes `add_unsubscribe_link: true`, and it now passes `unsubscribe_url`.
- **Route shadowing:** none. The `t/:slug/:topic_id/...` constraints keep `unsubscribe` from matching the show routes.
- **Other locale files:** they still have the old `unsubscribe_link` text. That is a translation gap, not a crash.

## Unreviewed files
None. All 18 files in the patch were reviewed. These were reviewed even though OCR excluded them:
- The six `.js.es6` files, excluded as `unsupported_ext`.
- `spec/components/email/message_builder_spec.rb`, excluded as `default_path`.

Not done: no tests were run, so every claim is reasoned, including the spec in finding 1. The worst risk is findings 1 and 3: the unsubscribe link returns a 500 for @mentioned users, and the GET endpoint can be triggered by other sites to mute topics.
