# Documentation Retrieval Pipeline

## Overview

`query_ifcopenshell_docs` is a hybrid documentation retrieval system that combines dense vector search, BM25 lexical search, reverse-question search, and cross-encoder reranking to retrieve relevant IfcOpenShell documentation chunks.

**Entry point**: `src/tools/initial/query_ifcopenshell_documentation.py`

---

## Algorithm (LaTeX)

```latex
\begin{algorithm}[t]
\caption{Documentation Retrieval Pipeline}
\label{alg:doc-retrieval}
\begin{algorithmic}[1]
\REQUIRE Query $q$, chunk collection $\mathcal{C}$, question collection $\mathcal{Q}$, BM25 index $\mathcal{B}$
\ENSURE Top-$k$ relevant documentation chunks
\STATE \textbf{Parameters:} $k{=}5$, $n{=}25$, $n_r{=}15$, $k_{\text{rrf}}{=}60$
\STATE \textbf{Models:} embed $=$ \texttt{qwen3-embedding:0.6b}, rerank $=$ \texttt{jina-reranker-v3}
\STATE $\mathbf{e}_q \gets \textsc{Embed}(q)$ \COMMENT{Dense query embedding, dim$=$1024}
\STATE $R_1 \gets \textsc{DenseSearch}(\mathcal{C}, \mathbf{e}_q, n)$ \COMMENT{Cosine similarity over chunk embeddings}
\STATE $R_2 \gets \textsc{BM25}(\mathcal{B}, q, n)$ \COMMENT{Lexical search with BM25-Okapi}
\STATE $R_3 \gets \textsc{DenseSearch}(\mathcal{Q}, \mathbf{e}_q, n)$ \COMMENT{Search over reverse questions}
\STATE $S \gets \emptyset$ \COMMENT{Reciprocal rank fusion}
\FOR{$R \in \{R_1, R_2, R_3\}$}
    \FOR{each document $d$ at rank $r$ in $R$}
        \STATE $S[d] \gets S[d] + \frac{1}{k_{\text{rrf}} + r}$
    \ENDFOR
\ENDFOR
\STATE $\mathcal{F} \gets \text{top-}n_r \text{ from } S \text{ by score}$ \COMMENT{Fusion candidates}
\STATE $\mathcal{F}^* \gets \textsc{Rerank}(q, \mathcal{F}, k)$ \COMMENT{Cross-encoder reranking, return top-$k$}
\RETURN $\mathcal{F}^*$
\end{algorithmic}
\end{algorithm}
```

---

## Parameters

| Parameter | Value | Source file |
|---|---|---|
| Embedding model | `qwen3-embedding:0.6b` (Ollama) | `src/docs_indexer/embedder.py:15` |
| Embedding dimension | 1024 | `src/docs_indexer/embedder.py:11` |
| Reranker model | `jina-reranker-v3-mlx` | `src/docs_indexer/retriever.py:16` |
| Dense vector store | ChromaDB (cosine HNSW) | `src/docs_indexer/storage.py:128` |
| Sparse index | `rank_bm25.BM25Okapi` | `src/docs_indexer/storage.py:12` |
| Search limit per method ($n$) | 25 | `src/docs_indexer/retriever.py:81` |
| RRF constant ($k_{\text{rrf}}$) | 60 | `src/docs_indexer/retriever.py:18` |
| Rerank candidates ($n_r$) | 15 | `src/docs_indexer/retriever.py:82` |
| Final top-$k$ | 5 | `src/docs_indexer/retriever.py:80` |

---

## Pipeline Details

### 1. Document Corpus and Chunking

The documentation corpus is the IfcOpenShell Python library source and its accompanying tutorials, cloned into `src/docs_indexer/external/ifcopenshell-docs/`.

Chunking is **semantic, not fixed-size** -- there is no chunk size or overlap parameter:

