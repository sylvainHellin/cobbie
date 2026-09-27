# Cobbie -- Code-Based BIM Information Extraction

Experiment harness for answering natural-language questions about BIM models in IFC format with LLM agents that write and execute Python (CodeAct) against [IfcOpenShell](https://ifcopenshell.org/).

> **Paper**: *BIM Information Extraction Through LLM-based Adaptive Exploration*, submitted to *Automation in Construction* (under revision). Authors: S. Hellin, S. Jang, S. Fuchs, S. Nousias, A. Borrmann.
> This repository accompanies the paper. Please cite it if you use this code or the IFC-Bench dataset.

> **Note**: the original multi-agent system with dynamic tool creation (BAML agents, MLflow tracking) described in the submitted manuscript was replaced during revision by the leaner factorial harness documented here. The old implementation is available in the git history.

## What the harness does

The revision experiments are a **model x paradigm x tools factorial**: each *cell* runs one LLM backbone in one of two paradigms, with or without curated tools, over the IFC-Bench question set.

- **Paradigm axis** -- `agentic`: a CodeAct loop (DeepAgents + persistent Jupyter kernel) that iterates freely up to a cap, then is forced to emit a structured final `Answer`; `static`: a two-call baseline (one `python_exec` inspection round, then a separate plain synthesis completion).
- **Tools axis** -- `tools`: the curated helper functions in `src/tools/curated/` are preloaded into the kernel namespace and documented in the system prompt; `none`: bare IfcOpenShell.
- **Model axis** -- any prefixed model id supported by `src/harness/llm.py` (MiniMax, Z.AI/GLM, OpenRouter, Fireworks, xAI, Gemini, OpenAI, Anthropic, ...).

The system prompt is static per cell (the IFC path and question go in the first human message), so provider prompt caching holds and cached-input tokens are measured for the cost study.

Each cell writes a single sqlite (`outputs/factorial/<cell_id>/results.sqlite`) with per-question answers, full code/observation transcripts, token/latency accounting, and (after judging) the correctness classification. Runs are resume-safe: re-launching a cell skips completed rows.

## Quick Start

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/) package manager
- API keys for the providers you want to run (see `.env.example`); `GEMINI_API_KEY` is required for the judge

### Installation

```bash
git clone <repository-url>
cd cobbie
uv sync
cp .env.example .env  # Then fill in your API keys, and set ROOT_PATH to the repo root
```

### Dataset Setup

The IFC-Bench dataset and IFC model files are hosted on HuggingFace. The dataset
ships the question-answer pairs as a CSV (`questions/ifc-bench-v2.csv`) plus
per-project IFC model folders under `projects/`. It does **not** ship a prebuilt
database; Cobbie expects a SQLite database at `src/db/db.db`, which you build
from the CSV with the bundled script.

