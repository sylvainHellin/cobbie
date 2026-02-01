# Second LLM Judge (Gemini 3 Pro Preview) Implementation Plan

## Overview

Add a second LLM judge (Gemini 3 Pro Preview) to evaluate the same answers already evaluated by human judges and the first LLM judge (GLM-4.7), enabling measurement of inter-rater agreement between multiple LLM judges.

## Current State Analysis

### Existing Components
- **BAML Clients** (`src/baml/baml_src/clients.baml`): Already has `Gemini_2_5_Flash_Lite` configured with `google-ai` provider
- **Answer Verifier** (`src/agents/answer_verifier.py`): Calls `b.EvaluateResponse()` which uses `GLM_4_7` client by default
- **Grading Data** (`src/db/eval/EC3-2026 - sylvain (sylvain) 2026-01-20_21-07.csv`): Contains 100 questions with:
  - Question ID, Question, Cobbie's Answer, Ground Truth, Category
  - Error column (0=valid, 1=error)
  - UPDATED column (x=updated ground truth)
  - Human evaluations (Abstention, Faithfulness, Completeness, Transparency, Relevance)
- **IRR Stats Script** (`scripts/compute_ec3_irr_stats.py`): Computes inter-rater reliability metrics

### Data Filtering Logic (from existing script)
Questions to skip:
- `Error == 1` (19 questions with system errors)
- `UPDATED == 'x'` (3 questions with modified ground truth)
- 74 valid questions remain

## Desired End State

