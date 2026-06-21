#!/usr/bin/env bash
# Full TESTSET factorial run for the 8 new GLM cells:
#   2 models x (paradigm {static,agentic} x tools {none,tools})
# The cell runner (scripts/run_cell.py) is resume-safe: already-done rows are
# skipped and prior status='error' rows are retried, so re-running simply
# completes the remaining questions per cell.
set -uo pipefail
cd /home/sylvain/code/tum/cobbie
QS=full
ts() { date +%Y-%m-%dT%H:%M:%S; }
mkdir -p outputs/factorial/_logs
LOG=outputs/factorial/_logs/glm_factorial_$(date +%Y%m%dT%H%M%S).log
echo "[$(ts)] START GLM full factorial (8 cells x 514 q)" | tee -a "$LOG"
for M in glm:glm-5.2 glm:glm-4.5-air; do
  for PARADIGM in static agentic; do
    for TOOLS in none tools; do
      echo "[$(ts)] === START $M paradigm=$PARADIGM tools=$TOOLS ===" | tee -a "$LOG"
      uv run python scripts/run_cell.py --model "$M" --paradigm "$PARADIGM" --tools "$TOOLS" --question-set "$QS" 2>&1 | tee -a "$LOG"
      echo "[$(ts)] === END $M paradigm=$PARADIGM tools=$TOOLS rc=${PIPESTATUS[0]} ===" | tee -a "$LOG"
    done
  done
done
echo "[$(ts)] ALL GLM CELLS COMPLETE" | tee -a "$LOG"
