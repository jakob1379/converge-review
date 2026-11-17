## Review of pinned.patch (98fa098e → 5b229316ee), done with `open-code-review:delegate-review`

**What I ran.** I used OCR delegate mode in range mode. `ocr delegate preview --from 98fa098e… --to 5b229316ee` listed 5 reviewable files. `ocr delegate rule` returned only the generic system/default checklist: there are no repo-specific rules or documented standards. There is no spec, so there are no spec gaps to report.

**Coverage.** total_files=5, reviewed_files=5, skipped_files=0, coverage_rate=100%. No files were left unreviewed.
- `app/assets/stylesheets/common/base/header.scss` [modified]: reviewed
- `app/assets/stylesheets/common/base/topic-post.scss` [modified]: reviewed
- `app/assets/stylesheets/common/base/topic.scss` [modified]: reviewed
- `app/assets/stylesheets/common/components/badges.css.scss` [modified]: reviewed
- `app/assets/stylesheets/common/foundation/mixins.scss` [modified]: reviewed

**Compile safety.** The patch should compile; I did not run a build. `common.scss` imports `common/foundation/mixins` (line 6) before `common/components/*` (line 8) and `common/base/*` (line 12), so all four new mixins resolve. `badges.css.scss` already used `@include border-radius-all`. `embed.css.scss` does not import any of the changed files.

**RTL is fine.** R2 flips `body { direction: ltr }` (`common/foundation/base.scss:15`) to rtl, and flips `margin-left: auto` to `margin-right: auto`. The flex header therefore still mirrors correctly in the `_rtl` targets.

**Verification limits.** I tried to confirm the layout findings with headless Chromium. The Nix chromium crashes inside the bash sandbox, and the Playwright headless shell is missing `libglib`. Running outside the sandbox was denied. **Every finding below is reasoned from CSS layout rules and none was run.** The repro page is at `/tmp/claude-1000/-home-jsg--t3-scratch-2026-11-12-find-a-benchmark-for-code-61e02dff-converge-bench-work-ai-code-review-evaluation--discourse-graphite--5/54e8a409-d74f-4f08-93fc-a65414f3d983/scratchpad/hdr.html`. Open it in any browser and check `body[data-r]` to get the panel width, panel height and button position.

## Findings

### 1. Important: a long topic title squeezes the header icons in the docked header (desktop)
- **Location:** `app/assets/stylesheets/common/base/header.scss:17-18,36-39` and `app/assets/stylesheets/common/base/topic.scss:30`
- **Claim:**
  - `.contents` is now a flex container whose items keep the default `flex: 0 1 auto`.
  - `.extra-info-wrapper` gets its width from its content. Its `.topic-link` is `display:block; white-space:nowrap` (`desktop/topic-post.scss:533-538`), so a long title has a very large content width.
  - Flex shrinking is split in proportion to each item's base size, so `.panel` and `.title` also shrink, not just the title wrapper.
  - The `.panel`'s minimum width is the width of its widest floated child (`.icons`, and `> li` are `float:left`). It can therefore shrink to roughly one icon. The floated icons then wrap onto a second line inside the fixed 60px header (`desktop/header.scss:10`).
- **Worked example:** 1110px wrap, title wrapper about 1500px, logo 150px, panel 200px. The overflow is about 740px. The panel loses about 80px and ends up near 120px, so its icons wrap.
- **IE10 variant:** IE10 defaults flex items to `-ms-flex: 0 0 auto`, so nothing shrinks. The panel is pushed past the right edge instead.
- **Before the patch:** the floats plus `overflow:hidden` on `.extra-info-wrapper` kept the panel at full width.
- **Fix:** add `flex: 1 1 0; min-width: 0` (plus prefixes) on `.extra-info-wrapper`, or `flex-shrink: 0` on `.title` and `.panel`.
- **Evidence:** reasoned. The repro page above shows it if opened in a browser.

### 2. Minor: small-action edit/delete buttons no longer sit at the right edge
- **Location:** `app/assets/stylesheets/common/base/topic-post.scss:264-265,280`
- **Claim:** `.small-action-desc` used to be a full-width block (755px on desktop), so `button { float: right }` (line ~308) placed edit/delete at the far right. As a flex item with no `flex-grow`, the desc is now only as wide as its content. The buttons now sit right next to the "CLOSED 2 DAYS AGO" text.
- **Fix:** `flex: 1` on `.small-action-desc`.
- **Evidence:** reasoned. The template is `templates/components/small-action.hbs`.

### 3. Minor: mobile small-action rules written for the old float layout are now wrong
- **Location:** `app/assets/stylesheets/mobile/topic-post.scss:521,530-532`, not touched by the patch but broken by the change at `common/base/topic-post.scss:280`
- **`.custom-message { margin-left: -40px }`:** this offset was sized for the old `padding-left: 4em` with a floated icon. Now the desc starts right after the 45px icon with only `0 1.5%` padding. The custom message is pulled about 40px back over the icon, which is vertically centred next to it, so the text overlaps the icon.
- **`.small-action.time-gap .topic-avatar { margin-top: -5px }`:** this came from the base commit 98fa098e ("fix up mobile alignment on time gaps"). With `align-items: center` it now pushes the clock icon 5px above centre.
- **Evidence:** reasoned.

### 4. Minor: the new mixins produce invalid or incomplete legacy output
- **Location:** `app/assets/stylesheets/common/foundation/mixins.scss:117-131`
- `-ms-align-items` (line 121) is not a real property and is dead output.
- `align-items` has no `-moz-box-align`, although `flexbox()` emits `display: -moz-box`. On the Firefox versions that only support the old box model, items stretch instead of centring.
- The mixins pass values straight through to the legacy properties:
  - `-webkit-box-align` and `-ms-flex-align` take `start`/`end`, not `flex-start`/`flex-end`.
  - `-webkit-box-ordinal-group` must be 1 or more, so `order(0)` or a negative value is invalid there.
  - The current call sites (`center`, `baseline`, `2`, `3`) are fine. Any future `align-items(flex-start)` or `order(0)` call will silently produce invalid legacy CSS.
- In the old box model (`display:-webkit-box`, Android ≤4.3 stock browser, iOS ≤6), auto margins are not honoured. `margin-left: auto` on `.panel` (`header.scss:37`) will not right-align the header icons there, and the patch removed the `float: right` fallback. This is reasoned and only matters if those browsers are still supported.

## Not issues
- The `badges.css.scss` change only adds vendor prefixes. The modern output is still `inline-flex` / `align-items: baseline`.
- The `clearfix` `::before`/`::after` on `.contents` become zero-size flex items, which does no harm.
- Removing `&.bullet { margin-top: 5px }` from `.extra-info-wrapper` matches the switch to centre alignment.

I did not run any SCSS compile or browser rendering; the sandbox blocked both, so every layout claim is reasoned. Finding 1 is the only one I'd block the merge on.
