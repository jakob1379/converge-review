## Correctness review of PR "UX: show complete URL path if website domain is same as instance domain" (7a5fbae060 → 267d8be1f5)

I ran it through OCR delegate-review in range mode. OCR marked 2 of the 5 files as reviewable and excluded three: two `.es6` files for their extension, and the spec for its path. I reviewed all 5 from the patch anyway, so coverage is 5/5 and no file was skipped. I did not run any tests (no Ruby on the machine, and the brief forbade it), so every finding below is reasoned from the code, not reproduced. I made no edits.

### Important

**1. The website name on the profile goes stale after the user edits their website. This is a regression.**
- **Where:** `app/assets/javascripts/discourse/templates/user/user.hbs:66-71`, `app/assets/javascripts/discourse/controllers/user.js.es6` (removed `websiteName`), `app/serializers/user_serializer.rb:137`.
- **Claim:** The old `websiteName` was computed on the client from `model.website`, so it updated as soon as the website changed. The new `model.website_name` is set once by the server and nothing refreshes it.
- **Evidence:**
  - `User#save` in `app/assets/javascripts/discourse/models/user.js.es6:206-213` copies back only `bio_excerpt` from the PUT response. It ignores `data.user.website_name`, even though `users_controller#update` returns the full `UserSerializer`.
  - The user route reloads details (`findDetails`) only in `afterModel` when you enter the user route (`routes/user.js.es6:51-54`). Moving from preferences back to the profile inside the same user route does not reload.
- **What the user sees:** after changing website A to B, the profile shows A's name as the link text while the link points to B. If the user had no website before and adds one, the globe and link stay hidden until a full page reload.
- **Fix:** copy `website_name` back in `save().then(...)`, or keep a client-side computed fallback.
- **Test:** none run. An acceptance test would show it: set the website in preferences, save, go to the summary, and check the link text.

### Minor

**2. `include_website_name` is dead code (`user_serializer.rb:153`).**
- active_model_serializers 0.8.3 (from Gemfile.lock) only calls `include_<attr>?` with a trailing `?`. Every other filter in this file follows that, e.g. `include_email?` and `include_card_image_badge_id?`.
- So `website_name` is always serialized, as `null` when there is no website. That is harmless only because `URI("").host` is nil. The method's intent is never applied.

**3. Sibling-domain branch matches across public suffixes (`user_serializer.rb:143-145`).**
- It treats two hosts with the same number of labels (more than 2) and equal labels after the first as the same site.
- So `attacker.co.uk` matches an instance at `forum.co.uk`, and `a.github.io` matches `forum.github.io`: the full path is shown for unrelated sites.
- Impact is cosmetic: the path is the real URL and is HTML-escaped. But it breaks the PR's stated rule ("website domain is same as instance domain").

**4. Matching is inconsistent (`user_serializer.rb:137-150`).**
- Host comparison is case-sensitive: `URI` keeps the case, so `http://Example.com/u` does not match `example.com`.
- It is asymmetric: website `www.example.com` with instance `example.com` falls into the `else` branch and shows the host only, while the reverse shows the path.
- A port is silently dropped when the path is shown: `example.com:8080/u` displays as `example.com/u`.

**5. Test gap (`spec/serializers/user_serializer_spec.rb:76-90`).** The `www.example.com == forum.example.com` branch has no spec, and that is the branch with the bug in finding 3. The spec also does not check that `website_name` is absent when there is no website, which would have caught finding 2.

### Checked and not an issue
- **XSS:** `{{model.website_name}}` is output in text nodes and the `title` attribute with double braces, so it is HTML-escaped. The `href={{model.website}}` part is unchanged code, and `UserUpdater#format_url` forces an `http` prefix.
- **Bad input:** `URI(...)` on malformed input is rescued on the first line. The later `URI(website.to_s).path` calls only run after a successful parse, so they cannot raise.
- **`"." << website_host`:** the file has no `frozen_string_literal`, so this mutates a fresh literal and is fine.
- **Other users of `websiteName`:** none remain in `app`, `lib`, `plugins` or `spec`.
- **`models/user.js.es6`:** a doc-comment fix only.

Not verified: the Ember behaviour in finding 1 is inferred from the route and model code, not run in a browser.
