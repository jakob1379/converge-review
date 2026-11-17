Correctness review of change.patch (56abd247e1..6669a2d94d, "FEATURE: per-topic unsubscribe option in emails"). No spec was given, so I judged the change by its own wording: the email says "stop receiving notifications about this particular topic". I invoked superpowers:requesting-code-review. That skill normally hands the review to a reviewer subagent, but you told me not to spawn agents, so I applied its reviewer template myself. I ran no tests, as instructed. The failing tests below are reasoned and have not been run.

**Findings**

1. **app/controllers/topics_controller.rb:500 (`render :show` in `perform_show_response`), together with line 87 — Important**
   - **Claim:** Every server-rendered topic page now loses its `<link rel="canonical">` tag. This is an SEO regression on `topics#show`, not only on the new endpoint.
   - **Evidence:**
     - `show` calls `perform_show_response` at line 85 and only then sets `canonical_url` at line 87.
     - Before this patch, the template was rendered implicitly after the action returned, so `@canonical_url` was already set.
     - Now `render :show` runs inside `perform_show_response`. The layout (`app/views/layouts/application.html.erb:8` and `crawler.html.erb:7`) renders `layouts/_head.html.erb:9`, which calls `canonical_link_tag` while `@canonical_url` is still nil.
     - `lib/canonical_url.rb:14` returns `''` when the URL is nil, so the tag is silently dropped.
   - **Failing test (reasoned):** in a controller spec with `render_views`, run `get :show, slug: topic.slug, topic_id: topic.id` and then `expect(response.body).to include('rel="canonical"')`. This passes on the base commit and fails on the patch. Checking `assigns(:canonical_url)` would not catch it, because the variable is still set after the render.
   - **Fix direction:** move `canonical_url` before `perform_show_response`, or drop the explicit `render :show` and render `:show` only from `unsubscribe`.

2. **app/controllers/topics_controller.rb:105-107 — Important**
   - **Claim:** `TopicUser.find_by(...)` can return nil, and the next line calls `tu.notification_level` on it, giving a 500 (NoMethodError on nil).
   - **Evidence:**
     - The only guard is `ensure_logged_in`.
     - The intended recipient always has a row, because `user_notifications.rb` calls `TopicUser.change(..., last_emailed_post_number:)`, which inserts one.
     - But any logged-in user who opens `/t/:slug/:id/unsubscribe` for a topic they have no `topic_users` row for crashes the endpoint. Realistic cases: a forwarded email, a shared device, or a hand-typed or shared link.
   - **Failing test (reasoned):** `log_in(:coding_horror); get :unsubscribe, slug: topic.slug, topic_id: topic.id` on a fresh topic raises `NoMethodError: undefined method 'notification_level' for nil`.

3. **app/controllers/topics_controller.rb:98-116, routes at config/routes.rb:440-441 — Important**
   - **Claim:** A GET request changes state and is open to CSRF.
   - **Evidence:**
     - `get "t/:slug/:topic_id/unsubscribe"` writes `notification_level` via `tu.save!`.
     - Rails CSRF protection does not cover GET, and `skip_before_filter :check_xhr` lets plain navigations through.
     - Any third-party page can embed `<img src="https://forum/t/x/<id>/unsubscribe">` and change a logged-in victim's notification level for any topic they can see.
   - Reasoned. The impact per hit is low, but it is a real security gap in the endpoint.

4. **app/controllers/topics_controller.rb:107-111 and config/locales/client.en.yml:985 — Important**
   - **Claim:** What the endpoint does does not match what the email and page promise, and repeated visits keep changing the result.
   - **Evidence:**
     - Watching or Tracking drops only to Regular. Regular still sends reply, mention and quote notifications, yet the page says "You will stop receiving notifications for <title>".
     - The action toggles a level downward rather than setting one, so it is not idempotent. Reloading the page or following the link a second time moves Regular to Muted. Two clicks on a "watching" email therefore mute the topic, which the user never chose.
     - It also bypasses `TopicUser.change`, so it does not set `notifications_reason_id = user_changed` or `notifications_changed_at`, and it does not publish the `notification_level_change` MessageBus event that `topic_user.rb:113` emits. The UI in the user's other open tabs goes stale, and the old "reason" text stays attached.
   - Reasoned.

5. **No tests for the new endpoint — Important**
   - **Claim:** The new behaviour is untested.
   - **Evidence:** The patch adds a controller action, two routes, `Topic#unsubscribe_url` and a new mailer argument. The only spec change (spec/components/email/message_builder_spec.rb:171-172) adds `unsubscribe_url` so the existing spec keeps passing. Nothing tests:
     - what the action does to notification levels
     - the redirect when the slug is missing or wrong
     - the login requirement
     - the missing-`TopicUser` path
     - that the email body contains the topic link

   Findings 1, 2 and 4 would all have been caught by a single spec in spec/controllers/topics_controller_spec.rb.

6. **config/locales/server.en.yml:1852-1855 together with lib/email/message_builder.rb:67 and :90 — Minor**
   - **Claim:** `unsubscribe_link` now requires `%{unsubscribe_url}`. Any `MessageBuilder` caller that passes `add_unsubscribe_link: true` without `unsubscribe_url` raises `I18n::MissingInterpolationArgument` in both the text and HTML parts.
   - **Evidence:** In core, only `user_notifications.rb:294-295` sets the flag, and it passes the URL, so core is safe. Plugins or future callers using this flag will break. The 28 other `server.*.yml` locales keep the old string, so non-English users never see the per-topic link.

7. **app/assets/javascripts/discourse/routes/topic-unsubscribe.js.es6:4-10 and templates/topic/unsubscribe.hbs:3 — Minor**
   - **Claim:** The page shows the "You will stop receiving notifications" message whether or not the server changed anything.
   - **Evidence:**
     - The Ember route only loads topic JSON. The change happens solely in the server-side HTML GET.
     - A client-side transition to this route therefore changes nothing but still shows the confirmation.
     - Combined with finding 4, the message is wrong on the Watching→Regular path either way.

8. **app/controllers/topics_controller.rb:102 — Minor**
   - **Claim:** `status: 301` on a URL that has side effects is a permanent, cacheable redirect.
   - **Evidence:** If the topic slug later changes, browsers jump through the cached redirect to the stale slug first. `slugs_do_not_match` then redirects again, adding an extra hop each time. A 302 is the safer default here.

**Checked and found correct:**
- The template `topic/unsubscribe` does resolve from route `topicUnsubscribe` (resolver.js.es6:157-158 maps `topic_unsubscribe` to `topic/unsubscribe`).
- `PostStream.loadTopicView` exists as a class method and uses PreloadStore, so it matches the server preload.
- Removing the `post_number` constraints on the summary routes is harmless: those routes had no such segment.
- The `topic-from-params` refactor keeps `self` in scope.
- The `dropdown-button` nil-title guard is fine.
- `Topic#url` is absolute (`Discourse.base_url`), so the link in the email is valid.

**Unreviewed files in the patch:** none. Every file in the patch was read. These were checked only for behaviour change, since they are formatting or style edits:
- app/models/topic_user.rb (formatting only; no logic change)
- app/views/email/notification.html.erb (whitespace and hash syntax only; the placeholders are unchanged)
- app/assets/stylesheets/common/base/topic.scss (CSS only; correctness not applicable)
- app/assets/javascripts/discourse/views/topic-unsubscribe.js.es6 (adds a class name only)

Not checked: I ran no specs, so none of the failing tests above were executed. The biggest live risk is finding 1. It hits every topic page in production, not just the new feature, and nothing in the existing suite catches it.
