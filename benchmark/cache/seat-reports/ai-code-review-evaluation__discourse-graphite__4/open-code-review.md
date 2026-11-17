OCR delegate-review, range mode 62db063e1e..4f8aed295a. I only reported and fixed nothing, because the caller said report-only and that overrides the skill's auto-fix step. There is no Ruby toolchain in this environment (`ruby: command not found`), so I could not run any test. Every finding below comes from reading the code; each one names a test that would fail.

## Findings

**1. app/models/topic_embed.rb:13 (with :22, :61-75, app/models/post.rb:133) — Critical. An anonymous visitor can plant stored XSS on the forum.**
- **Claim:** The "Imported from" footer puts `url` into `<a href='#{url}'>` without escaping. The post is created with `cook_method: raw_html`, so `Post#cook` returns `raw` and the sanitizer never runs.
- **How it is reached:**
  - The URL comes straight from the unauthenticated `embed_url` param. Path: `EmbedController#best` → `Jobs::RetrieveTopic` → `TopicRetriever` → `import_remote` → `import`.
  - The only checks are that the URL's host equals `embeddable_host` (topic_retriever.rb:15) and that the Referer host matches. The Referer is trivially forged by a non-browser client.
  - Ruby's URI parser (RFC2396) accepts `'` in the path and query. Example: `http://<embeddable_host>/?a='onmouseover='alert(document.cookie)`.
  - The host serves 200 for unknown query params (most blogs do), so the fetch succeeds.
  - `absolutize_urls` then runs Nokogiri over the string and writes `onmouseover` out as a real attribute.
  - The OP's cooked HTML is rendered unescaped in the normal Discourse topic view.
- **Test that should fail:** in spec/models/topic_embed_spec.rb, `TopicEmbed.import(user, "http://eviltrout.com/?a='onmouseover='alert(1)", title, "x")` followed by `post.cooked.should_not =~ /onmouseover/`.

**2. app/models/post.rb:133 with app/models/topic_embed.rb:48-50 and app/jobs/scheduled/poll_feed.rb:35 — Important. Raw-HTML posts skip sanitization for any remote content.**
- **Claim:** Feed content (`CGI.unescapeHTML`, no filtering at all) and Readability output (which keeps `href`/`src` with any scheme, e.g. `javascript:`) are stored as cooked HTML exactly as received.
- **Who can inject script into the Discourse origin:**
  - Anything that controls the feed: a user-contributed feed, or MITM on an `http://` feed URL.
  - The `embed_by_username` account. Editing a raw_html post re-cooks it through the same bypass, so if an admin picks a non-staff account, that user can inject arbitrary HTML.
- **Evidence:** `return raw if cook_method == Post.cook_methods[:raw_html]`.
- **Test that should fail:** import contents `"<script>alert(1)</script>"`, then assert the cooked HTML has no `<script>`. Reasoned, not run.

**3. app/jobs/scheduled/poll_feed.rb:29 — Important. An admin can run shell commands on the server.**
- **Claim:** `open(SiteSetting.feed_polling_url)` uses `Kernel#open`. With open-uri loaded, a value that is not a URL falls through to the original `open`, which runs `|cmd` as a shell pipe.
- **Effect:** any admin can set `feed_polling_url = "|touch /tmp/pwned"` and get code execution on the hourly job. It also runs immediately through `TopicRetriever#perform_retrieve`. Admin is not supposed to mean shell access.
- **Fix direction:** use `URI.parse(url).open` / `open-uri` explicitly.
- **Test that should fail:** stub the settings with `feed_polling_url = "|touch #{tmp}"`, run `poller.execute({})`, and assert the file does not exist.

**4. app/jobs/scheduled/poll_feed.rb:35 — Important. Feed polling crashes on Ruby 2.0, and on RSS 2.0 feeds.**
- **Ruby version:** `String#scrub` only exists from Ruby 2.1. `.travis.yml` pins `rvm: 2.0.0` and no scrub polyfill is in the Gemfile or Gemfile.lock, so you get `NoMethodError` on the first item.
- **RSS 2.0 feeds:** SimpleRSS exposes `<content:encoded>` as `content_encoded` and `<description>` as `description`. Typical RSS 2.0 items have no `<content>`, so `i.content` is nil and `nil.scrub` raises.
- **Fallback field:** line 33 falls back to `i.id`, which is Atom-only; RSS uses `guid`.
- **No error isolation:** with `retry: false` and no per-item rescue, one bad item stops the whole feed.
- **Why CI misses it:** the specs never exercise `poll_feed`.
- **Test that should fail:** on Ruby 2.0, `ruby -e '"x".scrub'` raises NoMethodError. Also: feed `SimpleRSS.parse` an RSS 2.0 document with only `<description>` items into `poll_feed`.