1. **Download the dataset** from [ifc-bench-v2](https://huggingface.co/datasets/sylvainHellin/ifc-bench) on HuggingFace (the `ifc-bench-v2.csv` and the `projects/` folder).
2. **Link the IFC model files.** Cobbie expects them under `src/db/bim_models/`. Create a symlink to the ifc-bench project directory:
   ```bash
   ln -s /path/to/ifc-bench/projects src/db/bim_models
   ```
3. **Build the database** at `src/db/db.db` from the CSV:
   ```bash
   uv run python scripts/build_db.py --csv /path/to/ifc-bench-v2.csv
   ```

The evaluation set (`TESTSET`) holds 514 questions across 19 projects in 4 categories (direct property / aggregation / computation / estimation-or-unavailable).

## Running experiments

### One factorial cell

```bash
uv run python scripts/run_cell.py \
  --model minimax-anthropic:MiniMax-M3 \
  --paradigm agentic --tools none \
  --question-set full
```

Key arguments:

| Argument | Options | Default | Description |
|---|---|---|---|
| `--model` | prefixed id, e.g. `glm:glm-5.2`, `openrouter:qwen/qwen3.5-35b-a3b` | required | LLM backbone (see `src/harness/llm.py` for prefixes) |
| `--paradigm` | `static`, `agentic` | required | Generation paradigm |
| `--tools` | `none`, `tools` | required | Curated-tools axis |
| `--question-set` | `dev-mini` (10), `dev-midi` (40), `dev-large` (100), `full` (514) | `dev-mini` | Deterministic category-stratified subsets; each is a strict superset of the smaller ones |
| `--limit`, `--question-ids` | -- | -- | Escape hatches over the chosen set |
| `--repeats` | int | 1 | Repeated samples per question |
| `--thinking` | `off`, `adaptive` | `off` | Extended-thinking mode (MiniMax-M3) |
| `--temperature` | float | 0.0 | Sampling temperature |
| `--concurrency` | int | 5 | Parallel agents (one Jupyter kernel each) |
| `--out-dir` | path | `outputs/factorial` | Base dir for `<cell_id>/results.sqlite` |

`run_full_factorial.sh` / `run_glm_factorial.sh` / `scripts/run_minimax*_rerun.sh` show the full-stack invocations used for the paper.

### Judging

Correctness is scored post-hoc by a Gemini LLM-as-judge (`gemini-3.1-pro-preview`) against the multi-criteria BIM rubric; it writes `classification` (`correct` / `wrong` / `abstained` / `error`) back into each cell's sqlite. Resume-safe (already-classified rows are skipped).

```bash
# Spot-check / small cells: synchronous
uv run python scripts/judge.py --judge-mode sync --cell '<cell_id>' --dry-run
uv run python scripts/judge.py --judge-mode sync --cell '<cell_id>'

# Full pass: Gemini Batch API, one job per cell, submit/wait/collect
uv run python scripts/judge_batch.py --cells all            # or a glob, e.g. '*agentic*'
uv run python scripts/judge_batch.py --base-dir outputs/factorial_rerun_YYYYMMDD --cells all
```

### Analysis

All analysis scripts read the judged cell sqlites:

```bash
uv run python scripts/compare_runs.py                 # cross-cell accuracy/cost comparison
uv run python scripts/analyze_per_category.py         # per-category accuracy breakdown
uv run python scripts/analyze_per_project.py          # per-project quality
uv run python scripts/analyze_complementarity.py      # complementarity + significance tests
uv run python scripts/analyze_census.py               # failure-mode census over open-coded traces
uv run python scripts/view_traces_streamlit.py        # interactive trace viewer
```

## Project Structure

```
cobbie/
├── src/
│   ├── harness/          # CodeAct harness: agent loop, Jupyter interpreter,
│   │                     #   LLM routing, system prompt (jinja2), tools axis
│   ├── db/               # SQLite dataset layer, models, queries, dev subsets
│   │   └── bim_models/   # Symlink to ifc-bench/projects (gitignored)
│   ├── tools/curated/    # Curated helper functions for the tools axis
│   ├── baseline/         # IFC summary helper for the static arm
│   └── util/             # Utilities
├── scripts/              # Cell runner, judge, analysis scripts
├── prompts/              # Open-coding / census prompts for failure analysis
├── docs/                 # Architecture and dataset documentation
└── outputs/              # Cell sqlites, judge summaries, figures (gitignored)
```

## Supported LLM Providers

Prefix-routed in `src/harness/llm.py`:

- **MiniMax** (`minimax:` OpenAI-compatible, `minimax-anthropic:` Anthropic-compatible with cache-token reporting)
- **Z.AI / GLM** (`glm:`, optionally rerouted through OpenRouter via `GLM_PROVIDER=openrouter`)
- **OpenRouter** (`openrouter:<vendor>/<model>`)
- **Fireworks** (`fireworks:`), **xAI** (`grok:`)
- **Google** (`gemini:`), **OpenAI** (`openai:`), **Anthropic** (`anthropic:`)

## Development

```bash
# Lint
uv run ruff check .

# Type check
uvx ty check

# Harness smoke test
uv run python scripts/smoke_harness.py
```

## License

CC BY 4.0 -- see [LICENSE](LICENSE).
