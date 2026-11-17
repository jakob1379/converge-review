# LinkedIn post: asking for an OpenAI verifier

Image: `converge-review-verified-truth.png`, built by `experiments/005-pooled-truth/chart.py` and `rich-card`.
Not posted yet. It promises a Codex verifier script that does not exist yet (issue 10).

```text
Looking for someone with a Codex subscription to try to break a result of mine.

I built a code-review workflow on Claude Code: four independent reviewers and a merge step. I ran it on the 50 pull requests in Martian's Code Review Bench, next to CodeRabbit, Augment, Claude Code's own review, Cubic and Qodo.

On the benchmark's score it came 21st of 23. It reports about 14 findings per pull request, and the benchmark counts anything outside its 3 or so labelled issues per pull request as wrong.

So I checked the findings instead of the labels. I pooled every tool's comments with the benchmark's own labels, merged duplicates into 1,109 distinct issues, removed the tool names, and had a fresh agent check each one against the source code. 990 held up. The benchmark's labels cover 149 of them.

Measured that way, my workflow finds about 15 real issues per pull request against 3 to 5 for the others, and 96% of its comments are true against 84 to 94%.

The weak spots:
- About 4 in 10 of its true findings are trivial.
- Counting only issues above trivial, its comments are true less often than four of the five other tools. It wins by finding more, not by being more precise.
- The checker was Claude, and so were my reviewers. That is either a real result or a model marking its own homework. I can't tell which from here.

What I need: someone to run the same blind check with an OpenAI model through Codex, on a sample of about 200 issues. I'm packaging it as a repository with a script that reads code and writes one verdict per issue, nothing else. It will use some of your Codex usage limit. I don't know how much yet, and the first run will tell us.

If OpenAI's models disagree with Claude, that is the result I'll report.

Comment or message me if you're up for it.
```
