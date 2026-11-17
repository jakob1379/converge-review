## Ponytail review: over-engineering only, patch 98fa098e6f → 5b229316ee

**What this change does:** It turns the site header (`.contents`) and the small-action post rows (`.small-action`) from float layouts into flexbox. It also adds four Sass mixins to `mixins.scss` (`flexbox`, `inline-flex`, `align-items`, `order`). These mixins write out the old vendor-prefixed versions of each flex property. Vendor prefixes are browser-specific copies of a CSS property, such as `-webkit-flex`.

**Load assumed:** This is static CSS for every Discourse page. The only constraint that matters is the browser support table in `README.md:40-47`: Safari 5.1+, Chrome 23+, IE10+, Firefox 16+, Android 4.1+.

**The prefix mixins are justified, so they are not a finding.** I first suspected them as bloat. The Gemfile has no autoprefixer (a tool that adds prefixes automatically), and the existing mixins (`border-radius-all`, `box-shadow`) write only plain CSS. But the README targets Safari 5.1 and Android 4.1, which need `-webkit-box`, plus IE10 (`-ms-flexbox`) and Firefox 16–19 (`-moz-box`). Given that list, writing the prefixes by hand in one mixin is the smallest correct option. The same reason covers swapping the plain `inline-flex` in `badges.css.scss` for the mixin.

### Should fix

1. **The `order` mixin and both `order` calls can go** (`common/base/topic.scss:30`, `common/base/header.scss:39`, `common/foundation/mixins.scss:125-131`). Severity: Minor.
   - **What this is:** In `header.hbs` the children come in this order: `.title` (line 4), `.panel` (line 6), `.extra-info-wrapper` (line 94). The CSS uses `order(2)` and `order(3)` to show the extra info before the panel.
   - **Problem:** Two calls plus a 7-line mixin do what moving the `{{#if showExtraInfo}}{{header-extra-info}}{{/if}}` block above `<div class='panel'>` in `header.hbs` would do. Changing visual order with `order` also leaves keyboard Tab order different from screen order. Even keeping CSS ordering, `order(2)` on `.extra-info-wrapper` is redundant: with only `.panel` ordered, the extra info already follows the title in source order.
   - **Fix:** Move the block in the template, then delete both `@include order(...)` lines and the `order` mixin. The smallest version keeps the panel's include and deletes only `topic.scss:30`.
   - **If we skip it:** About 10 extra lines, and the visual order and DOM order stay different for good.
   - Evidence: reasoned, from the DOM order in `app/assets/javascripts/discourse/templates/header.hbs` lines 4, 6 and 92-94. `home-logo.js.es6` sets `classNames: ["title"]`.

### Nice to have

2. **`-ms-align-items` is not a real CSS property** (`common/foundation/mixins.scss:121`). Severity: Minor.
   - **Problem:** IE10 reads `-ms-flex-align`, which is already on the line above. No browser reads `-ms-align-items`.
   - **Fix:** Delete the line.

3. **A float is now dead on a flex item** (`common/base/topic-post.scss:270`). Severity: Minor.
   - **Problem:** `.small-action .topic-avatar { float: left }`. Now that `.small-action` is a flex container, `.topic-avatar` is a flex item, and CSS ignores `float` on flex items.
   - **Fix:** Delete `float: left;` here.

4. **A mobile override is now dead** (`app/assets/stylesheets/mobile/topic-post.scss:516-519`, not in the patch). Severity: Minor.
   - **Problem:** `.small-action .small-action-desc p { padding-top: 0 }` existed only to cancel the base `> p { padding-top: 4px }`. The patch deleted that base rule, so the override now does nothing.
   - **Fix:** Delete the `p { padding-top: 0; }` block.

5. **The `clearfix` class on `.contents` is now dead weight** (`header.hbs:2`, not in the patch). Severity: Minor.
   - **Problem:** A flex container already contains its children, so clearfix is no longer needed. Its `::before` and `::after` (empty `display: table` boxes) now become stray empty flex items.
   - **Fix:** Remove `clearfix` from `<div class='contents clearfix'>`.

Verdict: No Critical or Important over-engineering. The mixins are justified by the documented browser support. Ship after the small deletions, or ship as is.
Lean: about -15 lines possible (findings 1–5).

**Outside my scope (over-engineering only), noticed but not judged:** `mobile/topic-post.scss:521` `.custom-message { margin-left: -40px }` offset the old `4em` left padding. The patch changed that padding to `0 1.5%`, so on mobile the custom message probably now overhangs the left edge. Also, in the 2009 `-webkit-box` model (Safari 5.1, Android 4.x), `margin-left: auto` on `.panel` may not push it to the right. I did not verify either one in a browser.

**Files not reviewed:** none. I reviewed all 5 files in the patch: `header.scss`, `topic-post.scss`, `topic.scss`, `badges.css.scss`, `mixins.scss`. Nothing was compiled or run; I can't build or render the CSS here. I could not inspect older commits (partial clone, fetch blocked), so I relied on the files at HEAD and the README.
