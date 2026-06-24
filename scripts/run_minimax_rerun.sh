#!/usr/bin/env bash
# Stochasticity re-run of the 4 minimax-m3 factorial cells.
#   model minimax-anthropic:MiniMax-M3
#   paradigm {static,agentic} x tools {none,tools}, full TESTSET (514 q each)
# Writes to a SEPARATE base dir via --out-dir so the existing final results in
# outputs/factorial/<cell>/results.sqlite are never read-for-write or touched.
set -uo pipefail
cd /home/sylvain/code/tum/cobbie
M=minimax-anthropic:MiniMax-M3
QS=full
OUTDIR=outputs/factorial_rerun_20260624
ts() { date +%Y-%m-%dT%H:%M:%S; }
mkdir -p "$OUTDIR/_logs"
LOG="$OUTDIR/_logs/minimax_rerun_$(date +%Y%m%dT%H%M%S).log"
echo "[$(ts)] START minimax-m3 stochasticity re-run (4 cells x 514 q) -> $OUTDIR" | tee -a "$LOG"
for PARADIGM in static agentic; do
  for TOOLS in none tools; do
    echo "[$(ts)] === START $M paradigm=$PARADIGM tools=$TOOLS ===" | tee -a "$LOG"
    uv run python scripts/run_cell.py --model "$M" --paradigm "$PARADIGM" --tools "$TOOLS" --question-set "$QS" --out-dir "$OUTDIR" 2>&1 | tee -a "$LOG"
    echo "[$(ts)] === END $M paradigm=$PARADIGM tools=$TOOLS rc=${PIPESTATUS[0]} ===" | tee -a "$LOG"
  done
done
echo "[$(ts)] ALL MINIMAX RERUN CELLS COMPLETE" | tee -a "$LOG"
