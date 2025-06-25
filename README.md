# IfcAnswerEngine - V3

The third version of the IfcAnswerEngine: this time using the Smolagents library from Hugging Face for agent orchestration and the CodeAct paradigm.

It answers any question in natural language about any BIM model stored in .ifc format.

## Tracing

### MLflow

Set up MLflow first:
```bash
mlflow server --backend-store-uri sqlite:///mlflow.sqlite
```
