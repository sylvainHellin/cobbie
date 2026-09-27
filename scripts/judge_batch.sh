#!/usr/bin/env bash
# Multi-cell batch judge driver wrapper (milestone 4).
#
# Resume-safety: this is ALWAYS safe to relaunch. The driver reads the same state
# file judge.py uses ($JUDGE_BASE_DIR/judge_batch_jobs.json). On --phase all it
# submits a Gemini Batch job only for cells with no uncollected job, then polls
# and collects every uncollected job. Already-classified rows are skipped and
# collected jobs are never re-polled, so re-running picks up exactly where it left
# off. Pass --dry-run first to preview what would be submitted.
#
# Base dir: set JUDGE_BASE_DIR to judge a non-default factorial out-dir. It
# defaults to outputs/factorial (unchanged behaviour). The logs, batch-state file
# and summary all live under the chosen base dir so concurrent judging of
# different out-dirs never collides.
#
# Usage:
#   scripts/judge_batch.sh [--cells all] [--phase all] [--dry-run] ...
#   JUDGE_BASE_DIR=outputs/factorial_thinking_20260625 scripts/judge_batch.sh --cells all --phase all
set -uo pipefail
cd /home/sylvain/code/tum/_archiv/cobbie
BASE_DIR="${JUDGE_BASE_DIR:-outputs/factorial}"
mkdir -p "$BASE_DIR/_logs"
LOG="$BASE_DIR/_logs/judge_batch_$(date +%Y%m%dT%H%M%S).log"
exec uv run python -u scripts/judge_batch.py --base-dir "$BASE_DIR" "$@" 2>&1 | tee -a "$LOG"
