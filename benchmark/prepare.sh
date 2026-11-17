#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"

PIN=e616e849755441da38f18bf3adba2c9583b03803
V=vendor/code-review-benchmark

[ -d "$V" ] || git clone https://github.com/withmartian/code-review-benchmark.git "$V"
git -C "$V" checkout -q "$PIN"
(cd "$V/offline" && uv sync -q && { [ -f .env ] || cp .env.example .env; })

python3 -I bench.py manifest
python3 -I bench.py repos
python3 -I bench.py run --dry-run --limit 1
