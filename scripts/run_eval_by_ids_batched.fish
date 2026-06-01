#!/usr/bin/env fish
#
# Run evaluation in batches using --question-ids.
# Each batch runs as a separate process to avoid ifcopenshell memory accumulation.
#
# Usage:
#   fish scripts/run_eval_by_ids_batched.fish --question-ids dev_split_qids.json
#   fish scripts/run_eval_by_ids_batched.fish --question-ids dev_split_qids.json --batch-size 10 --client MiniMax_M2_7
#
#   # Continue an existing run:
#   fish scripts/run_eval_by_ids_batched.fish --question-ids dev_split_qids.json --continue <run_id>

# -- defaults --
set batch_size 10
set run_id ""
set qids_file ""
set extra_args

# -- parse arguments --
set i 1
while test $i -le (count $argv)
    switch $argv[$i]
        case --question-ids
            set i (math $i + 1)
            set qids_file $argv[$i]
        case --batch-size
            set i (math $i + 1)
            set batch_size $argv[$i]
        case --continue
            set i (math $i + 1)
            set run_id $argv[$i]
        case '*'
            set -a extra_args $argv[$i]
    end
    set i (math $i + 1)
end

if test -z "$qids_file"
    echo "Error: --question-ids is required"
    exit 1
end

# Split JSON into batches using python
set tmp_dir (mktemp -d)
set total (python3 -c "
import json, math, sys
with open('$qids_file') as f:
    ids = json.load(f)
bs = $batch_size
n_batches = math.ceil(len(ids) / bs)
for i in range(n_batches):
    chunk = ids[i*bs : (i+1)*bs]
    with open(f'$tmp_dir/batch_{i:04d}.json', 'w') as f:
        json.dump(chunk, f)
print(len(ids))
")

set batch_files (ls $tmp_dir/batch_*.json | sort)
set n_batches (count $batch_files)

echo "═══════════════════════════════════════════════════════"
echo "  Batched evaluation: $total questions in $n_batches batches"
echo "  Batch size: $batch_size"
echo "  Question IDs: $qids_file"
if test -n "$run_id"
    echo "  Continuing run: $run_id"
end
echo "  Extra args: $extra_args"
echo "═══════════════════════════════════════════════════════"

set batch_idx 0

# -- if no run_id, run first batch to create the MLflow run --
if test -z "$run_id"
    set batch_idx 1
    set first_batch $batch_files[1]
    set first_count (python3 -c "import json; print(len(json.load(open('$first_batch'))))")

    echo ""
    echo ">> Batch 1/$n_batches ($first_count questions) -- creating MLflow run..."
    uv run scripts/run_evaluation.py --question-ids $first_batch $extra_args

    if test $status -ne 0
        echo "x First batch failed. Aborting."
        rm -rf $tmp_dir
        exit 1
    end

    echo ""
    echo "═══════════════════════════════════════════════════════"
    echo "  First batch done. Check MLflow for the new run."
    echo "  Enter the MLflow run ID to continue:"
    echo "═══════════════════════════════════════════════════════"
    read -P "Run ID> " run_id

    if test -z "$run_id"
        echo "x No run ID provided. Aborting."
        rm -rf $tmp_dir
        exit 1
    end
end

# -- remaining batches --
while test $batch_idx -lt $n_batches
    set batch_idx (math $batch_idx + 1)
    set batch_file $batch_files[$batch_idx]
    set batch_count (python3 -c "import json; print(len(json.load(open('$batch_file'))))")

    echo ""
    echo ">> Batch $batch_idx/$n_batches ($batch_count questions)"
    uv run scripts/run_evaluation.py --question-ids $batch_file --continue $run_id $extra_args

    if test $status -ne 0
        echo "x Batch $batch_idx failed."
        echo "  Remaining batch files are in: $tmp_dir"
        echo "  To resume from batch $batch_idx:"
        echo "  # Process remaining batches manually with --continue $run_id"
        exit 1
    end
end

# Cleanup
rm -rf $tmp_dir

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  All $total questions completed in $n_batches batches."
echo "  MLflow run ID: $run_id"
echo "═══════════════════════════════════════════════════════"
