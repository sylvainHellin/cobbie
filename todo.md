# TODO

## Before publication
- [ ] Decide on orphan root SQLite files (`acc_server.sqlite`, `acc_old.sqlite`, `mlflow.sqlite`) — gitignored, but still ~2 GB on disk
- [ ] Trim unused helpers in `src/util/` (`extract_tool_usage.py`, `get_created_tools.py`, `get_tools.py`, `get_usage_openrouter.py`, `query_mlflow.py`) and remove dead config paths in `src/config.py` (`TEST_IFC_PATH`, `DEVSET_PATH`, `DB_PATH`, `DIRECTORY_IFC_MODELS_PATH`, `CREATED_TOOLS_PATH`, `INITIAL_TOOLS_PATH`, `MANUAL_TOOLS_PATH`)
- [ ] Prune `pyproject.toml` — dead deps confirmed unused by the ACC pipeline: `sentence-transformers`, `sqlite-vec`, `chromadb`, `rank-bm25`, `docutils`, `sqlmodel`, `sqlacodegen`, `krippendorff`, `openpyxl`, `ollama`, `mlx`, `mlx-lm`, `torch`, `streamlit`, `arize-phoenix`, `openinference-instrumentation-smolagents`, `mermaid-magic`, `seaborn`, `rtree`, `fastapi`, `jupyter`, `ipykernel`
- [ ] End-to-end reproduction check — run steps 3–6 against committed inputs and diff `outputs/ec3/` against committed versions
- [ ] Fix pre-existing lint/type issues in `src/notebooks/acc_results.ipynb` and `src/util/get_function_code.py`
- [ ] Add citation block to `README.md` once the paper is accepted
