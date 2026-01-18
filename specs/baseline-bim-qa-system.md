# Baseline BIM-QA System: Static Summary Approach

## Context

### Research Background

This baseline system is being developed for the EC3 2026 paper: **"Validating Multi-Dimensional Evaluation of BIM Question Answering Systems: Human-LLM Agreement Analysis"**.

The paper validates an evaluation framework for BIM-QA systems. Currently, only one system (Cobbie - an LLM-based agentic workflow) has been evaluated. Adding a second, fundamentally different system strengthens the paper by:

1. **Demonstrating framework generalizability**: The evaluation framework should work across different BIM-QA architectures
2. **Providing baseline comparison**: Shows what "naive" approaches can/cannot achieve
3. **Highlighting agentic workflow value**: Illustrates why dynamic retrieval matters for certain question categories

### Inspiration: Savora Viewer

This baseline is inspired by the [Savora Viewer](https://github.com/SavyTechLabs/Savora-Viewer), which has two modes:
- **Selection mode**: User selects elements on screen; info about selected elements is passed to LLM
- **Summary mode**: If nothing selected, a default model summary (element counts, types, quantities) is passed as context

We implement **only the summary mode**—a deterministic, static approach where the same model summary is passed as context for every question, regardless of what is being asked.

### Scientific Hypothesis

**H1**: A static summary approach will perform well on Category 2 (aggregation) questions where counts and totals are explicitly in the summary, but will fail on:
- Category 1 (direct property) questions requiring specific element properties not in summary
- Category 3 (geometric) questions requiring spatial computations
- Category 4 (incomplete info) questions requiring reasoning about missing data

**H2**: Comparing baseline vs. agentic approach will reveal which question categories benefit from dynamic retrieval.

---

## System Design

### Architecture Overview

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│   IFC Model     │────▶│ Summary Extractor │────▶│ Model       │
│   (.ifc file)   │     │ (one-time)        │     │ Summary     │
└─────────────────┘     └──────────────────┘     │ (cached)    │
                                                  └──────┬──────┘
                                                         │
┌─────────────────┐     ┌──────────────────┐            │
│   Question      │────▶│   LLM Prompt     │◀───────────┘
│   (from IFC-    │     │   (summary +     │
│    Bench)       │     │    question)     │
└─────────────────┘     └────────┬─────────┘
                                 │
                                 ▼
                        ┌──────────────────┐
                        │   LLM Response   │
                        │   (answer)       │
                        └──────────────────┘
```

### Key Design Decisions

1. **Static summary per model**: Summary is extracted once per IFC file, not per question
2. **No dynamic retrieval**: Unlike Cobbie, no tools or agents query the model at runtime
3. **Same LLM backbone**: Use same LLM (e.g., GPT-4, Claude) as Cobbie for fair comparison
4. **Deterministic context**: Every question for a given model receives identical context

### Summary Content

The model summary should include information that a user would reasonably have access to in a "model overview":

```
MODEL SUMMARY FOR: {filename}
================================

BUILDING OVERVIEW:
- Name: {IfcBuilding.Name}
- Description: {IfcBuilding.Description}
- Address: {IfcSite address if available}

SPATIAL STRUCTURE:
- Number of storeys: {count}
- Storey names: {list}
- Number of spaces/rooms: {count}
- Space names and types: {list with basic info}

ELEMENT COUNTS BY TYPE:
- Walls: {count} (Exterior: X, Interior: Y)
- Doors: {count}
- Windows: {count}
- Slabs: {count}
- Columns: {count}
- Beams: {count}
- Stairs: {count}
- ... (other significant types)

MATERIALS USED:
- {material_name}: used in {count} elements
- ...

PROPERTY SUMMARY:
- Total elements with fire rating: {count}
- Total elements with thermal properties: {count}
- ...

Note: This is a summary overview. Specific element properties,
geometric calculations, and spatial relationships are not included.
```

---

## Implementation Plan

### Directory Structure

```
analysis/
├── baseline_qa/
│   ├── __init__.py
│   ├── ifc_summary.py      # Extract summary from IFC
│   ├── qa_system.py        # Run questions through LLM
│   ├── evaluate.py         # Evaluate answers
│   └── run_benchmark.py    # Main script to run IFC-Bench
├── data/
│   ├── ifc_bench/          # IFC-Bench questions and models
│   └── baseline_results/   # Output directory
└── pyproject.toml          # Add dependencies
```

### Step 1: IFC Summary Extractor

**File**: `analysis/baseline_qa/ifc_summary.py`

**Dependencies**: `ifcopenshell`

**Functions**:
```python
def extract_model_summary(ifc_path: str) -> dict:
    """
    Extract comprehensive summary from IFC model.
    Returns structured dict with all summary information.
    """
    pass

def format_summary_for_llm(summary: dict) -> str:
    """
    Format summary dict as human-readable text for LLM context.
    """
    pass

def get_or_create_summary(ifc_path: str, cache_dir: str = None) -> str:
    """
    Get cached summary or create new one.
    Cache summaries to avoid re-extraction.
    """
    pass
```

**Implementation notes**:
- Use `ifcopenshell` for IFC parsing
- Handle IFC2x3 and IFC4 schemas
- Graceful handling of missing/malformed data
- Cache summaries as JSON files

### Step 2: QA System

**File**: `analysis/baseline_qa/qa_system.py`

**Dependencies**: LLM client (e.g., `openai`, `anthropic`, or unified via `litellm`)

**Functions**:
```python
def create_qa_prompt(question: str, model_summary: str) -> str:
    """
    Create prompt combining summary and question.
    Include instructions for the LLM on how to respond.
    """
    pass

def answer_question(
    question: str,
    model_summary: str,
    llm_client,
    model_name: str = "gpt-4"
) -> dict:
    """
    Get answer from LLM.
    Returns dict with 'answer', 'model', 'tokens_used'.
    """
    pass

def batch_answer_questions(
    questions: list[dict],
    model_summaries: dict[str, str],  # ifc_filename -> summary
    llm_client,
    model_name: str = "gpt-4"
) -> list[dict]:
    """
    Answer multiple questions.
    Returns list of results with question_id, answer, metadata.
    """
    pass
```

**Prompt design**:
```
You are a BIM (Building Information Model) assistant. You have access to a
summary of a building model. Answer the user's question based ONLY on the
information provided in the summary.

IMPORTANT GUIDELINES:
1. If the information needed to answer is not in the summary, clearly state
   "The model summary does not contain this information."
2. Do not make assumptions about specific element properties unless explicitly
   stated in the summary.
3. For counting questions, use the counts provided in the summary.
4. Be precise and concise in your answers.

MODEL SUMMARY:
{model_summary}

QUESTION: {question}

ANSWER:
```

### Step 3: Evaluation Integration

**File**: `analysis/baseline_qa/evaluate.py`

**Purpose**: Compare baseline answers against ground truth using existing evaluation framework.

**Functions**:
```python
def load_ifc_bench_questions(bench_path: str) -> list[dict]:
    """Load IFC-Bench questions with ground truth."""
    pass

def evaluate_answer(
    question: dict,
    system_answer: str,
    ground_truth: str
) -> dict:
    """
    Apply evaluation criteria (same as used for Cobbie).
    Returns dict with criterion scores.
    """
    pass

def compute_accuracy_by_category(results: list[dict]) -> dict:
    """
    Compute accuracy breakdown by question category.
    """
    pass
```

### Step 4: Benchmark Runner

**File**: `analysis/baseline_qa/run_benchmark.py`

**Purpose**: Main script to run full IFC-Bench evaluation.

```python
def main():
    # 1. Load IFC-Bench questions (same 78 questions used for Cobbie)
    questions = load_ifc_bench_questions()

    # 2. Extract/load model summaries for each IFC file
    summaries = {}
    for ifc_file in get_unique_ifc_files(questions):
        summaries[ifc_file] = get_or_create_summary(ifc_file)

    # 3. Run all questions through baseline system
    results = batch_answer_questions(questions, summaries)

    # 4. Save results
    save_results(results, "baseline_results.json")

    # 5. Generate comparison report
    generate_comparison_report(results, cobbie_results)
```

---

## Integration with EC3 Paper

### Paper Modifications Needed

1. **Methodology section** (~1 paragraph):
   > To provide baseline comparison, we implemented a static summary approach inspired by existing BIM viewers. This system extracts a one-time model summary (element counts, types, spatial structure) and passes it as context to the same LLM backbone for all questions—without dynamic retrieval or tool use.

2. **Results section** (~1 table column + 1 paragraph):
   - Add "Baseline" column to accuracy tables
   - Brief comparison of where baseline succeeds/fails

3. **Discussion section** (~2-3 sentences):
   > The baseline system achieved X% accuracy on Category 2 questions (aggregation) where counts are explicit in the summary, but only Y% on Category 3 (geometric) where dynamic model access is required. This demonstrates that the evaluation framework discriminates between fundamentally different BIM-QA architectures and highlights the value of retrieval-augmented approaches.

### Expected Results Table

| Category | N | Cobbie | Baseline | Delta |
|----------|---|--------|----------|-------|
| 1: Direct Property | 15 | ~100% | 30-50% | -50% |
| 2: Aggregation | 39 | ~85% | 60-80% | -15% |
| 3: Geometric/Spatial | 6 | ~60% | 0-20% | -50% |
| 4: Incomplete Info | 18 | ~70% | 40-60% | -20% |
| **Overall** | 78 | ~80% | 40-60% | -30% |

---

## Timeline

| Task | Estimated Time | Priority |
|------|---------------|----------|
| IFC summary extractor | 1-2 hours | High |
| QA system (LLM integration) | 1 hour | High |
| Run benchmark on 78 questions | 30 min (API calls) | High |
| Manual evaluation of answers | 2-3 hours | High |
| Update paper with results | 1 hour | High |
| **Total** | ~6-8 hours | |

---

## Dependencies

Add to `analysis/pyproject.toml`:
```toml
[project]
dependencies = [
    "ifcopenshell",
    "openai",  # or anthropic, litellm
    "pandas",
    "tqdm",
]
```

---

## Success Criteria

1. **Technical**: System runs on all 78 IFC-Bench questions without errors
2. **Scientific**: Results show meaningful differentiation between categories
3. **Paper integration**: Comparison adds value without requiring major restructuring

---

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Summary too large for context window | Limit summary to most relevant info; test context size |
| IFC parsing errors | Use try/except; skip problematic elements gracefully |
| LLM API rate limits | Add retry logic; batch requests appropriately |
| Results don't show expected pattern | Still valuable—document unexpected findings |

---

## Notes

- Use the **same 78 questions** already evaluated for Cobbie
- Use the **same LLM** (or comparable) for fair comparison
- Apply the **same evaluation criteria** for consistency
- This is a **baseline**, not a competitor—the goal is contrast, not competition
