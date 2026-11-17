## Review: d38c4d5f74 "scale-color $lightness must use $secondary for dark themes"

I used the `superpowers:requesting-code-review` skill and did the review myself, as asked; no subagent was dispatched. There is no spec, so I reviewed against the commit message and the helper the patch uses. That helper is `dark-light-choose($light, $dark)` in `app/assets/stylesheets/common/foundation/variables.scss:46`.

**What the patch should do.** Each `scale-color($primary, $lightness: X%)` becomes `dark-light-choose(scale-color($primary, $lightness: X%), scale-color($secondary, $lightness: (100-X)%))`. This is the right approach. The light branch must stay byte-identical, so light themes don't change. The dark branch uses `100-X` on the dark background color, which gives the same "muted" effect. Default colors are `$primary #222`, `$secondary #fff` (`common/foundation/colors.scss:1-2`).

**How I checked.** A script paired every `-`/`+` line in the patch (115 added lines) and checked `light == X` and `dark == 100-X`. 110 lines are correct. 5 are not, listed below. I also confirmed that no `scale-color($primary` outside `dark-light-choose` is left anywhere under `app/assets/stylesheets`, so coverage is complete.

### Findings

**1. Important: `app/assets/stylesheets/mobile/modal.scss:102`, values swapped in both themes.**
- Original: `scale-color($primary, $lightness: 70%)`.
- New: `dark-light-choose(scale-color($primary, $lightness: 30%), scale-color($secondary, $lightness: 70%))`. It should be `(70%, 30%)`.
- The desktop version of the same rule, `desktop/modal.scss:94` `.custom-message-length`, is converted correctly to `(70, 30)`.
- Effect on light theme: the faint hint goes from `#bdbdbd` to `#646464` (contrast vs white 1.88 → 5.92).
- Effect on dark theme: the hint renders bright `#bdbdbd` on `#222` (8.47:1) instead of muted `#646464` (2.69:1). That is the opposite of what the commit intends.

**2. Important: `app/assets/stylesheets/desktop/topic-post.scss:291`, values swapped (`.topic-meta-data h5 a`).**
- Original: `$lightness: 30%`. New: `(70%, 30%)`. It should be `(30%, 70%)`.
- Effect on light theme: the bold username link goes from `#646464` (5.92:1 vs white) to `#bdbdbd` (1.88:1). That is below WCAG AA and changes a light-theme style in a commit scoped to dark themes.
- Effect on dark theme: the link becomes dim (2.69:1) instead of prominent.

**3. Important: `app/assets/stylesheets/mobile/topic-post.scss:182`, light-theme value changed (`h3` in the topic-map links section).**
- Original: `$lightness: 20%`. New: `(50%, 50%)`. It should be `(20%, 80%)`.
- The desktop version of the same rule, `desktop/topic-post.scss:321`, is converted correctly to `(20, 80)`, so mobile and desktop now differ.
- Effect on light theme: `#4e4e4e` (8.32:1) → `#909090` (3.19:1). The heading fades and fails AA for normal text.

**4. Important: `app/assets/stylesheets/desktop/user.scss:522` and `app/assets/stylesheets/mobile/user.scss:497`, light-theme value changed (`.group-member-info .name`).**
- Original: `$lightness: 30%`. New: `(50%, 50%)`. It should be `(30%, 70%)`.
- The name becomes as light as the `.title` beneath it, so the name/title hierarchy is lost. In light theme it goes `#646464` → `#909090`.
- The same mistake in both files suggests a copy-paste of the `.title` line.

All four findings are reasoned from the source plus a color calculation; there are no SCSS tests in the repo for this. To reproduce the mismatches, run this from the repo root. It prints exactly the 5 bad lines:
```
python3 -I - ../ai-code-review-evaluation__discourse-graphite__7.scratch/change.patch <<'EOF'
import re,sys
f=None;new=0;minus=[]
for l in open(sys.argv[1]).read().splitlines():
    if l.startswith('+++ b/'): f=l[6:];continue
    m=re.match(r'@@ -\d+(?:,\d+)? \+(\d+)',l)
    if m: new=int(m.group(1));minus=[];continue
    if l.startswith('-') and not l.startswith('---'): minus.append(l);continue
    if l.startswith('+'):
        o=minus.pop(0) if minus else ''
        x=int(re.findall(r'primary, \$lightness: (\d+)%',o)[0])
        a,b=map(int,re.search(r'primary, \$lightness: (\d+)%\), scale-color\(\$secondary, \$lightness: (\d+)%',l).groups())
        if a!=x or b!=100-x: print(f"{f}:{new} orig={x} light={a} dark={b}")
        new+=1;continue
    minus=[];new+=1
EOF
```
I computed contrast values with `colorsys` HLS lightness scaling, which is how Sass `scale-color` works, using the default `#222`/`#fff` palette and a `#222` dark background. I did not compile the SCSS, because no sass binary is installed and I did not install one.

**Minor.** `desktop/queued-posts.scss:14`, `desktop/topic-list.scss:39-54` and several `desktop/topic-post.scss` one-liners add a stray space before `}` (`...)); }`). This is cosmetic, but it doesn't match the surrounding style.

### Assessment
Not ready to merge. Five of the 115 converted lines don't follow the patch's own rule. Two are swapped in both themes (findings 1 and 2) and three silently change light-theme colors (findings 3 and 4), in a commit that claims to touch only dark themes. Finding 2 drops a light-theme link below WCAG AA contrast. Each fix is a one-number edit.

### Files not reviewed
None. All 32 files in the patch were read and every changed line was checked by the script.

I did not check visually in a real dark theme, and the contrast numbers assume the default palette; custom color schemes will differ.
