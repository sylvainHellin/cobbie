# Update Evaluation Framework

## Overview

Replace the binary correct/wrong/abstained evaluation with a 5-criterion framework based on `specs/eval_instruction.md`.

## New Evaluation Criteria

| Criterion | Type | Description |
|-----------|------|-------------|
| Abstention | bool | `true` = system abstained, `false` = answer provided |
| Faithfulness | yes/no/na | Claims grounded in valid sources for question category |
| Completeness | yes/no/na | All relevant facts included (N/A for open-ended questions) |
| Transparency | yes/no/na | Sources/methods explicitly disclosed |
| Relevance | yes/no/na | Directly addresses the question asked |

## Derived Classification (for training script)

For backward compatibility with training logic:
- `abstained`: `abstention = true`
- `correct`: `abstention = false` AND `faithfulness = yes` AND `completeness = yes`
- `wrong`: otherwise

Note: Transparency and Relevance do not affect tool creation/debugging decisions.

---

## Phase 1: Update BAML Schema and Prompt

### Files to modify
- `baml_src/schemas.baml`
- `baml_src/answer_verifier.baml`

### Changes to `schemas.baml`

Add new enum:
```baml
enum CriterionResult {
  yes
  no
  na
}
```

Update `AnswerEvaluationResult`:
```baml
class AnswerEvaluationResult {
  abstention bool @description("true if system explicitly declined to answer, false if answer provided")
  faithfulness CriterionResult @description("Are all claims grounded in valid sources for this question category?")
  completeness CriterionResult @description("Are all relevant facts included? Use 'na' for open-ended questions")
  transparency CriterionResult @description("Are sources/methods explicitly disclosed for each claim?")
  relevance CriterionResult @description("Does the answer directly address the question asked?")
  justification string @description("Brief explanation of the evaluation, especially for edge cases")
}
```

### Changes to `answer_verifier.baml`

Rewrite prompt based on `specs/eval_instruction.md`:
- Evaluation workflow: first check abstention, then evaluate 4 quality criteria
- Category-specific faithfulness rules
- Completeness N/A determination by LLM
- Transparency requirements (explicit disclosure, not hedging)
- Relevance assessment

### Test
```bash
uv run baml-cli check
uv run baml-cli generate
```

---

## Phase 2: Update `answer_verifier.py`

### Files to modify
- `src/agents/answer_verifier.py`

### Changes

1. Add helper function:
```python
def derive_classification(result: AnswerEvaluationResult) -> Literal["correct", "wrong", "abstained"]:
    if result.abstention:
        return "abstained"
    if result.faithfulness == CriterionResult.yes and result.completeness == CriterionResult.yes:
        return "correct"
    return "wrong"
```

2. Update `verify_answer()`:
   - Return type remains `Tuple[AnswerEvaluationResult, Collector]`
   - Update MLflow span outputs to include all 5 criteria

3. Update `__main__` test block to print new fields

### Test
```bash
uv run python src/agents/answer_verifier.py
```

---

## Phase 3: Update `run_training_phase.py`

### Files to modify
- `scripts/run_training_phase.py`

### Changes

1. Import `derive_classification` from `src.agents.answer_verifier`

2. Update `handle_verify_answer()`:
   - Use `derive_classification(result)` for branching logic
   - Log all 5 criteria to MLflow

3. Update `log_qa_metrics()`:
   - Add metrics for each criterion
   - Keep derived classification for aggregate metrics

4. Update `calculate_aggregate_metrics()`:
   - Add criterion-level aggregates

### Test
```bash
uv run scripts/run_training_phase.py --start 0 --end 2
```

---

## Phase 4: Update `run_evaluation.py`

### Files to modify
- `scripts/run_evaluation.py`

### Changes

1. Update `calculate_and_log_metrics()`:
   - Replace `accuracy`, `correct_count`, `wrong_count`, `abstained_count` with:
     - `abstention_rate`: abstained / total
     - `faithfulness_rate`: yes / (yes + no) for faithfulness
     - `completeness_rate`: yes / (yes + no) for completeness
     - `transparency_rate`: yes / (yes + no) for transparency
     - `relevance_rate`: yes / (yes + no) for relevance
   - Track counts for each criterion (yes/no/na)

2. Update `process_question()`:
   - Log all 5 criteria to MLflow
   - Update result dictionary structure

3. Update `print_results()`:
   - Display new criterion-based metrics
   - Show N/A counts where applicable

### Test
```bash
uv run scripts/run_evaluation.py --start 0 --nb-samples 3
```

---

## Checklist

- [ ] Phase 1: BAML schema and prompt updated
- [ ] Phase 1: `baml-cli check` passes
- [ ] Phase 1: `baml-cli generate` completed
- [ ] Phase 2: `answer_verifier.py` updated
- [ ] Phase 2: Manual test passes
- [ ] Phase 3: `run_training_phase.py` updated
- [ ] Phase 3: Training test passes
- [ ] Phase 4: `run_evaluation.py` updated
- [ ] Phase 4: Evaluation test passes
