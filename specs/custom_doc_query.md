# Custom Documentation Query System - Specification

## Background

The current `query_ifcopenshell_docs` tool uses Context7 API, which has rate limits and is a black box. This spec describes a custom implementation with:
- Full control over the pipeline (valuable for research paper)
- No external API dependencies
- Quality-controlled chunks reviewed by Claude

**Config switch**: `DOC_BACKEND: Literal["context7", "custom"]`

---

## 1. Documentation Source

### Repository & Version
- **Repo**: https://github.com/IfcOpenShell/IfcOpenShell
- **Tag**: `v0.8.2` (matches `pyproject.toml`)
- **Clone command**: `git clone --depth 1 --branch v0.8.2 https://github.com/IfcOpenShell/IfcOpenShell.git`

### Content to Extract

| Type | Location | Format |
|------|----------|--------|
| User tutorials | `src/ifcopenshell-python/docs/ifcopenshell-python/*.rst` | RST |
| API docstrings | `src/ifcopenshell-python/ifcopenshell/**/*.py` | Python |

**Files to include from tutorials:**
- `code_examples.rst`
- `geometry_creation.rst`
- `geometry_processing.rst`
- `hello_world.rst`
- `installation.rst`
- `schema_querying.rst`
- `selector_syntax.rst`
- `validation.rst`

**Python modules to extract docstrings from:**
- `ifcopenshell` (core: `file`, `entity_instance`)
- `ifcopenshell.api.*` (all submodules)
- `ifcopenshell.util.*` (all submodules)
- `ifcopenshell.geom`
- `ifcopenshell.ids`
- `ifcopenshell.validate`

---

## 2. Parsing Strategy

### RST Files (Tutorials)
```python
from docutils.core import publish_doctree
from docutils import nodes

def parse_rst(file_path: str) -> list[dict]:
    """Parse RST file into sections with code blocks preserved."""
    with open(file_path) as f:
        doctree = publish_doctree(f.read())

    # Extract sections by heading
    # Keep code blocks attached to their explanatory text
    ...
```

### Python Files (API Docstrings)
```python
import ast

def extract_docstrings(file_path: str) -> list[dict]:
    """Extract docstrings from Python file using AST."""
    with open(file_path) as f:
        tree = ast.parse(f.read())

    chunks = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            docstring = ast.get_docstring(node)
            if docstring:
                chunks.append({
                    "type": "class" if isinstance(node, ast.ClassDef) else "function",
                    "name": node.name,
                    "signature": get_signature(node),
                    "docstring": docstring,
                    "module": get_module_path(file_path),
                    "line_start": node.lineno,
                })
    return chunks
```

### Chunk Structure
Each chunk should contain:
```python
@dataclass
class DocChunk:
    id: str                    # unique identifier
    content: str               # the actual text (docstring or section)
    chunk_type: str            # "function" | "class" | "method" | "tutorial_section"
    name: str                  # function/class name or section title
    module: str | None         # e.g., "ifcopenshell.util.element"
    signature: str | None      # for functions/methods
    source_file: str           # original file path
    line_start: int | None     # for traceability
    parent: str | None         # parent class for methods
```

---

## 3. Chunk Review & Question Generation

### Process (Claude via Haiku sub-agent)

For each extracted chunk:
1. **Review**: Check if the chunk is meaningful and complete
2. **Clean**: Fix any formatting issues, remove noise
3. **Generate questions**: Create 2-5 hypothetical questions that this chunk answers

### Prompt Template
```
You are reviewing documentation chunks for a RAG system about IfcOpenShell (a Python library for working with IFC/BIM files).

## Chunk to review:
Type: {chunk_type}
Name: {name}
Module: {module}
Signature: {signature}

Content:
{content}

## Tasks:
1. Is this chunk useful for answering user questions about IfcOpenShell? (yes/no)
2. If yes, generate 3-5 questions that a user might ask that this chunk would answer.
   - Questions should be natural (how users actually phrase things)
   - Cover different ways to ask about the same functionality
   - Include both specific ("How do I get all walls?") and conceptual ("How does element filtering work?")

## Output format (JSON):
{
  "useful": true/false,
  "reason": "why not useful" (only if false),
  "questions": ["question 1", "question 2", ...]
}
```

### Storage
Store both:
- Original chunk embedding
- Each generated question embedding (linked to chunk ID)

---

## 4. Embedding Model

### Choice: `all-mpnet-base-v2`
- 768 dimensions
- Best quality among sentence-transformers
- Pre-computing at index time eliminates speed concerns

```python
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-mpnet-base-v2')

def embed_chunk(chunk: DocChunk) -> np.ndarray:
    # Combine relevant fields for embedding
    text = f"{chunk.name}\n{chunk.signature or ''}\n{chunk.content}"
    return model.encode(text, convert_to_numpy=True)

def embed_questions(questions: list[str]) -> list[np.ndarray]:
    return model.encode(questions, convert_to_numpy=True)
```