**5. app/controllers/embed_controller.rb:15 with lib/topic_retriever.rb:9-33 — Important. Anonymous requests can force unlimited fetches and topic creation.**
- **Claim:** Every anonymous request for an unknown `embed_url` enqueues a job. The throttle is keyed per URL, so changing a query param gets around it.
- **What each new URL costs:**
  - an outbound fetch of the page;
  - a full `PollFeed` run when polling is enabled (topic_retriever.rb:41), so the whole feed is re-fetched per request;
  - a new topic, owned by `embed_by_username`, for every 200 response on the host.
- The Referer check is the only gate, and it is forgeable. In practice this is spam-topic creation plus a work-amplification DoS.
- **Test that should fail:** call `get :best` twice with Referer=host and embed_urls `.../a?x=1` and `.../a?x=2` (`queue_jobs` is false in test). `TopicRetriever#perform_retrieve` runs both times, and `TopicEmbed.count` would be 2 if the fetch is stubbed.

**6. lib/tasks/disqus.thor:117, 143-148 — Important. The Disqus import loses the `--category` option and original timestamps, and is now fragile.**
- **Lost behaviour:** the patch silently drops the `--category` option and the `created_at: Date.parse(t[:created_at])` preservation. Imported threads are uncategorised and dated "now".
- **New network dependency:** each thread now makes a live HTTP request (`import_remote`).
- **Aborts on failure:** any 404 or network error raises `OpenURI::HTTPError` and ends the whole import, since there is no rescue.
- **Missing `require 'open-uri'`:** neither the thor task nor topic_embed.rb requires it. In a non-eager-loaded env, `open("http://...")` falls back to a file open and gives `Errno::ENOENT`. The only require is in poll_feed.rb, which may not be loaded.
- Reasoned.

**7. app/models/topic_embed.rb:62-72 — Minor. Protocol-relative URLs get rewritten wrongly.**
`//cdn.example.com/x.png` starts with `/`, so it becomes `http://host/cdn.example.com/x.png`, which breaks images and links. The check should be `start_with?('/') && !start_with?('//')`.

**8. app/models/topic_embed.rb:34-38 / :82 — Minor. A deleted topic or post permanently breaks the embed for its URL.**
Nothing cleans up `topic_embeds`; Topic has no association to it.
- A trashed topic makes `TopicView` raise NotFound, so the iframe 404s forever and the topic is never re-created.
- A hard-deleted post makes `embed.post` nil, so `PostRevisor.new(nil).revise!` raises NoMethodError.

**9. lib/topic_retriever.rb:27-28 — Minor. The throttle key can end up permanent.**
`setnx` then `expire` is not atomic. If the process dies between the two calls, the key never expires and that URL is throttled forever. Use `SET key 1 NX EX 60`.

**10. app/assets/javascripts/embed.js:17 — Minor. The postMessage origin check is a substring match.**
`discourseUrl.indexOf(e.origin)` accepts any origin that is a prefix of the Discourse URL. For example, `http://forum.example.co` is accepted for `http://forum.example.com/`. Today the only impact is resizing the iframe. Compare against the exact origin instead.

**11. app/views/embed/best.html.erb:6 — Minor. Typo `<%- end if %>`.**
It only works by accident: the whole if/else becomes conditional on the next `@output_buffer.safe_append=` expression, which is always truthy. It should be `<%- end %>`.

**12. db/migrate/20131223171005_create_top_topics.rb:3 and db/migrate/20131217174004_create_topic_embeds.rb:3 — Minor. `force: true` in migrations, one of them already shipped.**
- The patch edits a migration that has already shipped. That is a no-op for databases that already ran it, but `force: true` silently drops an existing table if anyone re-runs it.
- db/migrate/20131210181901_migrate_word_counts.rb gets a whitespace-only edit, which is unrelated churn.

**13. spec/jobs/poll_feed_spec.rb:18, :24 — Minor. Two specs pass for the wrong reason.**
"requires feed_polling_url" and "requires embed_by_username" pass vacuously, because `feed_polling_enabled` defaults to false. Neither actually tests the guard it names. No spec covers `poll_feed`, `import_remote` or `absolutize_urls` edge cases.

## Files not reviewed or only partly reviewed
- **Gemfile_rails4.lock:** OCR excluded it (unsupported_ext). I only skimmed it to check the new gems against the Gemfile.
- **app/assets/stylesheets/embed.css.scss, config/locales/client.en.yml, config/locales/server.en.yml, config/routes.rb, config/site_settings.yml:** read only; style and config with no logic, and no findings.
- **lib/tasks/disqus.thor and the four new spec files** (topic_retriever, embed_controller, poll_feed, topic_embed): OCR excluded them (unsupported_ext / default_path). I still read them for context, and they are the source of findings 6 and 13.

Coverage: OCR listed 22 reviewable files out of 28, and I reviewed all 22.

I did not check Erubis line-trim behaviour or the SimpleRSS field mapping against their sources; both come from memory of those gems. Findings 1 and 4 are the ones to verify first, by running the named tests on a Ruby 2.0 environment.
