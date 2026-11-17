# Run a verifier from another model family on the pool

Status: needs-info

Experiment 005 used two Claude models as verifiers. The three Claude-written sources scored the highest truth precision, which is what a family bias would look like. The pool in `pool/` is kept so a GPT or Gemini verifier can check the same 1,109 issues.

Needs an API key for the outside model and a small read-only harness for it (`verify.py --cli codex` now drives Codex; see `validation/README.md`). Waiting on: an outside team to run `validation/README.md`.
