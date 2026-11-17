## mattpocock-skills:code-review on change.patch (62db063e1e..4f8aed295a)

I did both axes myself and spawned no sub-agents. I ran no tests, as instructed, so every claim below is reasoned and none was executed.

**Standards sources I used:** `CONTRIBUTING.md` (§3 "Code" and §4 "Coding Conventions"), `.jshintrc`, `docs/TESTING.md`, and the documented supported Ruby versions (README.md:23 says 1.9.3+, `.travis.yml` uses 2.0.0). The repo has no `.rubocop.yml` and no CODING_STANDARDS file. As the caller asked, I left out the generic Fowler smell baseline.

## Spec

There is no spec, so this axis was skipped. I checked for issue refs in the commit message and for a `docs/`/`specs/` file matching the feature, and found neither.

## Standards

1. **app/jobs/scheduled/poll_feed.rb:24-38, app/models/topic_embed.rb:44-53, lib/topic_retriever.rb:36-53 — Important.**
   - **Claim:** this breaches CONTRIBUTING.md §3, "Include tests, and ensure they pass". The new feed-import and remote-fetch paths have no tests:
     - `PollFeed#poll_feed` is always stubbed in `spec/jobs/poll_feed_spec.rb`.
     - `TopicEmbed.import_remote` is never called in a spec.
     - `TopicRetriever#perform_retrieve` and `#fetch_http` are always mocked out (`expects(:perform_retrieve)`).
   - **Why it matters:** this code parses third-party RSS and HTML, which is where defects hide. For example, `i.content.scrub` (poll_feed.rb:35) raises NoMethodError for a plain RSS 2.0 item that has only `<description>`, because SimpleRSS leaves `content` nil there. With `retry: false`, one such item aborts the whole hourly import.
   - **Test that would fail on the patched code (reasoned):** stub `open`/`SimpleRSS.parse` to return an RSS item with link, title and description but no content, set the three feed settings, then call `Jobs::PollFeed.new.poll_feed`. It raises `NoMethodError: undefined method 'scrub' for nil`.

2. **spec/jobs/poll_feed_spec.rb:18-29 — Minor.**
   - **Claim:** two of the specs pass for the wrong reason, which falls short of the §3 test requirement.
   - **Evidence:** "requires feed_polling_url" and "requires embed_by_username" stub only their own setting. `feed_polling_enabled` defaults to `false` (config/site_settings.yml:355), so `execute` short-circuits on the first condition. Both pass even if the url/username checks are deleted from poll_feed.rb:15-17.

3. **spec/controllers/embed_controller_spec.rb:8-11 — Minor.**
   - **Claim:** the "is 404 without an embed_url" spec passes for the wrong reason.
   - **Evidence:** `embeddable_host` defaults to `''`, so the `ensure_embeddable` before_filter raises InvalidAccess (403) before `params.require(:embed_url)` runs. The spec asserts only `should_not be_success`, so the missing-param path (a 400) is never exercised.

4. **app/controllers/embed_controller.rb:13 (also spec/controllers/embed_controller_spec.rb:50) — Minor.**
   - **Claim:** `{best: 5}` breaches CONTRIBUTING §4, "use spaces around ... `{` and before `}`".
   - **Evidence:** it should read `{ best: 5 }`, or just `best: 5`.

5. **app/models/topic_embed.rb:44, lib/topic_retriever.rb:3 — Minor.**
   - **Claim:** `opts=nil` breaches CONTRIBUTING §4, "use spaces around operators".
   - **Caveat:** the repo itself is inconsistent here. Both `opts={}` (e.g. app/jobs/base.rb:153) and `maxlength = nil` (post.rb:229) appear.

6. **app/models/topic_embed.rb:10, 44, 56, 78; app/models/post.rb:63 — Minor.**
   - **Claim:** these breach CONTRIBUTING §4, "prefer `class << self; def method; end` over `def class.method` for class methods".
   - **Counter-evidence:** §3 also says "Adhere to common conventions you see in the existing code". The codebase has 474 `def self.` definitions against 11 `class << self` (app/models + lib), and post.rb:63 matches its neighbours. Treat this as a judgement call.

**Standards I checked with no violation:**
- Tabs and trailing whitespace: none in the added lines.
- Ruby 1.9 hash syntax: used throughout.
- "avoid `return` when not required": every new `return` is a necessary guard.
- Brace vs `do...end` blocks: correct.
- `.jshintrc`: embed.js declares its globals via `/* global */`, and its function and variables are all used.
- Ruby compatibility: `String#scrub` would be Ruby 2.1+, but `lib/freedom_patches/scrub.rb` backports it.
- `docs/TESTING.md` says specs need no network, and none of the new specs make network calls.

**Outside my remit, noted for the other seats without a full writeup:**
- **Raw HTML in posts:** `cook_method: raw_html` (topic_embed.rb:22, post.rb:133) puts unsanitised feed or remote HTML straight into `cooked`. That HTML is rendered with `raw` (best.html.erb:19) and in normal topic views, so a compromised feed means stored XSS.
- **Unescaped URL:** `url` is interpolated into an `<a href='...'>` without escaping (topic_embed.rb:13).
- **Argument mutation:** `contents <<` (topic_embed.rb:13) mutates the caller's string.
- **Existing migration edited:** a shipped migration (20131223171005_create_top_topics.rb) was changed to add `force: true`.
- **Stray `end if`:** best.html.erb:6 has `<%- end if %>`, which works only because the template's next output becomes the `if` condition.
- **Lockfiles not updated:** `Gemfile.lock` (Rails 3) and `Gemfile_rails_master.lock` were not updated for the two new gems.

**Summary:** Standards has 6 findings, the worst being the untested feed-import and fetch paths (#1). Spec has none because there is no spec.

## Files not reviewed
- `Gemfile_rails4.lock`: generated lockfile. I only confirmed it adds the two gems plus `guess_html_encoding`.
- `app/assets/stylesheets/embed.css.scss`: the repo documents no SCSS standard. I only skimmed it.
- `config/locales/client.en.yml` and `config/locales/server.en.yml`: string additions only. I checked that the keys match their usages but did not check style.
- `db/migrate/20131210181901_migrate_word_counts.rb`: whitespace-only change. I skimmed it, and no documented standard applies.
- `lib/tasks/disqus.thor`: skimmed only. It removes the `--category` option, but with no spec I can't judge whether that removal was intended.

Every other file in the patch was reviewed in full.
