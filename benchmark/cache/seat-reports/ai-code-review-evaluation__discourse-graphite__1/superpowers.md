Review of ffbaf8c542 "FEATURE: automatically downsize large images" (base 3f71fa15c9). There is no spec, so I judged it against the commit title and the existing callers. I did not run anything: Ruby isn't installed in this sandbox, so every Critical and Important claim below is reasoned from the source. Each one comes with the command or test that would prove it.

Findings

1. app/models/optimized_image.rb:145-151 — **Critical** — The second `def self.downsize(from, to, dimensions, opts={})` silently replaces the four-argument `downsize(from, to, max_width, max_height, opts={})`. Ruby has no overloading. The only remaining signature takes 3 or 4 arguments.
   - Evidence: app/jobs/regular/resize_emoji.rb:14 still calls `OptimizedImage.downsize(path, path, 100, 100, opts)` with 5 arguments. The job is enqueued from app/models/emoji.rb:73.
   - Effect: every custom emoji upload now raises `ArgumentError: wrong number of arguments (5 for 3..4)`, so emoji are no longer shrunk to 100x100.
   - The suite won't catch it: spec/jobs has no ResizeEmoji spec, and optimized_image_spec stubs `resize`.
   - Check: `ruby -wc app/models/optimized_image.rb` prints "warning: method redefined; discarding old downsize". Failing test: `Jobs::ResizeEmoji.new.execute(path: "spec/fixtures/images/logo.png")` raises ArgumentError on the patched code.

2. app/assets/javascripts/discourse/lib/utilities.js:182 — **Important** — The client-side size check is now hardcoded to 10 MB for every upload type. It used to be `max_#{type}_size_kb`.
   - Attachments: `max_attachment_size_kb` is no longer enforced in the browser. Files between the setting and 10 MB are uploaded in full, then rejected by lib/validators/upload_validator.rb:81-86 and reported back asynchronously through MessageBus.
   - Images: a site that sets `max_image_size_kb` above 10240 now has its own limit overridden in the browser. Uploads it used to accept are blocked with an error naming a limit the admin never set.
   - Downsizing only applies to images, yet the patch drops the per-type limit for all types.
   - Reasoned. A QUnit test of `Discourse.Utilities.validateUploadedFiles` with `max_attachment_size_kb = 1` and a 2 KB attachment would fail on the patched code.

3. app/assets/javascripts/discourse/lib/utilities.js:246 — **Important** — The HTTP 413 handler now always says the limit is 10240 KB. A 413 comes from nginx or another proxy, whose limit is whatever the operator configured. The 10m in config/nginx.sample.conf:61 is only a sample default, so the message misstates the real limit on many installs. Reasoned.

4. app/controllers/uploads_controller.rb:63-70 — **Important** — Downsizing animated GIFs with "80%" cannot work. When `allow_animated_thumbnails` is on and the file is a .GIF, `optimize` routes to `downsize_instructions_animated`, which runs `gifsicle --resize-fit 80%` (optimized_image.rb:113-122).
   - `--resize-fit` expects WxH, not a percentage, so gifsicle exits non-zero and `convert_with` returns false.
   - The loop then spends all 5 attempts on failing processes, and the upload is still rejected by the size validator.
   - Reasoned from the gifsicle CLI syntax; not executed here.

5. app/controllers/uploads_controller.rb:64-69 — **Important** — SVGs are included. `FileHelper.is_image?` matches .svg, so an oversized SVG goes through `convert file.svg[0] -resize 80%\> file.svg`. That rewrites the user's SVG in place with ImageMagick's re-encoded output. Upload.create_for (upload.rb:63) and OptimizedImage.create_for (optimized_image.rb:44) both deliberately skip SVG for this reason. Reasoned.

6. app/controllers/uploads_controller.rb:65-69 — **Important** (production risk) — Each upload can now trigger up to 5 sequential ImageMagick runs, each followed by ImageOptim (`convert_with`), on files up to 10 MB.
   - Non-API uploads run in `Scheduler::Defer.later` (uploads_controller.rb:19), a shared background queue. Large uploads will stall unrelated deferred work.
   - The loop has no stop on failure. If `downsize` returns false (bad image, convert error), it retries the same failing command until attempts run out.
   - Reasoned.

7. app/controllers/uploads_controller.rb:55 — **Minor** — The API URL download cap moved from `max_image_size_kb` to a hardcoded `10.megabytes`, whatever the type or the site settings. A site with limits above 10 MB now has API URL uploads cut off at about 10 MB. `FileHelper.download` stops reading once the file passes the cap, so the result is a broken file, not a rejection.

8. No tests — **Important** (plan alignment) — The change adds a new code path in the upload controller, refactors OptimizedImage's public signature and alters client-side validation, with zero spec or QUnit changes. Finding 1 got through because nothing covers the emoji path or the new loop.

Unreviewed files: none. All three files in the patch were reviewed (utilities.js, uploads_controller.rb, optimized_image.rb).

Not checked: whether ImageMagick reads the `80%\>` geometry as intended for still images (I believe it shrinks correctly), and whether ImageOptim replacing the file in place leaves the open tempfile handle showing a stale size. Both are reasoned, not run.
