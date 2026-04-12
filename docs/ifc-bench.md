# IFC-Bench Dataset

## What is IFC-Bench?

IFC-Bench is a benchmark dataset for evaluating AI systems that answer questions about BIM (Building Information Modeling) models stored in the Industry Foundation Classes (IFC) format.

Each entry pairs a natural-language question with a ground-truth answer, linked to a specific IFC model file. The questions test a system's ability to read, interpret, and reason about building data.

## Dataset Location

The dataset is hosted on HuggingFace: [ifc-bench-v2](https://huggingface.co/datasets/ifc-bench-v2)

It consists of:
- A SQLite database (`db.db`) containing the questions, ground truth answers, and IFC model metadata
- IFC model files referenced by the database

## Statistics

- **Total QA pairs**: ~200
- **IFC models**: 10 files across multiple building projects
- **Train/Dev split**: 50/50, seeded shuffle (`seed=42`)

## Question Categories

Questions are categorized by the type of reasoning required:

| Category | Name | Description |
|---|---|---|
| 1 | Direct Property | Answer is directly available as a property or attribute in the IFC model |
| 2 | Aggregation | Answer requires counting, summing, or grouping elements |
| 3 | Computation | Answer requires geometric calculations or derived values |
| 4 | Estimation/Unavailable | Answer requires inference or is not explicitly modeled |

## Database Schema

### `ifcmodels` table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `project_name` | TEXT | Project identifier |
| `model_name` | TEXT | Model name within the project |
| `model_path` | TEXT | Relative path to the .ifc file |
| `model_description` | TEXT | Brief description of the model |

### `ifc_bench` table

| Column | Type | Description |
|---|---|---|
| `id` | INTEGER | Primary key |
| `question` | TEXT | Natural-language question about the IFC model |
| `ground_truth` | TEXT | Expected answer |
| `ifc_id` | INTEGER | Foreign key to `ifcmodels.id` |
| `category` | INTEGER | Question category (1-4) |
| `cobbie` | TEXT | Cobbie's cached answer (nullable) |

## Ground Truth Format

Ground truth answers are stored as plain text. They can be:
- A single value (e.g., "42", "3.5 m")
- A short phrase (e.g., "reinforced concrete")
- A list (e.g., "Level 1, Level 2, Level 3")

Answers are evaluated by an LLM judge on four criteria:
1. **Faithfulness** -- is the answer factually consistent with the IFC model?
2. **Completeness** -- does it cover all aspects of the question?
3. **Transparency** -- does it explain how the answer was derived?
4. **Relevance** -- does it directly address the question?

## Extending the Dataset

To add new questions:

1. Register new IFC models in the `ifcmodels` table with their file paths.
2. Add QA pairs to the `ifc_bench` table, linking each to an `ifc_id`.
3. Assign a category (1-4) to each question.
4. Place the corresponding `.ifc` files under `src/db/bim_models/`.

Use the `sqlacodegen` tool to regenerate models if the schema changes:

```bash
uv run sqlacodegen sqlite:///src/db/db.db --generator sqlmodels --outfile src/db/models.py
```

## Extracting Statistics

```bash
uv run scripts/extract_benchmark_stats.py
```

This produces summary files under `outputs/ifc-bench/`.
