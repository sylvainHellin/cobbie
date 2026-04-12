# System Architecture

## Overview

Cobbie is a multi-agent system for answering questions about BIM (Building Information Modeling) models stored in IFC format. The system operates in two modes:

- **Training**: Answers questions while dynamically creating, debugging, and pruning reusable Python tools.
- **Inference/Evaluation**: Answers questions using the accumulated tool library.

All agents are defined using [BAML](https://docs.boundaryml.com/) (Boundary Markup Language) for structured LLM interactions, with Python orchestration handling state management, tool execution, and experiment tracking.

## Agent Roles

### Primary Agents

| Agent | File | Role |
|---|---|---|
| **Cobbie** | `src/agents/cobbie.py` | Main QA agent. Receives a question and IFC model, writes Python code using available tools, returns an answer. |
| **Answer Verifier** | `src/agents/answer_verifier.py` | Grades Cobbie's answer against ground truth on four criteria: faithfulness, completeness, transparency, relevance. |

### Tool Management Agents (Training Only)

| Agent | File | Role |
|---|---|---|
| **Identify Helper** | `src/agents/identify_helper_function.py` | After a correct answer, identifies reusable logic in Cobbie's code that could become a tool. |
| **Create Helper** | `src/agents/create_helper_function.py` | Extracts the identified logic into a standalone, documented Python function. |
| **Faulty Tool Identifier** | `src/agents/faulty_tool_identifier.py` | After a wrong answer, identifies which tool (if any) caused the failure. |
| **Debug Helper** | `src/agents/debug_helper_function.py` | Fixes the faulty tool based on error analysis. |
| **Assess Helper** | `src/agents/assess_helper_function.py` | Tests a newly created/fixed tool by re-running Cobbie, then decides whether to keep, merge, or discard it. |

### Baseline Systems

| System | File | Description |
|---|---|---|
| **Static One-Shot** | `src/agents/static_oneshot.py` | Single-turn code generation without iterative refinement. |
| **Static One-Shot + Docs** | `src/agents/static_oneshot_doc.py` | Same as above but with IfcOpenShell documentation context. |

## Tool Ecosystem

Tools are Python functions that Cobbie can call to interact with IFC models. They are organized in three directories:

```
src/tools/
  initial/        1 tool:  query_ifcopenshell_documentation (RAG over docs)
  manual/        26 tools: hand-written functions for common BIM queries
  created/        N tools: dynamically generated during training
```

Each tool is a standalone `.py` file with a function that takes an `ifcopenshell.file` object and returns structured data. Tools include docstrings that Cobbie uses to decide which tool to call.

## Training Loop (State Machine)

```
START
  |
  v
RUN_COBBIE  ------->  VERIFY_ANSWER
                          |
              +-----------+-----------+
              |                       |
         Correct answer          Wrong answer
              |                       |
              v                       v
     IDENTIFY_NEW_TOOL       IDENTIFY_FAULTY_TOOL
              |                       |
              v                       v
       CREATE_NEW_TOOL         DEBUG_FAULTY_TOOL
              |                       |
              +----------+------------+
                         |
                         v
               TEST_TOOL_WITH_COBBIE
                         |
                         v
                  ASSESS_TOOL_USAGE
                         |
                         v
                  DECIDE_TOOL_FATE
                    (keep / merge / discard)
                         |
                         v
                        END
```

After each question, tools are ranked by a deletion score (based on usage frequency, success rate, and age). When the tool count exceeds `--max-tools`, the lowest-ranked tools are pruned.

## Evaluation Pipeline

1. Load evaluation split from IFC-Bench dataset (`src/db/`)
2. For each question, run the selected system configuration (cobbie/static/static-doc)
3. Grade the answer using the Answer Verifier agent
4. Log metrics, traces, and tool usage to MLflow
5. Aggregate results (accuracy, abstention rate, per-category breakdown)

## Data Flow

```
IFC Model (.ifc)  --->  ifcopenshell  --->  Cobbie Agent
                                               |
Question (text)  ------------------------------>|
                                               |
Tool Docs (auto-generated)  ------------------>|
                                               |
                                               v
                                     Python code generation
                                               |
                                               v
                                     Tool execution (sandboxed)
                                               |
                                               v
                                     Answer (text)
                                               |
                                               v
                                     Answer Verifier
                                               |
                                               v
                                     Grading (4 criteria)
```

## Key Dependencies

- **ifcopenshell**: Python library for reading and querying IFC files
- **BAML**: Structured LLM prompting framework (agent definitions in `src/baml/baml_src/`)
- **MLflow**: Experiment tracking (runs, metrics, parameters, artifacts)
- **SQLModel**: ORM for the IFC-Bench dataset stored in SQLite
