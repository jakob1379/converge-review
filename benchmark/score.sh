#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
TOOL=${TOOL:-converge-review}
python3 -I bench.py ingest --tool "$TOOL" --min-seats "${MIN_SEATS:-0}" "$@"

cd vendor/code-review-benchmark/offline
if [ -z "${MARTIAN:-}" ]; then
  python3 -I ../../../judge_proxy.py 2>>../../../judge_proxy.log &
  proxy=$!
  trap 'kill $proxy' EXIT
  until curl -s -o /dev/null localhost:${JUDGE_PORT:-8787}; do sleep 0.2; done
  export MARTIAN_BASE_URL=http://127.0.0.1:${JUDGE_PORT:-8787}/v1 MARTIAN_API_KEY=local
  JUDGES=${JUDGES:-"anthropic/claude-opus-4-5-20251101 anthropic/claude-sonnet-4-5-20250929"}
fi
JUDGES=${JUDGES:-"anthropic/claude-opus-4-5-20251101 anthropic/claude-sonnet-4-5-20250929 openai/gpt-5.2"}
for m in $JUDGES; do
  export MARTIAN_MODEL=$m
  dir=results/${m//\//_}
  echo "== judge $m"
  uv run python -m code_review_benchmark.step2_extract_comments --tool "$TOOL"
  python3 -I -c 'import json,sys; t=sys.argv[2]; want=sum(any(r["tool"]==t and r["review_comments"] for r in e["reviews"]) for e in json.load(open("results/benchmark_data.json")).values()); n=sum(t in v for v in json.load(open(sys.argv[1])).values()); sys.exit(f"extraction covered {n}/{want} PRs; see the errors above" if n < want else 0)' "$dir/candidates.json" "$TOOL"
  uv run python -m code_review_benchmark.step2_5_dedup_candidates --tool "$TOOL"
  uv run python -m code_review_benchmark.step3_judge_comments --tool "$TOOL" --dedup-groups "$dir/dedup_groups.json"
done
uv run python analysis/benchmark_dashboard.py
echo "open $(pwd)/analysis/benchmark_dashboard.html"
