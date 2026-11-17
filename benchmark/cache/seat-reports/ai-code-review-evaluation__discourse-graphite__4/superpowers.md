Review of change.patch (62db063e1e..4f8aed295a), done with the superpowers:requesting-code-review checklist. I reviewed it myself and spawned no subagents. There was no spec, so I judged behaviour by what a reasonable operator of the forum would expect. Ruby is not installed here and I was told not to install anything or run the suite, so every finding below is reasoned from the code, not run. Line numbers refer to the files at head.

## Findings

**1. app/models/topic_embed.rb:13 (also :22 and app/models/post.rb:133). Critical: unauthenticated stored XSS on the forum origin.**
- **Claim:** Imported posts get `cook_method: raw_html`, so `Post#cook` returns `raw` unchanged and skips the PrettyText sanitizer. On top of that, `url` is placed into HTML with no escaping: `"<a href='#{url}'>#{url}</a>"`.
- **How an attacker gets there:**
  - The only gate in `EmbedController#ensure_embeddable` (embed_controller.rb:26) is the Referer header, and a non-browser client sets that freely.
  - `TopicRetriever#invalid_host?` (topic_retriever.rb:15) only compares `URI(@embed_url).host`. A single quote is a legal character in a Ruby URI path or query.
- **Reproduction (reasoned):** `curl -H 'Referer: http://<embeddable_host>/' "https://forum/embed/best?embed_url=http://<embeddable_host>/?'onmouseover='alert(document.cookie)'"`.
  - This enqueues `RetrieveTopic`, which runs `import_remote` and creates a post whose raw contains `<a href='http://host/?'onmouseover='alert(...)'...>`.
  - Nokogiri in `absolutize_urls` normalises that into a real `onmouseover` attribute, and the post is served as cooked HTML in the main forum UI.
- **Second source of the same bug:** the RSS path (poll_feed.rb:35) passes feed HTML through with no sanitising at all. Whoever controls the feed controls script on the forum.
- **It also persists:** `cook_method` stays on the post, so later edits by the owner or staff are rendered raw as well.
- **Fix:** escape `url`, and sanitise raw_html content, for example with a whitelist pass, before storing it.

**2. app/controllers/embed_controller.rb:15 and lib/topic_retriever.rb:26. Important: anyone can create unlimited topics and trigger server-side fetches.**
- **Claim:** Each distinct `embed_url` on the embeddable host (`?a=1`, `?a=2`, and so on) passes the host check and creates a new topic posted as `embed_by_username`.
  - The throttle key is `retrieved:#{@embed_url}`, so changing the URL gets around it.
  - Each request also runs a full `Jobs::PollFeed#execute` synchronously (topic_retriever.rb:40-41) and an outbound HTTP fetch.
- **Evidence:** the controller's only gate is the Referer check (forgeable), and `topic_id_for_embed` matches on the exact URL string.
- **Fix:** canonicalise URLs, apply a global or per-IP rate limit, and only auto-create topics for URLs that are already known from the feed (or behind a setting).

**3. app/jobs/scheduled/poll_feed.rb:29. Important: an admin can run shell commands on the server.**
- **Claim:** `open(SiteSetting.feed_polling_url)` calls `Kernel#open`, which open-uri falls back to for strings that are not URIs. A setting value of `|cmd` starts a subprocess.
- **Why it matters:** Discourse admins are not meant to have a shell on the host.
- **Evidence:** Ruby's documented `Kernel#open` pipe behaviour.
- **Fix:** use `URI.parse(url).open` or `open-uri`'s `URI#read`, and check the scheme is http or https.

**4. app/jobs/scheduled/poll_feed.rb:35. Important: polling crashes on common RSS 2.0 feeds.**
- **Claim:** `i.content.scrub` assumes every item has a `<content>` element. In SimpleRSS:
  - RSS 2.0 items normally have only `description`.
  - `content:encoded` (which WordPress uses) is exposed as `content_encoded`, not `content`.
- **Effect:** `i.content` is nil, so `NoMethodError` aborts the whole run. The job has `retry: false`, and the same failure repeats every hour. Nothing in the patch handles one bad item, so every item after it is lost too.
- **Evidence:** reasoned from SimpleRSS's item tag mapping. `spec/jobs/poll_feed_spec.rb` stubs out `poll_feed` entirely, so this path has no test.

**5. app/models/topic_embed.rb:32-36 and app/controllers/embed_controller.rb:13. Important: deleting an imported topic or post breaks things permanently.**
- **Claim:** `Post` and `Topic` use the Trashable default scope (`app/models/concerns/trashable.rb:5`). `TopicEmbed` rows are never cleaned up.
  - After a moderator deletes the post, `embed.post` is nil, and `PostRevisor.new(nil).revise!` raises `NoMethodError` inside the feed loop on every poll once that item's content changes.
  - After the topic is trashed, `topic_id_for_embed` still returns its id, `TopicView` raises `Discourse::NotFound` (topic_view.rb:300), and that page's comments stay a 404 forever with no way to re-create them.
