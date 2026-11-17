I reviewed the patch with `open-code-review:delegate-review` in range mode, 728845d008..ecfa17b5a7. I made no edits. I did not install anything or run the test suite, so every finding below is reasoned from the code. None has an executed failing test.

**Coverage**
- 7 files in the patch: 6 reviewed, 1 not reviewed.
- Reviewed: `app/controllers/application_controller.rb`, `config/initializers/i18n.rb`, `lib/freedom_patches/translate_accelerator.rb`, `config/environments/production.rb`, `config/environments/profile.rb`, `config/cloud/cloud66/files/production.rb`.
- Not reviewed: `config/initializers/pluralization.rb`. It is deleted and OCR left it out of the review. I compared it by hand: its two lines reappear unchanged at the top of `config/initializers/i18n.rb`, so nothing is lost.

## Findings

### 1. Important — translation cache ignores the fallback chain; wrong-language strings leak between sites
**Where:** `config/initializers/i18n.rb:17`, together with the existing cache in `lib/freedom_patches/translate_accelerator.rb:73`.

**Claim:** The fallback chain now depends on the per-site setting `SiteSetting.default_locale`. But the process-wide translation cache key does not include that setting.

**Evidence:**
- The cache key is `"#{key}#{config.locale}#{config.backend.object_id}"`, stored in one cache per process (`@cache` on the `I18n` singleton).
- The fallback order is `[locale, SiteSetting.default_locale.to_sym, :en]`.
- Discourse is multisite: `rails_multisite` is in `Gemfile.lock`, and `app/jobs/base.rb:150` switches the database per site.
- Example: site A's default locale is `de`, site B's is `es`. A user with locale `fr` asks for a key that has no French text. Whichever site asks first stores its own fallback (German or Spanish), and the other site then gets that string.
- The same happens on one site when an admin changes `default_locale` (the setting is marked `refresh: true`): old fallback strings stay in the cache until they are evicted.
- Calls with interpolation arguments skip the cache, so the same key can come back in different languages depending on whether arguments were passed.
- Before this patch, production fell back only to `I18n.default_locale`, which is the same for every site, so the cache was consistent.

**Test sketch (would fail on the patched code):**
1. Set `SiteSetting.default_locale = 'de'`, set `I18n.locale = :fr`, and call `I18n.t(k)` for a key missing in French but present in German.
2. Set `SiteSetting.default_locale = 'es'` and call `I18n.t(k)` again.
3. Expect the Spanish string; the patched code returns the cached German one.

**Fix direction:** add `SiteSetting.default_locale` to the cache key, or clear the cache when the setting changes.

### 2. Important — fallback locales are only loaded for web requests
**Where:** `app/controllers/application_controller.rb:159` and `lib/freedom_patches/translate_accelerator.rb:62-65`.

**Claim:** Outside controller requests, the fallback locales may never be loaded, so the fallback quietly fails.

**Evidence:**
- Translations are loaded per locale on demand. `I18n.translate` only loads `config.locale`.
- The fallback locales (site default and `:en`) are loaded only by `I18n.fallbacks.ensure_loaded!`, which is called only in `ApplicationController#set_locale`.
- Sidekiq jobs never call it: `app/jobs/base.rb:151` sets the locale, and `app/services/post_alerter.rb:138` uses `I18n.with_locale(user.effective_locale)`. Mailers, rake tasks and the console don't call it either.
- In a Sidekiq process that has not yet loaded the site default locale or `:en`, a missing key skips those unloaded locales and returns "translation missing". Finding 1 makes this worse: that missing-translation string then goes into the cache and stays there even after the locale loads.
- Loading belongs inside the fallback lookup or the translate path, not in a controller hook.

### 3. Minor — fallbacks are now on in development and test
**Where:** `config/initializers/i18n.rb:8-9`.

**Claim:** Fallbacks used to be enabled only in production, profile and cloud66 (`config.i18n.fallbacks = true`). The new initializer turns them on in every environment, including development and test.

**Evidence:** In development and test, a key missing in a non-English locale now shows English instead of "translation missing", which hides missing translations during development. Specs that expect a missing-translation result may change behaviour. This looks intentional, but it is not stated.

### 4. Minor — no tests for the new behaviour
The patch adds no specs for the fallback order (user locale, then site default, then en), for `ensure_loaded!`, or for how fallbacks interact with the cache. Findings 1 and 2 are exactly the gaps such a test would have caught.

## Checked and not a problem
- **Rails 4.1.10 i18n setup:** Rails only sets up its own fallbacks when `config.i18n.fallbacks` is set. The patch removes that setting from all three environment files, so Rails will not replace the custom `I18n.fallbacks`.
- **Initializer order:** `i18n.rb` sorts after `02-freedom_patches.rb`, so the patched backend is in place when the new code runs. The `# order:` comment only documents this; Rails loads initializers alphabetically.
- **Unsynchronised `@loaded_locales ||= []`** in `ensure_loaded!`: the read is outside the lock, but `load_locale` re-checks inside the mutex, so it is harmless.

**Not done:**
- I did not verify the i18n 0.7.0 gem source (the search for it timed out), so its `Fallbacks#translate` behaviour is from memory.
- Spec gaps: none to report, since there is no spec.
- I found no documented project coding standards to check against.
