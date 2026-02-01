#!/usr/bin/env fish
#
# Run training in batches to avoid memory accumulation from ifcopenshell C++ objects.
# Each batch runs as a separate process, so memory is fully reclaimed between batches.
#
# Usage:
#   fish scripts/run_training_batched.fish --nb-samples 20
#   fish scripts/run_training_batched.fish --nb-samples 20 --start 5 --batch-size 3
#   fish scripts/run_training_batched.fish --nb-samples 20 --max-tools 16 --grace-period 8
#
#   # Continue an existing run (skips the first-question step):
#   fish scripts/run_training_batched.fish --nb-samples 20 --continue <run_id>
#
# Without --continue: first batch = 1 question (creates MLflow run), then prompts for run ID.
# With --continue: all questions run in batches against the provided run ID.

# ── defaults ──
set start 0
set nb_samples 10
set batch_size 5
set run_id ""
set extra_args

# ── parse arguments ──
set i 1
while test $i -le (count $argv)
    switch $argv[$i]
        case --start
            set i (math $i + 1)
            set start $argv[$i]
        case --nb-samples
            set i (math $i + 1)
            set nb_samples $argv[$i]
        case --batch-size
            set i (math $i + 1)
            set batch_size $argv[$i]
        case --continue
            set i (math $i + 1)
            set run_id $argv[$i]
        case --end
            echo "✗ Error: --end is not supported. Use --nb-samples instead."
            echo "  --end conflicts with the batching logic (which computes --end internally)."
            echo "  Example: fish scripts/run_training_batched.fish --start 0 --nb-samples 500"
            exit 1
        case '*'
            set -a extra_args $argv[$i]
    end
    set i (math $i + 1)
end

set total_end (math $start + $nb_samples)

echo "═══════════════════════════════════════════════════════"
echo "  Batched training: questions $start.."(math $total_end - 1)
echo "  Batch size: $batch_size"
if test -n "$run_id"
    echo "  Continuing run: $run_id"
else
    echo "  First batch: 1 (to create MLflow run)"
end
echo "  Extra args: $extra_args"
echo "═══════════════════════════════════════════════════════"

set cursor $start

# ── if no run_id, run first question to create the MLflow run ──
if test -z "$run_id"
    echo ""
    echo "▶ Running first question (index $start) to create MLflow run..."
    uv run scripts/run_training_phase.py --start $start --end (math $start + 1) $extra_args

    if test $status -ne 0
        echo "✗ First batch failed. Aborting."
        exit 1
    end

    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  First question done. Check MLflow for the new run."
    echo "  Enter the MLflow run ID to continue:"
    echo "═══════════════════════════════════════════════════════"
    read -P "Run ID> " run_id

    if test -z "$run_id"
        echo "✗ No run ID provided. Aborting."
        exit 1
    end

    set cursor (math $start + 1)
end

# ── remaining batches ──
while test $cursor -lt $total_end
    set remaining (math $total_end - $cursor)
    set current_batch (math "min($batch_size, $remaining)")

    echo ""
    echo "▶ Batch: questions $cursor.."(math $cursor + $current_batch - 1)" ($current_batch questions)"
    uv run scripts/run_training_phase.py --start $cursor --end (math $cursor + $current_batch) --continue $run_id $extra_args

    if test $status -ne 0
        echo "✗ Batch starting at $cursor failed."
        echo "  To resume, run:"
        echo "  fish scripts/run_training_batched.fish --start $cursor --nb-samples "(math $total_end - $cursor)" --batch-size $batch_size --continue $run_id $extra_args"
        exit 1
    end

    set cursor (math $cursor + $current_batch)
end

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  All $nb_samples questions completed."
echo "  MLflow run ID: $run_id"
echo "═══════════════════════════════════════════════════════"
