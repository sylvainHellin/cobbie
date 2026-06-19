#!/usr/bin/env bash
set -uo pipefail
cd /home/sylvain/code/tum/cobbie
M=minimax-anthropic:MiniMax-M3
QS=full
ts() { date +%Y-%m-%dT%H:%M:%S; }
mkdir -p outputs/factorial/_logs
LOG=outputs/factorial/_logs/full_factorial_$(date +%Y%m%dT%H%M%S).log
echo "[$(ts)] START full factorial (4 cells x 514 q)" | tee -a "$LOG"
for PARADIGM in static agentic; do
  for TOOLS in none tools; do
    echo "[$(ts)] === cell paradigm=$PARADIGM tools=$TOOLS ===" | tee -a "$LOG"
    uv run python scripts/run_cell.py --model "$M" --paradigm "$PARADIGM" --tools "$TOOLS" --question-set "$QS" 2>&1 | tee -a "$LOG"
    echo "[$(ts)] === done paradigm=$PARADIGM tools=$TOOLS rc=${PIPESTATUS[0]} ===" | tee -a "$LOG"
  done
done
echo "[$(ts)] ALL CELLS COMPLETE" | tee -a "$LOG"