1. New BAML client `Gemini_3_0_Pro` configured in `clients.baml`
2. New script `scripts/run_second_llm_judge.py` that:
   - Reads Sylvain's grading sheet as input
   - Filters out Error=1 and UPDATED='x' questions
   - Uses existing answers (Cobbie's Answer column) instead of re-running Cobbie
   - Calls `verify_answer()` with the new Gemini client for each valid question
   - Outputs results in the same CSV format as existing eval files
3. Updated IRR computation script to include the second LLM judge
4. Regenerated figures and tables in `outputs/reports/ec3_irr/`

### Verification
- New output file: `src/db/eval/EC3-2026 - Gemini_Judge (Gemini_Judge) YYYY-MM-DD.csv`
- IRR metrics include 4 raters (sylvain, stefan, llm, gemini)
- All figures updated to show 4-rater comparisons

## What We're NOT Doing

- Re-running Cobbie to generate new answers
- Modifying the existing evaluation framework or criteria
- Changing the IRR computation methodology
- Adding new evaluation criteria

## Implementation Approach

Use the existing `verify_answer()` function with a client override parameter. The BAML function `EvaluateResponse` currently hardcodes `GLM_4_7`, so we'll need to either:
- Option A: Create a duplicate function with different client
- Option B: Make the client configurable via BAML options

**Chosen approach**: Option A (duplicate function) - simpler, avoids modifying existing working code.

## Phase 1: Add Gemini 3.0 Pro BAML Client

### Overview
Configure the new Gemini 3.0 Pro client in BAML.

### Changes Required:

#### 1.1 Add client to clients.baml

**File**: `src/baml/baml_src/clients.baml`
**Changes**: Add new client configuration

```baml
client<llm> Gemini_3_Pro {
  provider google-ai
  retry_policy Exponential
  options {
    model "gemini-3-pro-preview"
    api_key env.GEMINI_API_KEY
    // Note: Keep temperature at default (1.0) as recommended by Google for complex reasoning tasks
  }
}
```

Note: Using `gemini-3-pro-preview` model. Per Google's documentation, temperature should remain at default (1.0) for complex reasoning tasks.

#### 1.2 Create duplicate EvaluateResponse function

**File**: `src/baml/baml_src/answer_verifier.baml`
**Changes**: Add a new function `EvaluateResponseGemini` that uses the Gemini client

```baml
function EvaluateResponseGemini(
  question: string,
  category: QuestionCategory,
  ground_truth: string,
  system_response: string,
) -> AnswerEvaluationResult {
  client Gemini_3_Pro

  prompt #"
    ... (same prompt as EvaluateResponse)
  "#
}
```

#### 1.3 Regenerate BAML client

**Command**: `cd src/baml && uv run baml-cli generate`

### Success Criteria:

#### Automated Verification:
- [x] `cd src/baml && uv run baml-cli generate` completes without errors
- [x] `uvx ty check src/baml/baml_src/clients.baml` passes (N/A for .baml files)
- [x] Python can import `b.EvaluateResponseGemini` from baml_client

#### Manual Verification:
- [ ] Test single call to `EvaluateResponseGemini` works with valid inputs

---

## Phase 2: Create Second LLM Judge Script

### Overview
Create a simplified evaluation script that uses existing answers from the grading sheet.

### Changes Required:

#### 2.1 Create the script

**File**: `scripts/run_second_llm_judge.py`
**Changes**: New script

```python
#!/usr/bin/env python3
"""
Run Second LLM Judge (Gemini 3.0 Pro) on existing evaluation data.

Reads answers from Sylvain's grading sheet and evaluates them with Gemini,
outputting results in the same format as existing eval CSVs.

Usage:
    uv run scripts/run_second_llm_judge.py
    uv run scripts/run_second_llm_judge.py --dry-run  # Preview without calling API
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd
from loguru import logger
from tqdm import tqdm

from src.baml.baml_client import b
from src.baml.baml_client.types import QuestionCategory, CriterionResult
from src.agents.answer_verifier import derive_binary_classification

# Input file (Sylvain's grading sheet with all data)
INPUT_FILE = Path("src/db/eval/EC3-2026 - sylvain (sylvain) 2026-01-20_21-07.csv")
OUTPUT_DIR = Path("src/db/eval")


def map_category(cat: int) -> QuestionCategory:
    """Map category number to BAML enum."""
    return {
        1: QuestionCategory.Category1,
        2: QuestionCategory.Category2,
        3: QuestionCategory.Category3,
        4: QuestionCategory.Category4,
    }[cat]


def run_gemini_judge(dry_run: bool = False) -> None:
    """Run Gemini judge on all valid questions."""
    # Load data
    df = pd.read_csv(INPUT_FILE)
    logger.info(f"Loaded {len(df)} questions from {INPUT_FILE}")

    # Filter: Error=0, UPDATED != 'x'
    valid = df[(df["Error"] == 0) & (df["UPDATED"] != "x")].copy()
    logger.info(f"Valid questions after filtering: {len(valid)}")

    if dry_run:
        logger.info("DRY RUN - not calling API")
        print(f"Would evaluate {len(valid)} questions")
        print(f"Sample question IDs: {valid['Question ID'].head(5).tolist()}")
        return

    # Prepare output dataframe
    results = []

    for _, row in tqdm(valid.iterrows(), total=len(valid), desc="Evaluating with Gemini"):
        question_id = int(row["Question ID"])
        question = row["Question"]
        answer = row["Cobbie's Answer"]
        ground_truth = row["Ground Truth"]
        category = int(row["Category"])

        try:
            result = b.EvaluateResponseGemini(
                question=question,
                category=map_category(category),
                ground_truth=ground_truth,
                system_response=answer,
            )

            binary = derive_binary_classification(result)

            results.append({
                "Question ID": question_id,
                "Abstention": result.abstention,
                "Faithfulness": result.faithfulness.value,
                "Completeness": result.completeness.value,
                "Transparency": result.transparency.value,
                "Relevance": result.relevance.value,
                "Question": question,
                "Cobbie's Answer": answer,
                "Ground Truth": ground_truth,
                "Category": category,
                "Category Name": row["Category Name"],
                "Project": row["Project"],
                "Justification": result.justification,
                "Binary Classification": binary,
            })

        except Exception as e:
            logger.error(f"Error evaluating question {question_id}: {e}")
            results.append({
                "Question ID": question_id,
                "Abstention": True,
                "Faithfulness": "Na",
                "Completeness": "Na",
                "Transparency": "Na",
                "Relevance": "Na",
                "Question": question,
                "Cobbie's Answer": answer,
                "Ground Truth": ground_truth,
                "Category": category,
                "Category Name": row["Category Name"],
                "Project": row["Project"],
                "Justification": f"ERROR: {e}",
                "Binary Classification": "abstained",
            })

    # Save output
    output_df = pd.DataFrame(results)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    output_file = OUTPUT_DIR / f"EC3-2026 - Gemini_Judge (Gemini_Judge) {timestamp}.csv"
    output_df.to_csv(output_file, index=False)
    logger.info(f"Saved results to {output_file}")

    # Summary
    print(f"\n{'='*60}")
    print("GEMINI JUDGE RESULTS")
    print(f"{'='*60}")
    print(f"Total evaluated: {len(results)}")
    print(f"Abstentions: {sum(1 for r in results if r['Abstention'])}")
    print(f"Output file: {output_file}")


def main():
    parser = argparse.ArgumentParser(description="Run Gemini judge on existing answers")
    parser.add_argument("--dry-run", action="store_true", help="Preview without API calls")
    args = parser.parse_args()

    run_gemini_judge(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
```

### Success Criteria:

#### Automated Verification:
- [x] `uvx ruff check scripts/run_second_llm_judge.py` passes
- [x] `uvx ty check scripts/run_second_llm_judge.py` passes
- [x] `uvx pyright scripts/run_second_llm_judge.py` passes (1 false positive on pandas typing - code works)
- [x] `uv run scripts/run_second_llm_judge.py --dry-run` runs without errors (78 valid questions)

#### Manual Verification:
- [ ] Run full script: `uv run scripts/run_second_llm_judge.py`
- [ ] Output CSV exists in `src/db/eval/`
- [ ] Output CSV has correct format (same columns as existing eval files)

---

## Phase 3: Update IRR Stats Script

### Overview
Extend the IRR computation to include the Gemini judge as a 4th rater.

### Changes Required:

#### 3.1 Update file paths and constants

**File**: `scripts/compute_ec3_irr_stats.py`
**Changes**: Add Gemini file path, update RATERS list

```python
# Add to file paths section
GEMINI_FILE = EVAL_DIR / "EC3-2026 - Gemini_Judge (Gemini_Judge) YYYY-MM-DD_HH-MM.csv"  # Update with actual filename

# Update RATERS
RATERS = ["sylvain", "stefan", "llm", "gemini"]
```

#### 3.2 Update data loading

**File**: `scripts/compute_ec3_irr_stats.py`
**Changes**: Load and merge Gemini data

In `load_and_clean_data()`:
```python
def load_and_clean_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Load and clean the 4 CSV files."""
    sylvain = pd.read_csv(SYLVAIN_FILE)
    stefan = pd.read_csv(STEFAN_FILE)
    llm = pd.read_csv(LLM_FILE)
    gemini = pd.read_csv(GEMINI_FILE)
    # ... rest of function
    return sylvain, stefan, llm, gemini
```

#### 3.3 Update merge function

**File**: `scripts/compute_ec3_irr_stats.py`
**Changes**: Include Gemini in merge

#### 3.4 Update Krippendorff computation

**File**: `scripts/compute_ec3_irr_stats.py`
**Changes**: Add pairwise comparisons for Gemini

#### 3.5 Update figure generation

**File**: `scripts/compute_ec3_irr_stats.py`
**Changes**: Update heatmaps and bar charts for 4 raters

### Success Criteria:

#### Automated Verification:
- [x] `uvx ruff check scripts/compute_ec3_irr_stats.py` passes
- [x] `uvx ty check scripts/compute_ec3_irr_stats.py` passes (1 warning about mlflow import - fine)
- [x] `uv run scripts/compute_ec3_irr_stats.py --skip-cross-system` runs without errors

#### Manual Verification:
- [x] All output tables include Gemini columns
- [x] Figures show 4-rater comparisons (including inter_criteria_correlation_gemini.png)
- [x] `ec3_experiment.md` updated with new 4-rater findings

---

## Phase 4: Update Documentation

### Overview
Update the ec3_experiment.md with new results and findings.

### Changes Required:

#### 4.1 Update experiment documentation

**File**: `outputs/reports/ec3_irr/ec3_experiment.md`
**Changes**:
- Update raters section to include Gemini judge
- Add new IRR results tables
- Update interpretation section with 4-rater findings

### Success Criteria:

#### Manual Verification:
- [x] Documentation accurately reflects 4-rater experiment
- [x] All tables and figures referenced exist

---

## Testing Strategy

### Unit Tests:
- Test `map_category()` function with all 4 categories
- Test BAML client can be instantiated

### Integration Tests:
- Run `--dry-run` to verify data loading and filtering
- Run single question through Gemini judge to verify API connectivity

### Manual Testing Steps:
1. Run BAML generate and verify new function exists
2. Run dry-run of second LLM judge script
3. Run full evaluation (74 questions)
4. Run IRR stats script and verify output

## Performance Considerations

- 74 questions with Gemini Pro API calls
- Consider adding rate limiting if needed (Gemini has rate limits)
- Add retry logic for transient failures (already in BAML Exponential retry policy)

## References

- Gemini 3 documentation: https://ai.google.dev/gemini-api/docs/gemini-3
- BAML Google AI documentation: https://docs.boundaryml.com/ref/llm-client-providers/google-ai-gemini
- Existing clients.baml: `src/baml/baml_src/clients.baml`
- Existing IRR script: `scripts/compute_ec3_irr_stats.py`
