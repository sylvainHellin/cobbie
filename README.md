# IfcAnswerEngine - V3

An Engine that can answer any question related to a given BIM model in .ifc format. This project uses a multi-agent system (MAS) built with the [Smol-Agents](https://github.com/smol-ai/developer) library to process natural language queries.

## Roadmap

- Refactor the `get_python_interpreter` to limit output and log size
- Add an optional argument for each `dspy` agent: lm (to be able to granularly set which llm should be used for each agent)
- Implement a `prefix` to the python_interpreter in `CodeAct` to import variables and the boilerplate (to limit the amount of error because of this issue.)
- See if it would be possible to work with `**kwargs` instead of Dict for `final_answer` to reduce number of errors

## System Overview

The IfcAnswerEngine operates in two distinct modes: Training and Inference.

### Training Mode

In training mode, the system learns to generate new tools to answer questions it initially cannot. It follows a self-improving loop:

1.  Given a question from a training set, the `IfcAnswerEngine` attempts to answer it using its existing set of tools.
2.  If the engine cannot answer the question, it signals that a new tool is needed.
3.  A specialized `ToolMaker` agent is invoked to generate a new Python tool capable of addressing the query.
4.  The engine uses this new tool to try and answer the question again.
5.  The generated answer is compared against a ground truth by an `AnswerClassifier`.
6.  If the answer is correct, the newly generated tool is permanently saved to the engine's toolset for future use.

This process is illustrated below:

```mermaid
---
Title: IfcAnswerEngine Training Pipeline
---

flowchart TB
    subgraph IfcAnswerEngine System
        direction LR
        B(IfcAnswerEngine)
        H[Tools]
    end

    subgraph Tool Creation Loop
        direction TB
        E(ToolMaker)
        I[[Output: new tool]]
        J[save new tool]
    end

    subgraph Validation
        direction TB
        F(AnswerClassifier)
        G[["'Output:
- correct_answer (bool)'"]]
    end

    M[Start] --> A[question]
    A --> B
    H --> B
    B --Try to answer the question. ----> D[["'Output:
- answer (str)
- new_tool_needed (bool)'"]]
    D -- new_tool_needed: True --> E
    L[Ground Truth Answer] --> F
    D -- new_tool_needed: False --> F
    E -- create new tool --> I
    I -- add new tool to session --> H
    F -- classify answer --> G
    G --answer is correct AND new tool was created--> J
    J --> K[End]
    G -- else --> K
```

### Inference Mode

In inference mode, the `ToolMaker` is disabled. The engine relies on its pre-trained set of tools to answer questions. To handle novel queries or missing functionalities, it has access to two special tools:
- `web_search`: To search the internet for information.
- `query_ifcopenshell_documentation`: To look up specifics of the `ifcopenshell` library.

All tools are executed within a sandboxed Python environment for security.

## Getting Started

### Prerequisites

- Python 3.12+
- `uv` package manager (`pip install uv`)

### Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/sylvainhellin/ifcAnswerEngineV3.git
    cd ifcAnswerEngineV3
    ```

2.  Create a virtual environment and install dependencies:
    ```bash
    uv venv
    source .venv/bin/activate
    uv pip install -e .
    ```

### Running Experiments

To trace and log experiments, MLflow is used. Start the MLflow server before running any training or inference tasks:

```bash
mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite
```

## Project Structure

The core logic is located in the `src/` directory:

-   `src/engine/`: Contains the main `IfcAnswerEngine` logic, including the agent, its components, and tool definitions.
-   `src/engine/tools/`: Stores the dynamically created tools.
-   `src/experiment/`: Holds scripts and data for running experiments, including datasets and models.
-   `src/config.py`: Configuration file for the project.
