What this change does: The patch touches 32 SCSS files and replaces 115 lines. Each `scale-color($primary, $lightness: X%)` becomes `dark-light-choose(scale-color($primary, $lightness: X%), scale-color($secondary, $lightness: (100-X)%))`, so muted greys and borders are based on the background color when the theme is dark. `dark-light-choose` already existed in `app/assets/stylesheets/common/foundation/variables.scss:46` and is already used in `code_highlighting.scss`. The patch adds no new abstraction, option or dependency.

Over-engineering: none. The patch has the opposite problem: the same formula is copied 115 times when one small helper would do.

**Should fix**

1. **The same two-part formula is copied 115 times, and the parts have to change together** (`app/assets/stylesheets/common/admin/admin_base.scss:385`, `:506`, `:524`, `:577`, `:600`, plus 110 similar lines in the other 31 files; the helper would go next to `app/assets/stylesheets/common/foundation/variables.scss:46`)
   - **What this is:** Every changed line gives the light-theme value and the dark-theme value separately, but the dark value is always computed from the light one. I checked all 115 added lines with a script: in each one the `$secondary` lightness is exactly 100 minus the `$primary` lightness (50→50, 70→30, 40→60, 80→20, 75→25, and so on). There are no exceptions.
   - **Problem:** That rule is never written down. It exists only as 115 hand-copied pairs. A later edit that changes one number and not the other (for example 40% with 40% instead of 60%) still compiles and silently gives the wrong grey in dark themes. Each line is also about 100 characters, which is hard to read.
   - **Fix:** Add one function next to `dark-light-choose` in `variables.scss`, such as `@function primary-faded($pct) { @return dark-light-choose(scale-color($primary, $lightness: $pct), scale-color($secondary, $lightness: 100% - $pct)); }`. Then each call site becomes `color: primary-faded(50%);`. This matches what the repo already does with `dark-light-diff` (`variables.scss:39`) and with commit 54c0bea294 ("Create a mixin to DRY things up"). It is about 4 added lines, and the 115 call sites get much shorter.
   - **If we skip it:** It works today. But every later tweak to the dark-theme greys means editing two numbers per line in 32 files, and a mismatch will not show up until someone looks at a dark theme.

**Nice to have**

2. **One place was missed, and the commit message says it "must" be covered** (`app/assets/stylesheets/common/base/_topic-list.scss:115`)
   - **What this is:** `.topic-list.categories .category .badge-notification` still has a plain `color: scale-color($primary, $lightness: 50%);`. It is the only remaining `scale-color($primary…)` in `app/assets/stylesheets` that is not wrapped. The other match, `discourse.scss:73`, is just a comment.
   - **Problem:** In a dark theme this badge is lightened from the light text color, unlike every other muted grey the patch changed. The commit message says "must use $secondary for dark themes", so this is a gap against the change's stated goal.
   - **Fix:** Wrap it the same way (`primary-faded(50%)` if finding 1 is taken). One line.
   - **If we skip it:** One badge on the categories page looks different from the rest in dark themes. This is cosmetic only.

Verdict: Ship. Nothing is broken. Finding 1 is a maintenance cleanup, not a blocker.
Lean: each of the 115 call sites gets about 70 characters shorter, for about 4 added helper lines (-0 net lines, since each site stays one line).

What I checked and did not check: `dark-light-choose` is defined before every file that uses it, including `embed.css.scss`, which imports `foundation/variables` directly. I did not compile the SCSS or render a dark theme, and I did not judge whether the 100-minus-X mirror gives good contrast; that is a visual design call, not an over-engineering one. Every file in the patch was reviewed. Since the change is the same mechanical substitution in all 32 files, I verified it across all of them with grep and perl rather than reading each file by hand.