- **Python source files** (`parser_python.py`): AST-based extraction of docstrings per function, class, and method. Each chunk contains the function name, signature, and docstring as a self-contained unit.
- **RST tutorial files** (`parser_rst.py`): Split by section headers (detected via RST underline characters `=`, `-`, `~`, `^`). Each section becomes one chunk with its title and content.

### 2. Chunk Review and Reverse Question Generation

At index time, each chunk is reviewed by an LLM (Claude Haiku via BAML) in `chunk_reviewer.py`. The reviewer:

1. **Filters**: determines whether the chunk is useful for answering BIM-related queries (non-useful chunks are discarded).
2. **Generates reverse questions**: for each useful chunk, produces 3-5 hypothetical questions that a user might ask and that this chunk would answer.

These reverse questions are embedded separately and stored in a dedicated ChromaDB collection (`doc_questions`), enabling the third retrieval channel (line 6 in the algorithm). Results are cached to `src/db/doc_review_cache.json` to avoid redundant LLM calls on re-indexing.

### 3. Indexing

For each useful chunk:
- The chunk content (name + signature + content) is embedded with `qwen3-embedding:0.6b` and stored in ChromaDB (`doc_chunks` collection, cosine HNSW).
- Its reverse questions are embedded and stored in ChromaDB (`doc_questions` collection, cosine HNSW), with metadata linking back to the parent chunk.
- The chunk text is tokenized and added to a BM25-Okapi index (persisted as `src/db/bm25_index.pkl`).

### 4. Query-Time Retrieval

Given a user query $q$, the pipeline runs three retrieval channels:

1. **Dense chunk search** (line 4): embed $q$, retrieve top-25 from `doc_chunks` by cosine similarity.
2. **BM25 lexical search** (line 5): tokenize $q$, retrieve top-25 from the BM25 index by Okapi BM25 score.
3. **Dense question search** (line 6): embed $q$, retrieve top-25 from `doc_questions` by cosine similarity. Matches are mapped back to their parent chunk IDs.

### 5. Fusion

The three ranked lists are combined using **Reciprocal Rank Fusion** (RRF) with $k_{\text{rrf}} = 60$ (lines 8-12). For each document appearing in any list:

$$S[d] = \sum_{R} \frac{1}{k_{\text{rrf}} + \text{rank}_R(d)}$$

The top $n_r = 15$ candidates by RRF score are retained.

### 6. Reranking

The 15 fusion candidates are reranked using **Jina Reranker v3** (`jina-reranker-v3-mlx`, optimized for Apple Silicon). The reranker is a cross-encoder that scores each (query, document) pair. The top $k = 5$ chunks after reranking are returned.

### 7. Context Assembly

Retrieved chunks are formatted by `format_results()` in `retriever.py:230` as numbered markdown blocks:

```
## 1. function_name (module.path)
```python
def function_name(args) -> return_type
```
<chunk content>

---

## 2. next_function ...
```

This formatted string is printed to stdout by the `query_ifcopenshell_docs` tool (`src/tools/initial/query_ifcopenshell_documentation.py:109`), which the agent sees as tool output in its execution history.

---

## Storage

| Component | Path |
|---|---|
| ChromaDB | `src/db/chroma_docs/` |
| BM25 Index | `src/db/bm25_index.pkl` |
| Review Cache | `src/db/doc_review_cache.json` |

---

## Backend Selection

The tool supports two backends, selected via the `DOC_BACKEND` environment variable:

- `custom` (default): the local hybrid retrieval pipeline described above.
- `context7`: queries the Context7 API for IfcOpenShell documentation (library ID `/ifcopenshell/ifcopenshell`). Used as the external baseline in the evaluation matrix.

---

## MLflow Tracing

All retrieval steps are traced with nested spans:
- `query_ifcopenshell_docs` (parent)
  - `embed_query`, `dense_search`, `bm25_search`, `question_search`, `rrf_fusion`, `reranking`
