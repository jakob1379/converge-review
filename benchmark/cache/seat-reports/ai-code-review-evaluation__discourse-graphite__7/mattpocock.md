Code review: d38c4d5f74 against base 7554b5e3c4, following mattpocock-skills:code-review. I did both axes myself, with no sub-agents.

There was no spec, so I used the commit message as the stated intent: "scale-color $lightness must use $secondary for dark themes". That means light-theme output should not change, and dark themes should derive these colours from `$secondary`.

I checked it mechanically. A script parsed all 115 `-`/`+` line pairs across the 32 files. Every removed line is `scale-color($primary, $lightness: X%)`. Every added line is `dark-light-choose(scale-color($primary, $lightness: Y%), scale-color($secondary, $lightness: Z%))`, with Y+Z=100 in every case. `dark-light-choose` already exists at base (`common/foundation/variables.scss:46`) and is in scope for every touched file, `embed.css.scss` included, since it imports variables. In 110 pairs Y equals the original X, so the light theme is unchanged. In 5 pairs it is not.

## Spec (commit-message intent)

**1. Important: the light-theme colour changes in 5 places, which the change was not meant to do.** In each of these the first argument (the light-theme branch) differs from the original value. The light theme is the default, so this is a visible change on stock installs, outside the commit's stated scope.
- `app/assets/stylesheets/desktop/topic-post.scss:291` (`.topic-meta-data h5 a`): 30% becomes 70%. Bold author-link text goes from dark grey to pale grey on default themes.
- `app/assets/stylesheets/desktop/user.scss:522` (`.group-member-info .name`): 30% becomes 50%.
- `app/assets/stylesheets/mobile/user.scss:497` (`.group-member-info .name`): 30% becomes 50%.
- `app/assets/stylesheets/mobile/topic-post.scss:182` (`h3`): 20% becomes 50%.
- `app/assets/stylesheets/mobile/modal.scss:102` (`.custom-message-length`): 70% becomes 30%. The two values are swapped: the desktop twin at `desktop/modal.scss:94` is correctly `(70%, 30%)`, while mobile is now `(30%, 70%)`. Light-mobile text gets darker and dark-mobile text gets lighter, the reverse of every other rule.

Evidence: `git diff -U0 7554b5e3c4 HEAD -- app/assets/stylesheets/mobile/modal.scss` shows `- color: scale-color($primary, $lightness: 70%);` replaced by `+ color: dark-light-choose(scale-color($primary, $lightness: 30%), ...)`. The other four show the same in their own diffs. There is no sass compiler on the box and I installed none, so I have no rendered-CSS failing test. The claim rests on the diff text plus the pairwise script described above.

**2. Minor: the conversion is incomplete in a file the patch touches.** `app/assets/stylesheets/common/base/_topic-list.scss:115` (`.topic-list.categories .category .badge-notification`) still has bare `color: scale-color($primary, $lightness: 50%);`, which is the exact pattern the commit says must use `$secondary`. On dark themes that badge will be near-white while its neighbours are mid-grey. A repo-wide `git grep -nE 'scale-color\(\s*\$primary\s*,\s*\$lightness:\s*[0-9]' -- app/assets plugins | grep -v dark-light-choose` finds only this line and a comment at `common/base/discourse.scss:73`. That comment describes the old default and is now stale (Minor).

There is no scope creep beyond finding 1.

## Standards

Sources: `CONTRIBUTING.md` (sections 3 and 4) plus the smell baseline. There is no scss-lint config and no CODING_STANDARDS file.
- **No hard breaches.** No tabs or trailing whitespace were added. The new lines follow the existing `dark-light-choose` usage, which meets "Adhere to common conventions you see in the existing code". The `{color: ...;}` brace spacing in single-line rules was already there before the patch, so it is not introduced here.
- **Possible Duplicated Code / Shotgun Surgery (judgement call):** the same `dark-light-choose(scale-color($primary, $lightness: X%), scale-color($secondary, $lightness: (100-X)%))` shape is pasted 115 times across 32 files. A one-argument helper next to `dark-light-diff` in `variables.scss` would have made the 5 errors in Spec finding 1 impossible. I did not ask for this, so it is advisory only.

## Summary

Standards: 0 hard breaches, 1 smell. The worst is the 115-way copy-paste of the same expression. Spec: 2 findings. The worst is Important finding 1, the light-theme regressions in 5 rules, including the swapped `mobile/modal.scss:102`.

Files not reviewed: none. All 32 files in the patch were covered by the line-by-line script, with manual context reads at the 5 flagged sites, `_topic-list.scss` and `embed.css.scss`. Not checked: the compiled CSS output and actual rendered contrast, since no sass compiler is available. I also did not check whether the 100−X value for dark themes is visually right per rule. It follows the existing convention, but nobody has looked at it on screen.
