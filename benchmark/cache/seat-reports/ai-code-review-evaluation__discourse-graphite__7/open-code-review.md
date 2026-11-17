## Review: d38c4d5f74 "scale-color $lightness must use $secondary for dark themes"

I ran OCR delegate in range mode (7554b5e3c4..d38c4d5f74). It found 32 reviewable files out of 32, with 115 lines added and 115 removed, and gave every file the same generic system/default ruleset. The diff I generated is identical to change.patch in the + and - lines. I reviewed all 32 files: 32 total, 32 reviewed, 0 skipped, 100% coverage.

**How the change works.** It wraps every `scale-color($primary, $lightness: X%)` as `dark-light-choose(scale-color($primary, X%), scale-color($secondary, (100-X)%))`. `dark-light-choose` is defined in `common/foundation/variables.scss:46`. It returns the first argument when `$primary` is darker than `$secondary`, which is the light theme. So the change is only correct if the first argument is exactly the old value: then nothing changes in the light theme. I scripted that check over every - and + pair. 5 of 115 lines fail it. Each of these silently changes the default light-theme colours, and its dark-theme value no longer matches the 100-X rule.

### Important

1. **`app/assets/stylesheets/desktop/topic-post.scss:291`** (`.topic-meta-data h5 a`, the bold poster-name link). The old value was `$lightness: 30%`. The new light value is `70%` and the new dark value is `30%`; the pair is flipped. On the default light theme, poster names on desktop go from dark grey to pale grey, which is a large contrast and readability regression. The dark-theme value also does not match the stated rule, which would give `$secondary` at 70%.
   - Evidence: `git --no-pager diff 7554b5e3c4 d38c4d5f74 -- app/assets/stylesheets/desktop/topic-post.scss | grep -A1 'lightness: 30%);$'`
   - This is reasoned; there is no Sass compiler in the environment (no sass, sassc or ruby).

2. **`app/assets/stylesheets/mobile/modal.scss:102`** (`.custom-message-length`). The old value was `70%`. The new light value is `30%` and the new dark value is `70%`; the pair is flipped. The same rule in `desktop/modal.scss:94` was converted correctly (`70%` / `30%`), so mobile and desktop now disagree. In the light theme, the faint hint text becomes dark; in the dark theme it becomes near-white.
   - Evidence: `grep -n -A2 custom-message-length app/assets/stylesheets/{desktop,mobile}/modal.scss`
   - This is reasoned.

### Minor

These three change the light-theme value with no explanation. They could be intentional normalisation, but the commit message says the change is dark-theme only.

3. **`app/assets/stylesheets/desktop/user.scss:522`** (`.group-member-info .name`). Old value `30%`; new values `50%` light and `50%` dark. The expected values were `30%` / `70%`.
4. **`app/assets/stylesheets/mobile/user.scss:497`** (`.group-member-info .name`). This is the same change as item 3: old `30%`, new `50%` / `50%`.
5. **`app/assets/stylesheets/mobile/topic-post.scss:182`** (`h3`). Old value `20%`; new values `50%` / `50%`. The expected values were `20%` / `80%`. Mobile post headings get noticeably lighter in the light theme.

### Checked and found fine

- **Function in scope:** `dark-light-choose` is available in every compiled bundle. `common.scss` imports `common/foundation/variables` before the components and base files, and `embed.css.scss` imports variables directly.
- **The other 110 conversions:** each keeps the original light value, and its dark value is 100-X.

### Not flagged

The repo already has `dark-light-diff($primary, $secondary, X, -Y)` in `variables.scss:38` for this kind of adjustment. The patch's 230-character inline expression repeats the same idea 115 times. That is a maintainability concern, not a defect, so it is not a finding.

### Gaps

There is no spec, so I judged against the commit message. I did not compile the SCSS or render it, because no Sass toolchain is installed and installing one was not allowed. The colour effects are reasoned from the `scale-color` semantics. Base-revision blobs were not fully available because this is a partial clone and the fetch was blocked, so I took the original values from the patch's - lines.
