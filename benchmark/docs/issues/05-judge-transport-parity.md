# Measure the effect of judging through the local CLI

Status: needs-triage

The benchmark judges at temperature 0 through an API. We judge through the `claude` CLI, which does not expose temperature. Re-judge one competitor with stored results (for example `claude-code`) through the local proxy under a new tool name and compare with its stored score. Cost: judge calls for one small tool, about 10 USD.
