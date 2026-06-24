#!/usr/bin/env bash
# Multi-cell batch judge driver wrapper (milestone 4).
#
# Resume-safety: this is ALWAYS safe to relaunch. The driver reads the same state
# file judge.py uses (outputs/factorial/judge_batch_jobs.json). On --phase all it
# submits a Gemini Batch job only for cells with no uncollected job, then polls
# and collects every uncollected job. Already-classified rows are skipped and
# collected jobs are never re-polled, so re-running picks up exactly where it left
# off. Pass --dry-run first to preview what would be submitted.
#
# Usage: scripts/judge_batch.sh [--cells all] [--phase all] [--dry-run] ...
set -uo pipefail
cd /home/sylvain/code/tum/cobbie
mkdir -p outputs/factorial/_logs
LOG=outputs/factorial/_logs/judge_batch_$(date +%Y%m%dT%H%M%S).log
exec uv run python -u scripts/judge_batch.py "$@" 2>&1 | tee -a "$LOG"
