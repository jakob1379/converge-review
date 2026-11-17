Seat: over-engineering only, advisory. Skill used: ponytail:ponytail-review. Load assumed: a normal Discourse forum with one embedding host. All line numbers are head-file (4f8aed295a) line numbers.

What this change does: it adds a public `embed/best` iframe endpoint that shows a topic's best posts for an external blog URL. When no topic exists yet, the endpoint queues a job that builds one from an RSS feed or by scraping the page (TopicEmbed, TopicRetriever, PollFeed). It also adds a `raw_html` cook method so imported posts skip markdown rendering.

None of these findings is Critical or Important. The patch carries roughly 30 lines of dead or duplicated code and some unrelated edits, but that does not block shipping.

Findings

1. **Dead `feed_key` method and its require** (`app/jobs/scheduled/poll_feed.rb:4, 20-22`). Minor.
   - Claim: `feed_key` is never called, and `require 'digest/sha1'` exists only to serve it. It looks like leftover groundwork for If-Modified-Since caching that was never built.
   - Evidence: `grep -rn feed_key app lib spec` finds only the definition.
   - Fix: delete lines 4 and 20-22.

2. **Requires sit in the wrong file** (`app/jobs/scheduled/poll_feed.rb:5-7` vs `app/models/topic_embed.rb:1`). Minor.
   - Claim: PollFeed never uses PostCreator, PostRevisor or open-uri. TopicEmbed does: `PostCreator.new` at :22, `PostRevisor.new` at :35 and `open(url)` at :48. `lib/` is not autoloaded (`config/application.rb:46-48` adds only app, serializers and validators). So TopicEmbed only works because PollFeed happened to load first.
   - Evidence: grep for PostCreator, PostRevisor and `open(` in poll_feed.rb. The only `open(` hit is `SimpleRSS.parse open(...)` at :29, so open-uri is the one require PollFeed really needs.
   - Fix: move the two `require_dependency` lines, plus a `require 'open-uri'`, into topic_embed.rb. PollFeed keeps its own `require 'open-uri'`. This is the same number of lines in the right place. Do not just delete them from PollFeed, or TopicEmbed breaks.

3. **Unused require of `email/sender`** (`app/jobs/regular/retrieve_topic.rb:1`). Minor.
   - Claim: this looks copied from an email job. RetrieveTopic sends no email.
   - Evidence: the file has no `Email::` reference.
   - Fix: delete the line.

4. **Copy-pasted loop in `absolutize_urls`** (`app/models/topic_embed.rb:62-73`). Minor.
   - Claim: the `a[href]` and `img[src]` blocks are the same apart from the attribute name, so a fix to one (for example protocol-relative `//host` URLs, which both get wrong the same way today) must be made twice.
   - Fix: `{ 'a' => 'href', 'img' => 'src' }.each { |tag, attr| fragment.css(tag).each { |n| v = n[attr]; n[attr] = "#{prefix}/#{v.sub(/^\/+/, '')}" if v.present? && v.start_with?('/') } }`. That saves about 6 lines.

5. **Unused locale key `embed.permalink`** (`config/locales/server.en.yml`, the `permalink: "Permalink"` line in the new `embed:` block). Minor.
   - Evidence: `grep -rn permalink app/views/embed app/views/layouts/embed.html.erb` finds nothing. No code reads `embed.permalink`.
   - Fix: delete the line, so translators do not have to translate it.

6. **Duplicated header branch in the view** (`app/views/embed/best.html.erb:2-6`). Minor.
   - Claim: the two `link_to` calls differ only in the i18n key. The odd `<%- end if %>` comes from that structure.
   - Fix: one line, `link_to(I18n.t(@topic_view.posts.present? ? 'embed.title' : 'embed.start_discussion'), @topic_view.topic.url, class: 'button', target: '_blank')`. That saves 4 lines.

7. **`opts=nil` followed by `opts || {}`** (`lib/topic_retriever.rb:3-5`, `app/models/topic_embed.rb:44,47`). Minor.
   - Claim: Ruby's default argument `opts={}` does the same job. Both call sites pass a hash or nothing.
   - Fix: use `opts={}` and drop the `opts = opts || {}` line.

