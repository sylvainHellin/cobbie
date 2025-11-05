# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

### Backend (Python)
- **Dev Server**: `uv run python api/start_server.py` or `uv run uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload`
- **Lint**: `uv run ruff check .`
- **Type Check**: `uv run mypy .`

### MLflow Tracking
- **Start MLflow**: `uv run mlflow server --host 127.0.0.1 --port 5000 --backend-store-uri sqlite:///mlflow.sqlite`

## Architecture Overview

This is a sophisticated AI System named Cobbie (COde Based BIM Information Extraction) for BIM Information Extraction, using an LLM-based multi-agent architecture, with a training phase and an inference mode. During the training phase, the system can dynamically create Python tools to answer questions about IFC (Industry Foundation Classes) building models.

This MAS was originaly built with the dspy framework (all legacy components are still availale in the src/engine/components), but the repo is currently migrating to baml, with the agent located in src/agents

## Development Notes

### Environment Setup
- Python 3.12+ required
- Uses `uv` package manager for Python dependencies - all Python commands should use `uv run` prefix
- Requires multiple API keys for different LLM providers (set in `.env`)

### Database Integration
- SQLite database for storing IFC model metadata and question-answer pairs
- NocoDB can be used for visual database interaction (runs on port 8080)
- MLflow for experiment tracking and model performance monitoring

### IFC File Handling
- System works with .ifc files (BIM model format)
- Test models available in `src/experiment/bim_models/`

## Important guidelines for your answers
- Don't make any assumptions. If anything is unclear, ask for clarification.
- Use context7 for up to date information when interacting with libraries like baml, mlflow, sqlmodel, fastapi, etc.
- use `uv run` if you want to run a Python script
