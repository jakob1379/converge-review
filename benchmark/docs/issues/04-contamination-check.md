# Check for training-data contamination

Status: ready-for-agent

Compare each PR merge date with the training cutoff of the review model and of the judges. Search the seat reports for near-verbatim copies of golden comments. Report results split before and after the cutoff if any PR falls after it. Write the outcome into docs/findings.md.
