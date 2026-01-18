# Custom Documentation Query System - Specification

## Status

| Phase | Status | Notes |
|-------|--------|-------|
| Phase 1: Indexing Pipeline | ✅ Complete | All components implemented |
| Phase 2: Query Pipeline | ✅ Complete | Dual search + reranking working |
| Phase 3: Full Indexing | ⏳ Pending | Need to run with LLM review |
| Phase 4: Evaluation | ⏳ Pending | Compare custom vs Context7 |

---

## Background

The current `query_ifcopenshell_docs` tool uses Context7 API, which has rate limits and is a black box. This spec describes a custom implementation with:
- Full control over the pipeline (valuable for research paper)
- No external API dependencies
- Quality-controlled chunks reviewed by LLM (GLM 4.7)

**Config switch**: `DOC_BACKEND` environment variable (`"context7"` or `"custom"`, default: `"custom"`)

---

## 1. Documentation Source

### Repository & Version
- **Repo**: https://github.com/IfcOpenShell/IfcOpenShell
- **Branch**: `0.8.0` (note: `v0.8.2` tag doesn't exist, using branch instead)
- **Clone location**: `external/ifcopenshell-docs/` (gitignored)

### Content Extracted

| Type | Location | Chunks |
|------|----------|--------|
| RST tutorials | `docs/ifcopenshell-python/*.rst` | 69 |
| Python docstrings | `ifcopenshell/**/*.py` | 702 |
| **Total** | | **771** |

**Tutorial files parsed:**
- `code_examples.rst` (16 chunks)
- `geometry_creation.rst` (15 chunks)
- `geometry_processing.rst` (5 chunks)
- `geometry_tree.rst` (8 chunks)
- `hello_world.rst` (1 chunk)
- `installation.rst` (12 chunks)
- `schema_querying.rst` (2 chunks)
- `selector_syntax.rst` (4 chunks)
- `validation.rst` (6 chunks)

**Python modules parsed:**
- `ifcopenshell` core (53 chunks)
- `ifcopenshell.api.*` (410 chunks)
- `ifcopenshell.util.*` (233 chunks)
- `ifcopenshell.geom/*` (42 chunks - note: some files failed to parse)

---

## 2. Architecture

### Indexing Pipeline
```
RST Files ─────┐
               ├──► Parse ──► Chunks ──► LLM Review ──► Embed ──► sqlite-vec
Python Files ──┘                           (GLM 4.7)    (mpnet)
                                              │
                                              ▼
                                     Generate Questions ──► Embed ──► sqlite-vec
```

### Query Pipeline
```
User Query
    │
    ▼
┌─────────────────┐
│ Embed query     │
│ (all-mpnet)     │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ Search BOTH:                        │
│ 1. doc_chunk_embeddings (top 25)    │
│ 2. doc_question_embeddings (top 25) │
└────────┬────────────────────────────┘
         │
         ▼
┌─────────────────┐
│ Dedupe & merge  │
│ (by chunk_id)   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Rerank (top 5)  │
│ (cross-encoder) │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Format & return │
└─────────────────┘
```

---

## 3. Components

### Chunk Model
```python
@dataclass
class DocChunk:
    id: str                    # SHA256 hash (first 16 chars)
    content: str               # Docstring or section text
    chunk_type: str            # "function" | "class" | "method" | "module" | "tutorial_section"
    name: str                  # Function/class name or section title
    module: str | None         # e.g., "ifcopenshell.util.element"
    signature: str | None      # For functions/methods
    source_file: str           # Relative path
    line_start: int | None     # For traceability
    parent: str | None         # Parent class for methods
    questions: list[str]       # Generated hypothetical questions
```

### Embedding Model
- **Model**: `all-mpnet-base-v2`
- **Dimensions**: 768
- **Rationale**: Best quality among sentence-transformers, speed not critical for offline indexing

### Reranker
- **Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2`
- **Purpose**: Re-score top candidates for better precision

### LLM for Review
- **Model**: GLM 4.7 (via Z.AI API)
- **Client**: Defined in `baml_src/chunk_reviewer.baml`
- **Task**: Review chunk usefulness + generate 3-5 hypothetical questions per chunk

### Vector Storage
- **Database**: sqlite-vec
- **Location**: `src/db/doc_vectors.db`
- **Tables**:
  - `doc_chunks` - Chunk metadata
  - `doc_chunk_embeddings` - Chunk vectors (vec0)
  - `doc_questions` - Generated questions
  - `doc_question_embeddings` - Question vectors (vec0)

---

## 4. File Structure

```
src/docs_indexer/
├── __init__.py          # Module exports (query_docs, retrieve, run_indexing)
├── models.py            # DocChunk dataclass
├── parser_rst.py        # RST file parsing (regex-based section extraction)
├── parser_python.py     # Python docstring extraction (AST-based)
├── chunk_reviewer.py    # GLM 4.7 review via BAML
├── embedder.py          # all-mpnet-base-v2 embeddings
├── storage.py           # sqlite-vec storage (DocVectorStore class)
├── indexer.py           # Main orchestration script
└── retriever.py         # Query pipeline with reranking

src/db/
├── doc_vectors.db       # Vector database (generated)
└── doc_review_cache.json # Cache for LLM review results (avoid re-running)

src/tools/initial/
└── query_ifcopenshell_documentation.py  # Updated with DOC_BACKEND switch

baml_src/
└── chunk_reviewer.baml  # BAML function for GLM 4.7 review

external/
└── ifcopenshell-docs/   # Cloned repo (gitignored)
```

---

## 5. Usage

### Run Full Indexing (with LLM review)
```bash
uv run python src/docs_indexer/indexer.py --max-workers 5
```
This will:
1. Parse all documentation (771 chunks)
2. Review each chunk with GLM 4.7 (uses cache to avoid re-running)
3. Generate 3-5 hypothetical questions per useful chunk
4. Embed all chunks and questions
5. Store in sqlite-vec

### Run Indexing Without LLM Review (faster, for testing)
```bash
uv run python src/docs_indexer/indexer.py --skip-review
```

### Switch Backend
```bash
export DOC_BACKEND=custom   # Use local vector store (default)
export DOC_BACKEND=context7 # Use Context7 API
```

### Test Retrieval
```bash
uv run python src/docs_indexer/retriever.py
```

---

## 6. What Remains To Do

### Phase 3: Run Full Indexing with LLM Review
- [ ] Run `uv run python src/docs_indexer/indexer.py --max-workers 5`
- [ ] Verify questions are generated and stored
- [ ] Check cache file is populated (`src/db/doc_review_cache.json`)

**Estimated**: ~771 LLM calls (cached after first run)

### Phase 4: Evaluation
- [ ] Run evaluation with Context7: `DOC_BACKEND=context7 uv run python scripts/run_evaluation.py ...`
- [ ] Run evaluation with custom: `DOC_BACKEND=custom uv run python scripts/run_evaluation.py ...`
- [ ] Compare results (accuracy, latency)
- [ ] Document findings for paper

---

## 7. Dependencies Added

```toml
sentence-transformers = ">=3.0.0"  # Embeddings + reranking
sqlite-vec = ">=0.1.0"             # Vector storage
docutils = ">=0.20"                # RST parsing (not actually used, regex-based instead)
```

---

## 8. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Parse source vs scrape HTML | Parse source | Cleaner, version-controlled |
| Chunking strategy | Semantic (1 per function/section) | Better than arbitrary token splits |
| Question generation | At index time ("Hypothetical Questions") | No query-time LLM cost |
| LLM for review | GLM 4.7 | Same as Cobbie, lower cost than Claude |
| Embedding model | all-mpnet-base-v2 | Best quality, speed not critical |
| Reranker | ms-marco-MiniLM-L-6-v2 | Fast, good quality |
| Vector DB | sqlite-vec | Embedded, no server, SQLite compatible |

---

## Sources

- [IfcOpenShell GitHub](https://github.com/IfcOpenShell/IfcOpenShell)
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [Sentence Transformers](https://www.sbert.net/docs/sentence_transformer/pretrained_models.html)
- [Hypothetical Questions vs HyDE](https://pixion.co/blog/rag-strategies-hypothetical-questions-hyde)
- [Cross-encoder reranking](https://www.zeroentropy.dev/articles/ultimate-guide-to-choosing-the-best-reranking-model-in-2025)
