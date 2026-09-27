#!/usr/bin/env bash
# Deconfound run: extended-thinking re-run of the 4 minimax-m3 factorial cells
# at temperature=0 (NOT 1). Isolates the thinking effect from the temperature
# confound present in outputs/factorial_thinking_20260625 (thinking + temp=1).
#   model minimax-anthropic:MiniMax-M3
#   paradigm {static,agentic} x tools {none,tools}, full TESTSET (514 q each)
#   thinking=adaptive (MiniMax-M3 "thinking on"), temperature=0
# Writes to a SEPARATE base dir via --out-dir; outputs/factorial/<cell> is never touched.
set -uo pipefail
cd /home/sylvain/code/tum/_archiv/cobbie
M=minimax-anthropic:MiniMax-M3
QS=full
OUTDIR=outputs/factorial_thinking_temp0_20260626
ts() { date +%Y-%m-%dT%H:%M:%S; }
mkdir -p "$OUTDIR/_logs"
LOG="$OUTDIR/_logs/minimax_thinking_temp0_rerun_$(date +%Y%m%dT%H%M%S).log"
echo "[$(ts)] START minimax-m3 thinking@temp0 re-run (4 cells x 514 q) -> $OUTDIR" | tee -a "$LOG"
for PARADIGM in static agentic; do
  for TOOLS in none tools; do
    echo "[$(ts)] === START $M paradigm=$PARADIGM tools=$TOOLS ===" | tee -a "$LOG"
    uv run python scripts/run_cell.py --model "$M" --paradigm "$PARADIGM" --tools "$TOOLS" --question-set "$QS" --out-dir "$OUTDIR" --thinking adaptive --temperature 0 --concurrency 3 2>&1 | tee -a "$LOG"
    echo "[$(ts)] === END $M paradigm=$PARADIGM tools=$TOOLS rc=${PIPESTATUS[0]} ===" | tee -a "$LOG"
  done
done
echo "[$(ts)] ALL MINIMAX THINKING@TEMP0 RERUN CELLS COMPLETE" | tee -a "$LOG"
