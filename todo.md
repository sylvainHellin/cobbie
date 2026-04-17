# TODO

## Before publication
- [ ] Decide on orphan root SQLite files (`acc_server.sqlite`, `acc_old.sqlite`, `mlflow.sqlite`) — gitignored, but still ~2 GB on disk
- [ ] Remove dead config paths in `src/config.py` (`TEST_IFC_PATH`, `DEVSET_PATH`, `DB_PATH`, `DIRECTORY_IFC_MODELS_PATH`, `CREATED_TOOLS_PATH`, `INITIAL_TOOLS_PATH`, `MANUAL_TOOLS_PATH`)
- [ ] End-to-end reproduction check — run steps 3–6 against committed inputs and diff `outputs/ec3/` against committed versions
- [ ] Fix pre-existing lint/type issues in `src/notebooks/acc_results.ipynb` and `src/util/get_function_code.py`
- [ ] Add citation block to `README.md` once the paper is accepted