- **Fix:** handle a nil post (skip or re-create), and filter or remove embeds whose topic is deleted.

**6. db/migrate/20131223171005_create_top_topics.rb:3. Important: an already-shipped migration was edited.**
- **Claim:** The patch adds `force: true` to a migration that exists at base. On databases that already ran it, the edit does nothing. On any fresh or re-run path, `force: true` silently drops an existing `top_topics` table.
- **Related:** `create_topic_embeds` (line 3) also uses `force: true`. Its timestamp (20131217) is older than migrations already merged (20131223), so it runs out of order. That works, but it is fragile.
- **Fix:** revert the edit to the old migration and drop `force: true`.

**7. app/models/topic_embed.rb:64 and :70. Minor: protocol-relative URLs get mangled.**
- **Claim:** `href.start_with?('/')` also matches `//cdn.example.com/x.png`. The code then rewrites it to `http://host/cdn.example.com/x.png`, which breaks images and links on most real feeds.
- **Evidence:** read from the code (the `start_with?('/')` check plus `sub(/^\/+/, '')`).

**8. app/assets/javascripts/embed.js:17. Minor: the origin check is a substring match.**
- **Claim:** `discourseUrl.indexOf(e.origin) === -1` accepts any origin that is a prefix of the forum URL, such as `https://forum.example.co` when the forum is `https://forum.example.com/`. The only impact is that someone can resize the iframe.
- **Fix:** compare against the parsed origin exactly.

**9. app/controllers/embed_controller.rb:19 and :26. Minor: the anonymous cache bypasses the Referer check.**
- **Claim:** `discourse_expires_in` uses `Middleware::AnonymousCache`, whose key is only HTTP_HOST + REQUEST_URI (anonymous_cache.rb:14). Once one valid-referer request has been cached, the middleware serves it to any referer for a minute, and the controller check never runs.
- **Also:** `request.referer` is baked into the cached layout as the `postMessage` target (layouts/embed.html.erb), so other embedders receive the wrong target origin.

**10. app/controllers/embed_controller.rb:28. Minor: invalid header value.**
- `X-Frame-Options: ALLOWALL` is not a valid value. It only works because browsers ignore invalid values.
- **Fix:** omit the header, or use CSP `frame-ancestors <embeddable_host>`.

**11. app/views/embed/best.html.erb:6. Minor: `<%- end if %>`.**
- The ERB compiles to `end if` followed by a newline, so the next buffer append becomes the condition of the whole if/else. It renders by accident (the append returns a truthy value).
- **Fix:** use `<%- end %>`.
- **Evidence:** reasoned from Erubis statement handling. Controller specs don't render views, so no test covers this.

**12. lib/tasks/disqus.thor:148. Minor: regressions in the Disqus import task.**
- **Options removed:** `--category` is gone (users who pass `-c` now get an error), and the thread's `created_at` is no longer kept.
- **Network failures abort the whole import:** every thread now does a live HTTP fetch through `import_remote` (`open(url).read`), with no rescue.
- **Re-runs duplicate comments:** `import` returns the existing post, so the comment loop runs again.

**13. db/migrate/20131219203905_add_cook_method_to_posts.rb:3. Minor: table rewrite under lock.**
- `add_column ... default: 1, null: false` on `posts` rewrites the whole table under an exclusive lock on PostgreSQL versions before 11. Large forums will see downtime.

**14. Gemfile:209-211. Minor: lockfiles not updated.**
- The new gems were added only to `Gemfile_rails4.lock`. `Gemfile.lock` (used with `RAILS3=1`) and `Gemfile_rails_master.lock` were not updated, so `bundle install --deployment` fails in those modes.
- **Evidence:** `grep -c "simple-rss\|ruby-readability" Gemfile.lock Gemfile_rails_master.lock` returns 0 for both.

**15. spec/controllers/embed_controller_spec.rb:8. Minor: test gaps.**
- **Passes for the wrong reason:** "is 404 without an embed_url" passes because `ensure_embeddable` raises InvalidAccess (403) before `params.require` runs. `should_not be_success` hides that.
- **Not covered:**
  - `PollFeed#poll_feed`
  - view rendering
  - the XSS and escaping path
  - the update path when the post has been deleted

## Files not reviewed (or only partly)
- **Gemfile_rails4.lock:** generated lockfile. I only checked that the new gem entries were present.
- **app/assets/stylesheets/embed.css.scss:** presentation only. No behaviour or security impact.
- **config/locales/client.en.yml and config/locales/server.en.yml:** string additions. I skimmed them for missing keys (the `embed.*` keys used by the views are present) and did not review them further.
- **db/migrate/20131210181901_migrate_word_counts.rb:** whitespace and EOF-newline change only.

## Not checked
- None of this was executed. The quote-in-URL XSS (finding 1) depends on the embeddable host returning 200 for an arbitrary query string, which is true of most sites; I did not test it against a real host.
- My claims about SimpleRSS field mapping (finding 4) come from memory of the library, not from the installed gem source.
