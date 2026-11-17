I reviewed `change.patch` myself, as the brief asked. The `superpowers:requesting-code-review` skill says to send the review to a subagent; I didn't, because the brief rules that out. Base 728845d008, head ecfa17b5a7. There was no spec, so the bar was what an operator of a multisite Discourse would expect: a missing translation falls back to the site's default locale and then to English, and the right text appears in web requests and background jobs.

**Verdict: not ready to merge.** The fallback chain now depends on a per-site setting, but the translation cache it feeds is shared by every site in the process. The new fallback locales are also only loaded on the web request path. There is no Ruby in this sandbox and I did not run the test suite, so every finding below is reasoned from the source, not shown by a failing command.

## Important

**1. `config/initializers/i18n.rb:17` with `lib/freedom_patches/translate_accelerator.rb:72` — one site's fallback text gets served to other sites.**
- **Claim:** In multisite, a fallback string resolved for site A is shown to users on site B. The same stale cache keeps an old fallback after an admin changes `default_locale`.
- **Evidence:**
  - `FallbackLocaleList#[]` returns `[locale, SiteSetting.default_locale.to_sym, :en]`, and `SiteSetting` differs per site.
  - The cache in `I18n.translate` is one process-wide LRU (`@cache`), keyed on `"#{key}#{config.locale}#{config.backend.object_id}"`. Nothing in that key identifies the site or its default locale.
  - The app is multisite: `app/jobs/base.rb:150` calls `RailsMultisite::ConnectionManagement.establish_connection(db: db)` for each site in the same process.
- **Example:** site A has default `fr`, site B has default `de`, both allow user locales, and a user on each has locale `es`. If a key is missing from `es`, whichever site looks it up first caches its fallback (French or German) under the `es` key. The other site then gets that string.
- **Why this is new:** before the patch, Rails' `config.i18n.fallbacks = true` fell back to `I18n.default_locale`, which is the same for every site, so the cache key was enough.

**2. `config/initializers/i18n.rb:20-22` with `app/controllers/application_controller.rb:159` — fallback locales are only loaded in web requests, so jobs show "translation missing".**
- **Claim:** `I18n.fallbacks.ensure_loaded!` is only called from `ApplicationController#set_locale`. Other code that sets the locale never loads the fallback locales:
  - `app/jobs/base.rb:151` sets `I18n.locale = SiteSetting.default_locale`.
  - `app/services/post_alerter.rb:138` uses `I18n.with_locale(user.effective_locale)`.
  - `lib/post_destroyer.rb:102`, mail jobs, and rake tasks do the same.
- **Evidence:**
  - `I18n.translate` (`translate_accelerator.rb:68`) loads only `config.locale`.
  - `load_locale` loads `.rb` files plus the single `*.<locale>.yml` file it is asked for.
  - A Sidekiq process whose sites all use non-English locales may never load `:en`. When a key is missing from the user's or site's locale, the Fallbacks backend tries `:en`, finds no data there, and returns "translation missing".
  - For lookups without extra arguments, that "missing" string is frozen into the LRU cache and stays even after the locale loads later.
- **Fix direction:** load the fallback locales inside `I18n.translate`/`load_locale` instead of in a controller hook. That one change covers all callers.

**3. Tests — nothing added for the new behaviour.**
- **Claim:** The patch adds a new `FallbackLocaleList`, a new public `I18n.ensure_loaded!`, and changes how lookups resolve in every environment, with no spec.
- **Evidence:**
  - `spec/components/` has only `js_locale_helper_spec.rb` for locale code.
  - No spec covers the fallback order (user → site default → en), the multisite case in finding 1, or the job path in finding 2.
  - An integration spec of the form "set site A default to `fr`, translate a key missing in `es`, switch to site B, translate again" would catch finding 1.

## Minor

**4. `config/initializers/i18n.rb` — fallbacks are now on in development and test too.**
- **Claim:** Before the patch, fallbacks were enabled only in production, profile and cloud66 production. Now they are on everywhere.
- **Evidence:** missing keys in development will silently show English instead of a visible "translation missing" marker. That hides gaps from developers and translators, and it may change test results that relied on missing-key output. It's unclear whether this was intended; the commit message doesn't say.

**5. `config/initializers/i18n.rb:1` — the `# order: after 02-freedom_patches.rb` comment does nothing.**
- **Claim:** Rails doesn't read this comment. The file runs after `02-freedom_patches.rb` only because `i18n.rb` sorts after `02-…` alphabetically.
- **Evidence:** no other initializer uses this convention; it appears only in this file. Renaming the file to something like `000-i18n.rb` would silently break the ordering.

**6. `config/initializers/i18n.rb:3,7,11,15-16` — new comments, including a TODO.**
- **Claim:** This breaks the user's documented standard in CLAUDE.md ("DO NOT ADD COMMENTS unless asked").
- **Evidence:** the comments mostly repeat what the code says ("Include fallbacks module"). This applies only if that standard governs this repo.

**7. `lib/freedom_patches/translate_accelerator.rb:62-65` — `ensure_loaded!` sets up `@loaded_locales` but `translate` doesn't.**
- **Claim:** `ensure_loaded!` does `@loaded_locales ||= []`, but `translate` (line 68) still calls `@loaded_locales.include?` with no guard.
- **Evidence:** this is not reachable after `reload!`. It's an inconsistency, not a bug.

## Files reviewed
All 8 files in the patch:
- `app/controllers/application_controller.rb`
- `config/cloud/cloud66/files/production.rb`
- `config/environments/production.rb`
- `config/environments/profile.rb`
- `config/initializers/i18n.rb` (new)
- `config/initializers/pluralization.rb` (deleted; the pluralization include moved into the new `i18n.rb` unchanged)
- `lib/freedom_patches/translate_accelerator.rb`

Removing `config.i18n.fallbacks` from the three environment files is consistent, since the new initializer replaces it.

**Files not reviewed:** none.

## Set aside
- The TODO about per-language chains (for example zh_TW → zh_CN): this is future scope, not a defect.
- How the i18n 0.7.0 gem handles `:default` inside the Fallbacks module: I couldn't read the gem source here. A `find /` to locate it stalled and was moved to the background, still running when I finished. The uncached `args.length > 0` path means this doesn't affect findings 1 and 2.

**Not checked:** I couldn't run Ruby, the specs or the gem source, so findings 1 and 2 are reasoned rather than reproduced. They are the ones to confirm with a multisite spec before merging.
