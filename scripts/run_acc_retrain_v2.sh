#!/usr/bin/env bash
#
# Retrain ACC rules affected by ground_truth V2 changes.
#
# Runs 7 rules that had their ground truth modified by the extraction_element
# approach. Each rule runs as a separate process for memory isolation.
#
# Usage:
#   bash scripts/run_acc_retrain_v2.sh
#   bash scripts/run_acc_retrain_v2.sh --continue <RUN_ID>   # resume after failure
#
set -euo pipefail

RULES=(
    305_3_size
    404_2_5_two_doors_in_series
    504_2_stair_slab_connection
    504_2_non_uniform_risers_treads
    504_2_riser_height
    clearance_front_of_doors
    slabs_guarded_against_falling
)

run_id=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --continue)
            run_id="$2"; shift 2 ;;
        *)
            echo "Unknown argument: $1"; exit 1 ;;
    esac
done

echo "======================================================="
echo "  ACC V2 Ground Truth Retraining"
echo "  Rules: ${#RULES[@]}"
if [[ -n "$run_id" ]]; then
    echo "  Continuing run: ${run_id}"
fi
echo "======================================================="

# First rule creates the MLflow run (if not continuing)
if [[ -z "$run_id" ]]; then
    echo ""
    echo "=== Training: ${RULES[0]} (creates MLflow run) ==="
    output=$(uv run scripts/run_acc_training_phase.py --rules "${RULES[0]}")
    run_id=$(echo "$output" | grep '^MLFLOW_RUN_ID=' | cut -d= -f2)

    if [[ -z "$run_id" ]]; then
        echo "Error: Could not extract MLflow run ID from output."
        echo "Check output above and re-run with --continue <RUN_ID>"
        exit 1
    fi
    echo "  Captured run ID: ${run_id}"

    # Remove first rule from remaining
    RULES=("${RULES[@]:1}")
fi

# Remaining rules
for rule in "${RULES[@]}"; do
    echo ""
    echo "=== Training: ${rule} ==="
    uv run scripts/run_acc_training_phase.py --rules "$rule" --continue "$run_id"

    if [[ $? -ne 0 ]]; then
        echo ""
        echo "Error: Training failed for ${rule}."
        echo "  To resume, run:"
        echo "  bash scripts/run_acc_retrain_v2.sh --continue ${run_id}"
        exit 1
    fi
done

echo ""
echo "======================================================="
echo "  All ${#RULES[@]} rules completed."
echo "  MLflow run ID: ${run_id}"
echo "======================================================="
