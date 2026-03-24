#!/usr/bin/env bash
#
# Run ACC training in batches to avoid memory accumulation from ifcopenshell C++ objects.
# Each batch runs as a separate process, so memory is fully reclaimed between batches.
#
# Usage:
#   bash scripts/run_acc_training_batched.sh --nb-samples 20
#   bash scripts/run_acc_training_batched.sh --nb-samples 20 --batch-size 1  
#   bash scripts/run_acc_training_batched.sh --nb-samples 20 --start 5 --batch-size 3
#   bash scripts/run_acc_training_batched.sh --nb-samples 20 --no-geometry
#
#   # Continue an existing run (skips the first-question step):
#   bash scripts/run_acc_training_batched.sh --nb-samples 20 --batch-size 1 --start 11 --continue 7ca5817aba3e40879b3205398d958102
#
# Without --continue: first batch = 1 rule (creates MLflow run), then prompts for run ID.
# With --continue: all rules run in batches against the provided run ID.

set -euo pipefail

# -- defaults --
start=0
nb_samples=10
batch_size=5
run_id=""
extra_args=()

# -- parse arguments --
while [[ $# -gt 0 ]]; do
    case "$1" in
        --start)
            start="$2"; shift 2 ;;
        --nb-samples)
            nb_samples="$2"; shift 2 ;;
        --batch-size)
            batch_size="$2"; shift 2 ;;
        --continue)
            run_id="$2"; shift 2 ;;
        --end)
            echo "Error: --end is not supported. Use --nb-samples instead."
            echo "  --end conflicts with the batching logic (which computes --end internally)."
            echo "  Example: bash scripts/run_acc_training_batched.sh --start 0 --nb-samples 20"
            exit 1 ;;
        *)
            extra_args+=("$1"); shift ;;
    esac
done

# -- clamp to available rules --
total_rules=$(python -c "from src.acc.guid_comparison import load_rule_templates; print(len(load_rule_templates()))")
total_end=$(( start + nb_samples ))
if [[ $total_end -gt $total_rules ]]; then
    total_end=$total_rules
    echo "  Note: clamped to ${total_rules} available rules"
fi

echo "======================================================="
echo "  Batched ACC training: rules ${start}..$(( total_end - 1 ))"
echo "  Batch size: ${batch_size}"
if [[ -n "$run_id" ]]; then
    echo "  Continuing run: ${run_id}"
else
    echo "  First batch: 1 (to create MLflow run)"
fi
if [[ ${#extra_args[@]} -gt 0 ]]; then
    echo "  Extra args: ${extra_args[*]}"
fi
echo "======================================================="

cursor=$start

# -- if no run_id, run first rule to create the MLflow run --
if [[ -z "$run_id" ]]; then
    echo ""
    echo "> Running first rule (index ${start}) to create MLflow run..."
    output=$(python scripts/run_acc_training_phase.py --start "$start" --end $(( start + 1 )) "${extra_args[@]}")
    run_id=$(echo "$output" | grep '^MLFLOW_RUN_ID=' | cut -d= -f2)

    if [[ -z "$run_id" ]]; then
        echo "Error: Could not extract MLflow run ID from first batch output."
        exit 1
    fi
    echo "  Captured run ID: ${run_id}"

    cursor=$(( start + 1 ))
fi

# -- remaining batches --
while [[ $cursor -lt $total_end ]]; do
    remaining=$(( total_end - cursor ))
    current_batch=$(( batch_size < remaining ? batch_size : remaining ))

    echo ""
    echo "> Batch: rules ${cursor}..$(( cursor + current_batch - 1 )) (${current_batch} rules)"
    python scripts/run_acc_training_phase.py --start "$cursor" --end $(( cursor + current_batch )) --continue "$run_id" "${extra_args[@]}"

    if [[ $? -ne 0 ]]; then
        echo "Error: Batch starting at ${cursor} failed."
        echo "  To resume, run:"
        echo "  bash scripts/run_acc_training_batched.sh --start ${cursor} --nb-samples $(( total_end - cursor )) --batch-size ${batch_size} --continue ${run_id} ${extra_args[*]:-}"
        exit 1
    fi

    cursor=$(( cursor + current_batch ))
done

echo ""
echo "======================================================="
echo "  All ${nb_samples} rules completed."
echo "  MLflow run ID: ${run_id}"
echo "======================================================="
