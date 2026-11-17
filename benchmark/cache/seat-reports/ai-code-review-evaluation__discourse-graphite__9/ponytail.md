## Ponytail review: discourse-graphite__9 (Localization fallbacks, server side), over-engineering only

**What this change does:** It removes `config.i18n.fallbacks = true` from three environment files. It adds `config/initializers/i18n.rb`, which turns on the I18n Fallbacks backend and sets a custom fallback order: user locale, then site default locale, then `:en`. The old pluralization initializer is folded into the same file. Translations load lazily (only when first needed), so the change also adds `I18n.ensure_loaded!` and `FallbackLocaleList#ensure_loaded!`, and `ApplicationController#set_locale` calls them so every locale in the chain is loaded before the request runs.

Assumed load: a multi-process web app (Unicorn plus Sidekiq). There is no spec, so I judged the change against the PR title only.

### Should fix

1. **`I18n.ensure_loaded!` repeats `load_locale`** (`lib/freedom_patches/translate_accelerator.rb:62-65`)
   - **What this is:** A new public method on `I18n` that loads a locale's yml files if they are not loaded yet.
   - **Problem:** `load_locale` (L46-60) already returns early when `@loaded_locales.include?(locale)`, inside the mutex. So the outer `unless` adds nothing. `@loaded_locales ||= []` never runs in practice: the Rails I18n railtie calls `I18n.reload!` at boot, which sets it to `[]` (L40). If it ever were nil, the existing `translate` (L68) would crash first. This is reasoned, not run.
   - **Fix:** Delete the method. In `FallbackLocaleList#ensure_loaded!`, call `I18n.load_locale(l)` directly.
   - **If we skip it:** Two load paths with two guards that must stay in sync. That is about -5 lines.

2. **`FallbackLocaleList < Hash` inherits a Hash it never fills** (`config/initializers/i18n.rb:12`)
   - **What this is:** The object assigned to `I18n.fallbacks`. In i18n 0.7.0 (`Gemfile.lock:126`), `I18n.fallbacks=` is a plain assignment, and the Fallbacks backend only calls `I18n.fallbacks[locale]`.
   - **Problem:** Only `[]` is overridden. Every other Hash method gives wrong answers. `I18n.fallbacks.fetch(:de)` raises KeyError, `.keys` and `.each` return nothing, and `.to_h` is `{}`. The parent class adds nothing and misleads anyone who inspects the object.
   - **Fix:** Drop `< Hash` and make it a plain class with `[]` and `ensure_loaded!`. Zero net lines.
   - **If we skip it:** Later code that treats `I18n.fallbacks` as the hash it claims to be gets silent empty results.

### Nice to have

3. **The `# order: after 02-freedom_patches.rb` header points to a mechanism that does not exist** (`config/initializers/i18n.rb:1`)
   - **What this is:** A comment that implies initializers are ordered by a directive.
   - **Problem:** Nothing in the repo reads `order:` (I grepped). Rails loads initializers in sorted file-name order, so `i18n.rb` runs after `02-...` only because of its name. Nothing in this file needs the freedom patches at load time anyway. The patches are only used when `ensure_loaded!` is called during a request.
   - **Fix:** Delete the line, or rename the file to a numbered name such as `03-i18n.rb` if the order matters. -1 line.
   - **If we skip it:** A future reader trusts a directive that does nothing.

### Outside my remit (reasoned, not run)

The new loading hook is wired only into `ApplicationController#set_locale`. Sidekiq jobs set `I18n.locale` in `app/jobs/base.rb:151` and never call `I18n.fallbacks.ensure_loaded!`. So a fallback locale that was never loaded in that process (for example `:en` when the site default is `:de`) is not available to emails and jobs. Calling the load from the existing locale-load point in `I18n.translate` (`translate_accelerator.rb:68`) would cover both web requests and jobs, and would make the controller hook and finding 1 unnecessary. The cost is one `I18n.fallbacks[...]` array per `translate` call. This is a correctness gap, not over-engineering, so whoever owns bugs should weigh it.

Verdict: Ship after 1 and 2, which are cheap. None of these blocks the feature.
Lean: about -6 lines possible.

**Files reviewed:** all 8 files in the patch.
- `app/controllers/application_controller.rb`
- `config/cloud/cloud66/files/production.rb`
- `config/environments/production.rb`
- `config/environments/profile.rb`
- `config/initializers/i18n.rb`
- `config/initializers/pluralization.rb` (deleted)
- `lib/freedom_patches/translate_accelerator.rb`

**Files not reviewed:** none.

**Not checked:** I did not read the i18n 0.7.0 gem source. A filesystem search for it timed out, so the `fallbacks=` and `[]` behaviour above comes from my knowledge of that version. I did not run any tests, as instructed.
