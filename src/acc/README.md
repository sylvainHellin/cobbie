# ACC (Automated Compliance Checking) Module

Ground truth generation and GUID-based evaluation for IFC compliance checking.

## Overview

**Workflow:** Solibri → BCF → topics.json → ground_truth.json → Evaluation

```
src/acc/
├── AutorunGenerator.py      # Solibri autorun XML config
├── BcfHandler.py            # BCF extraction → topics.json
├── SolibriManagerMac.py     # Solibri execution on macOS
└── guid_comparison.py       # GUID-based P/R/F1 metrics

acc/
├── config/rule_templates.json  # Rule definitions
├── setup/                      # Solibri classification CSVs & configs
└── res/{model}/
    ├── bcfzip/                 # Solibri BCF output
    ├── issues/topics.json      # Extracted compliance issues
    └── ground_truth.json       # Evaluation ground truth
```

## Usage

### Generate Ground Truth

```bash
uv run scripts/generate_ground_truth.py
uv run scripts/generate_ground_truth.py --models duplex digital_hub
```

### Run Tool Evaluation

```bash
uv run scripts/run_acc_tool_evaluation.py
```

### Run Training

```bash
uv run scripts/run_acc_training.py --rules 304_3_1_circular_space
uv run scripts/run_acc_training.py --start 0 --end 5
```

## Rule Templates

Rules are defined in `acc/config/rule_templates.json`. Each rule specifies an
`extraction_element` field — the IFC type used to filter enriched GUIDs from
Solibri topics into the ground truth.

```json
{
  "304_3_1_circular_space": {
    "rule_code": "304.3.1",
    "rule_title": "304_3_1_circular_space",
    "description_pattern": "304.3.1 Circular Space",
    "question": "What spaces do not have enough room for wheelchair turning?",
    "extraction_element": "IfcSpace"
  }
}
```

## Metrics

GUID-based evaluation computes:
- **Per-issue:** TP, FP, FN, precision, recall, F1
- **Per-rule:** Aggregated metrics + matched issues count
