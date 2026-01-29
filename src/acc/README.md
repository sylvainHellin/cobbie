# ACC (Automated Compliance Checking) Module

Ground truth generation and GUID-based evaluation for IFC compliance checking.

## Overview

**Workflow:** Solibri → BCF → topics.json → ground_truth.json → Evaluation

```
src/acc/
├── AutorunGenerator.py      # Solibri autorun XML config
├── BcfHandler.py            # BCF extraction → topics.json
├── GroundTruthGenerator.py  # topics.json → ground_truth.json
├── Evaluator.py             # GUID-based P/R/F1 metrics
├── ModelProcessor.py        # Pipeline orchestration
└── SolibriManagerMac.py     # Solibri execution on macOS

acc/
├── config/rule_templates.json  # Rule definitions + GUID strategies
├── setup/                      # Solibri classification CSVs & configs
└── res/{model}/
    ├── bcfzip/                 # Solibri BCF output
    ├── issues/topics.json      # Extracted compliance issues
    └── ground_truth.json       # Evaluation ground truth
```

## GUID Strategies

Rules use different strategies to determine which GUIDs are required for a compliance match:

| Strategy | Required GUIDs | Example |
|----------|---------------|---------|
| `single` | First element | Space with insufficient wheelchair clearance |
| `primary_and_cause` | First element only | Stair (primary), slabs are context |
| `multiple` | All GUIDs | Colliding elements |
| `context_and_primary` | After first type change | [Space, Space, Door] → [Door] |

## Usage

### Generate Ground Truth

```python
from src.acc.GroundTruthGenerator import generate_ground_truth, generate_all_ground_truth

# Single model
generate_ground_truth("duplex")

# All models
generate_all_ground_truth()
```

### Evaluate Predictions

```python
from src.acc.Evaluator import AccEvaluator, format_evaluation_result

evaluator = AccEvaluator("duplex")

# Predictions format: rule_title -> list of {topic_id, predicted_guids}
predictions = {
    "304_3_1_circular_space": [
        {"topic_id": "abc-123", "predicted_guids": ["GUID1", "GUID2"]}
    ]
}

result = evaluator.evaluate(predictions)
print(format_evaluation_result(result))
```

### Run Full Pipeline

```bash
# Generate ground truth
uv run python -c "from src.acc.GroundTruthGenerator import generate_all_ground_truth; generate_all_ground_truth()"

# Run ACC evaluation
uv run scripts/run_acc_evaluation.py --model duplex
```

## Rule Templates

Rules are defined in `acc/config/rule_templates.json`:

```json
{
  "304_3_1_circular_space": {
    "rule_code": "304.3.1",
    "rule_title": "304_3_1_circular_space",
    "description_pattern": "304.3.1 Circular Space",
    "question": "What spaces do not have enough room for wheelchair turning?",
    "guid_strategy": "single"
  }
}
```

## Metrics

The evaluator computes:
- **Per-issue:** TP, FP, FN, precision, recall, F1
- **Per-rule:** Aggregated metrics + matched issues count
- **Overall:** Micro-averaged and macro-averaged P/R/F1
