# Test a one-issue-per-comment format

Status: wontfix

Experiment 001 showed the benchmark's extraction step makes 1.33 candidates per finding at k=3 under Opus and 1.91 under Sonnet. Each comment we send is `[Severity] claim` followed by the evidence, and the evidence is split into extra candidates that count as false positives.

Hypothesis: sending the claim only, one issue per comment, raises precision with no loss of recall. If extraction gave one candidate per finding, k=3 would score about F1 47 under Opus.

This needs its own pre-registration. It is a change to how the review is written, and it is partly a fit to this judge's behaviour, so the write-up must say so. Cost: judge calls only, about 20 USD.

## Answer

Tested in experiment 002 and rejected. Claim-only comments score the same as claim plus evidence. The extra candidates come from compound claims, not from the evidence. See `docs/experiments/002-comment-format.md`; the follow-up is issue 02.
