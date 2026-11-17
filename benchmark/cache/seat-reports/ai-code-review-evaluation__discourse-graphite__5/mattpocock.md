## Code review: `98fa098e6f..5b229316ee` ("adding flexbox to header via mixins (all prefixes)")

I ran `mattpocock-skills:code-review` without sub-agents, as you asked; the skill would normally spawn them. There is no spec, so the commit message stands in for one. The standards sources are `CONTRIBUTING.md` (the "Coding Conventions" and "Commit" sections) and `.editorconfig` (2-space indent, trim trailing whitespace). I found no `.scss-lint.yml` or other style tooling for SCSS.

I reviewed all five files in the patch. None were skipped:
- `app/assets/stylesheets/common/base/header.scss`
- `app/assets/stylesheets/common/base/topic-post.scss`
- `app/assets/stylesheets/common/base/topic.scss`
- `app/assets/stylesheets/common/components/badges.css.scss`
- `app/assets/stylesheets/common/foundation/mixins.scss`

I checked that the change compiles in context by reading the imports. `common.scss` imports `foundation/mixins` before `components/*` and `base/*`, so every `@include` resolves. I did not compile anything or render it in a browser.

## Standards

1. **`app/assets/stylesheets/common/foundation/mixins.scss:120`: Minor (hard violation).** There is trailing whitespace after `-ms-flex-align: $alignment;`.
   - Breaks `CONTRIBUTING.md` §4 ("no trailing whitespaces") and `.editorconfig` (`trim_trailing_whitespace = true`).
   - To reproduce: `grep -nE ' +$' app/assets/stylesheets/common/foundation/mixins.scss` prints line 120.

2. **`mixins.scss:122`: Minor (hard violation).** `align-items:$alignment;` has no space after the colon.
   - Breaks `CONTRIBUTING.md` §4 ("use spaces … after … colons"). Every other declaration in the patch has the space.

3. **`mixins.scss:117-123`: Minor (hard violation).** The `align-items` mixin body is indented 4 spaces, while the other three new mixins use 2.
   - Breaks `CONTRIBUTING.md` §4 ("two spaces") and `.editorconfig` `indent_size = 2`.
   - Mitigation: the older `clearfix` mixin in the same file (lines 38-47) already uses 4 spaces.

4. **Commit `5b229316ee`: Minor (hard violation).** The commit message is a summary line only, with no body.
   - `CONTRIBUTING.md` §5 asks for a summary "followed with a blank line and then more detailed descriptions of the change."
   - Here that matters: the commit also changes small-action spacing and badge margins, and the message gives no reason (see Spec 1).

5. **Baseline smell (judgement call): possible Speculative Generality / dead declaration at `mixins.scss:121`.** `-ms-align-items` is not a property that any IE or Edge version ever shipped; IE10 used `-ms-flex-align`, which is already on line 120. The line has no effect. This is reasoned from vendor property tables, not from a test.

No other baseline smells worth reporting. The mixins are used at 6 call sites across 4 files, so the extraction is justified.

## Spec (commit message only)

1. **`app/assets/stylesheets/common/base/topic-post.scss:263-265, 280, 292, 303`: Important (scope creep).**
   - The commit message promises "adding flexbox to header", but this hunk turns `.small-action` (post-stream action rows, not the header) into a flex container.
   - It also rewrites spacing: `padding: 0.5em 0 0.5em 4em; margin-top: 5px` becomes `padding: 0 1.5%`, and it removes the `p` margins and `padding-top: 4px`.
   - That is an unrelated layout change and breaks `CONTRIBUTING.md` §2 ("one feature or bug-fix per branch … fix it in a separated branch").
   - It also interacts with untouched overrides: `mobile/topic-post.scss:516-532` keeps `.custom-message { margin-left: -40px }` and `.time-gap .topic-avatar { margin-top: -5px }`, which were tuned for the old 4em padding.
   - Reasoned from reading the code; I did not render it to confirm visual breakage.

2. **`mixins.scss:116-123`: Minor (incomplete "all prefixes").**
   - `flexbox()` and `order()` emit the `-moz-box` model (`display: -moz-box`, `-moz-box-ordinal-group`), but `align-items()` has no `-moz-box-align`. On old Firefox (the `-moz-box` era), `.contents` would become a box with no vertical centring.
   - So "all prefixes" is only partly true, and one prefix that is emitted (`-ms-align-items`) is fake (Standards 5).

3. **`app/assets/stylesheets/common/base/header.scss:14-19`: Minor (side effect not handled).**
   - `.contents` still carries `clearfix` (`templates/header.hbs:2`), whose `:before`/`:after` (`display: table; content: " "`, `foundation/helpers.scss:53-62`) become flex items once `.contents` is a flex container.
   - They take zero width here because `.panel` uses `margin-left: auto` rather than `justify-content`, so the effect is harmless today. But the clearfix is now dead weight and a trap for anyone who later adds `justify-content: space-between`.
   - Reasoned, not tested.

4. **`app/assets/stylesheets/common/components/badges.css.scss:55-57`: no finding.** Swapping the hard-coded `inline-flex`/`align-items: baseline` for the mixins adds prefixes and changes nothing else. The odd blank lines between the two `@include`s are cosmetic; no documented standard covers them.

The header changes themselves do what the message says. They remove the `.title` and `.panel` floats, flex `.contents` with vertical centring, and order the children as logo, then `.extra-info-wrapper` (`order(2)`, `topic.scss:30`), then `.panel` (`order(3)`) pushed right with `margin-left: auto`. In the template the panel comes before the extra info, so the explicit ordering is needed. That part is correct.

## Summary

- **Standards: 5 findings.** The worst are trailing whitespace and a missing space after a colon in `mixins.scss`, both breaching `CONTRIBUTING.md` §4.
- **Spec: 3 findings.** The worst is the unrelated `.small-action` re-layout in `topic-post.scss`, which is outside the "header" scope and leaves the mobile overrides tuned for the old padding.

I didn't compile the SCSS or check anything in a browser, so every visual claim above is reasoned from the code, not tested. The biggest risk is the `.small-action` spacing regression on mobile.