---

## 5. Vector Storage

### Choice: `sqlite-vec`
- Embedded (no server)
- Separate file: `src/db/doc_vectors.db`
- Pure C, runs anywhere

### Schema
```sql
-- Chunks table
CREATE TABLE doc_chunks (
    id TEXT PRIMARY KEY,
    content TEXT NOT NULL,
    chunk_type TEXT NOT NULL,
    name TEXT NOT NULL,
    module TEXT,
    signature TEXT,
    source_file TEXT NOT NULL,
    line_start INTEGER,
    parent TEXT
);

-- Chunk embeddings (sqlite-vec virtual table)
CREATE VIRTUAL TABLE doc_chunk_embeddings USING vec0(
    chunk_id TEXT PRIMARY KEY,
    embedding FLOAT[768]
);

-- Generated questions
CREATE TABLE doc_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chunk_id TEXT NOT NULL REFERENCES doc_chunks(id),
    question TEXT NOT NULL
);

-- Question embeddings
CREATE VIRTUAL TABLE doc_question_embeddings USING vec0(
    question_id INTEGER PRIMARY KEY,
    embedding FLOAT[768]
);
```

### Installation
```bash
uv add sqlite-vec sentence-transformers
```

---

## 6. Retrieval Pipeline

### Query Flow
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

### Reranker: `ms-marco-MiniLM-L-6-v2`
```python
from sentence_transformers import CrossEncoder

reranker = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')

def retrieve(query: str, top_k: int = 5) -> str:
    query_emb = model.encode(query)

    # Search both tables
    chunk_results = search_chunk_embeddings(query_emb, limit=25)
    question_results = search_question_embeddings(query_emb, limit=25)

    # Dedupe by chunk_id, keep best score
    candidates = dedupe_by_chunk_id(chunk_results + question_results)

    # Rerank
    pairs = [(query, get_chunk_content(c.chunk_id)) for c in candidates]
    scores = reranker.predict(pairs)

    # Return top-k
    ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
    return format_results([c for c, s in ranked[:top_k]])
```

---

## 7. Implementation Plan

### Phase 1: Indexing Pipeline
1. Clone IfcOpenShell v0.8.2
2. Implement RST parser
3. Implement Python docstring extractor
4. Create chunk review sub-agent (Haiku)
5. Process all chunks, generate questions
6. Embed chunks and questions
7. Store in sqlite-vec

### Phase 2: Query Pipeline
1. Implement dual-search (chunks + questions)
2. Implement deduplication
3. Implement reranking
4. Integrate with existing tool (config switch)

### Phase 3: Evaluation
1. Run `run_evaluation.py` with `DOC_BACKEND="context7"`
2. Run `run_evaluation.py` with `DOC_BACKEND="custom"`
3. Compare results

---

## 8. Dependencies

```toml
# pyproject.toml additions
[project.dependencies]
sentence-transformers = ">=3.0.0"
sqlite-vec = ">=0.1.0"
docutils = ">=0.20"  # RST parsing
```

---

## 9. File Structure

```
src/
├── docs_indexer/
│   ├── __init__.py
│   ├── parser_rst.py        # RST file parsing
│   ├── parser_python.py     # Python docstring extraction
│   ├── chunk_reviewer.py    # Haiku sub-agent for review
│   ├── embedder.py          # Embedding logic
│   ├── indexer.py           # Main indexing orchestration
│   └── retriever.py         # Query pipeline
├── db/
│   └── doc_vectors.db       # Vector database (generated)
└── tools/
    └── initial/
        └── query_ifcopenshell_documentation.py  # Updated with config switch
```

---

## 10. Open Questions (Resolved)

| Question | Decision |
|----------|----------|
| Parse source vs scrape HTML? | Parse source files |
| Which modules to include? | All of them |
| Who generates questions? | Claude (Haiku sub-agent) |
| Version to use? | v0.8.2 (from pyproject.toml) |
| Vector DB location? | Separate file (`doc_vectors.db`) |

---

## Sources

- [IfcOpenShell GitHub](https://github.com/IfcOpenShell/IfcOpenShell)
- [sqlite-vec](https://github.com/asg017/sqlite-vec)
- [Sentence Transformers](https://www.sbert.net/docs/sentence_transformer/pretrained_models.html)
- [Hypothetical Questions vs HyDE](https://pixion.co/blog/rag-strategies-hypothetical-questions-hyde)
- [AST-based code chunking](https://github.com/yilinjz/astchunk)
- [Cross-encoder reranking](https://www.zeroentropy.dev/articles/ultimate-guide-to-choosing-the-best-reranking-model-in-2025)