8. **Unrelated churn in shipped migrations and PostRevisor** (`db/migrate/20131210181901_migrate_word_counts.rb:3,33`, `db/migrate/20131223171005_create_top_topics.rb:3`, `lib/post_revisor.rb:11`). Minor.
   - Claim: these are a whitespace edit, a removed trailing newline, a blank-line removal and a `force: true` added to a migration that has already shipped. None of them relates to embedding. Editing an already-run migration only changes behavior on fresh installs, and the diff noise hides the one real change in PostRevisor (`save(validate: !@opts[:skip_validations])` at :85).
   - Evidence: `git diff 62db063e1e 4f8aed295a -- db/migrate/20131210181901_migrate_word_counts.rb db/migrate/20131223171005_create_top_topics.rb`. (`force: true` is an existing repo pattern, so only its placement in an old migration is the issue.)
   - Fix: revert those hunks.

9. **Tests stub private methods and mock owned code** (`spec/components/topic_retriever_spec.rb:9-12, 15-18, 21-25, 32-42`; `spec/controllers/embed_controller_spec.rb:40-46`). Minor. This breaks the user's documented standard in ~/.claude/CLAUDE.md: never test private methods, never use mocks of things you own, test contracts not implementation.
   - Claim, TopicRetriever spec: it sets `expects(:perform_retrieve)` and `expects(:retrieved_recently?)`, both private. Renaming either method breaks the spec even when behavior is unchanged. It also never tests the throttle: the stubbed `retrieved_recently?` hides the redis code that actually decides whether a fetch happens.
   - Claim, controller spec: it mocks `TopicRetriever.new`, which the controller never calls (it calls `Jobs.enqueue(:retrieve_topic, ...)`). The test only passes because jobs run inline in test mode.
   - Fix: assert outcomes instead. Check whether a TopicEmbed row exists after `retrieve` (stub the HTTP call only), and in the controller check that `Jobs.enqueue` gets `:retrieve_topic`. That is a reasoned claim; I did not run the suite, per instructions.

10. **Framework-only and dead lines in specs** (`spec/models/topic_embed_spec.rb:5-8`, `spec/jobs/poll_feed_spec.rb:2`). Minor.
    - Claim: the shoulda `belong_to` and `validate_presence_of` checks only re-test ActiveRecord declarations (the documented rule is never test framework code). poll_feed_spec requires `jobs/regular/process_post`, which it never uses.
    - Fix: delete those 5 lines.

Verdict: Ship. These are advisory cleanups.
Lean: about -30 lines possible (feed_key and digest 4, email/sender 1, absolutize merge about 6, permalink key 1, header branch about 4, opts defaults 2, unrelated churn about 5, framework specs and dead require 5). Rewriting the stubbed specs would trade lines for real coverage rather than remove them.

Outside my lane, and not reviewed in depth:
- `TopicRetriever#perform_retrieve` (`lib/topic_retriever.rb:38-46`) runs the whole PollFeed synchronously for every unknown URL.
- `retrieved_recently?` uses `setnx` then `expire` in two separate calls, so a crash between them leaves a key that never expires.
- `request.referer` is written unescaped into a JS string in `app/views/layouts/embed.html.erb:10`.
- The page HTML is fetched with `open(url)` in topic_embed.rb:48.

Correctness and security seats should look at these.

Files skipped
- `Gemfile_rails4.lock`: generated lockfile. I only confirmed that `ruby-readability` and `simple-rss` are new. Both are needed (used at topic_embed.rb:45 and poll_feed.rb:28), not speculative.
- `app/assets/stylesheets/embed.css.scss`: presentation only, nothing to judge for over-engineering beyond a read-through, which found nothing.
- `config/locales/client.en.yml`: a single "Embedding" site-settings category label, required by the new site_settings group.
- Everything else in the patch was reviewed: Gemfile, embed.js, embed_controller.rb, retrieve_topic.rb, poll_feed.rb, post.rb, topic_embed.rb, the three views, server.en.yml, routes.rb, site_settings.yml, the 4 migrations, post_creator.rb, post_revisor.rb, disqus.thor, topic_retriever.rb and the 4 specs.

Not checked: I did not run the test suite, per instructions, so finding 9 is reasoned rather than shown to fail.
