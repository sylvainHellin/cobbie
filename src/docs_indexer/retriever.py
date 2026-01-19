"""Hybrid retrieval pipeline: dense + BM25 + RRF fusion + reranking."""

import sys
import time
from typing import Any

import mlflow

from src.docs_indexer.embedder import embed_text
from src.docs_indexer.models import DocChunk
from src.docs_indexer.storage import DEFAULT_DB_PATH, DocVectorStore
from src.util.python_executor import count_tokens

# Jina reranker v3 MLX - optimized for Apple Silicon
RERANKER_MODEL = "jinaai/jina-reranker-v3-mlx"

# RRF constant (commonly k=60)
RRF_K = 60

# Global reranker instance (lazy loaded)
_reranker: Any = None


def get_reranker() -> Any:
    """Get or create the Jina reranker v3 MLX model instance."""
    global _reranker
    if _reranker is None:
        from huggingface_hub import snapshot_download

        print(f"Loading reranker model: {RERANKER_MODEL} (MLX)...")

        # Download and get model path
        model_path = snapshot_download(RERANKER_MODEL)

        # Add model path to sys.path to import rerank module
        if model_path not in sys.path:
            sys.path.insert(0, model_path)

        from rerank import MLXReranker  # type: ignore[import-not-found]

        _reranker = MLXReranker(
            model_path=model_path,
            projector_path=f"{model_path}/projector.safetensors",
        )
        print("Reranker loaded.")
    return _reranker


def reciprocal_rank_fusion(
    ranked_lists: list[list[tuple[str, float]]],
    k: int = RRF_K,
) -> list[tuple[str, float]]:
    """Combine multiple ranked lists using Reciprocal Rank Fusion.

    RRF score for document d = sum over all lists of: 1 / (k + rank(d))

    Args:
        ranked_lists: List of ranked results, each is [(id, score), ...]
                     For dense search, lower score is better (distance)
                     For BM25, higher score is better
        k: RRF constant, typically 60

    Returns:
        Combined ranking as [(id, rrf_score), ...], sorted by RRF score descending
    """
    rrf_scores: dict[str, float] = {}

    for ranked_list in ranked_lists:
        for rank, (doc_id, _) in enumerate(ranked_list, start=1):
            rrf_scores[doc_id] = rrf_scores.get(doc_id, 0) + 1 / (k + rank)

    # Sort by RRF score descending
    sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_results


def retrieve(
    query: str,
    top_k: int = 5,
    search_limit: int = 25,
    rerank_limit: int = 15,
    store: DocVectorStore | None = None,
    use_reranking: bool = True,
    use_hybrid: bool = True,
) -> list[DocChunk]:
    """Retrieve relevant documentation chunks using hybrid search.

    Pipeline:
    1. Dense embedding search (via ChromaDB)
    2. BM25 lexical search
    3. Question embedding search
    4. RRF fusion of all results
    5. Jina reranker v3 reranking (optional)

    When running within an MLflow trace context, logs intermediate
    steps to spans for debugging and analysis.

    Args:
        query: User query string
        top_k: Number of final results to return
        search_limit: Number of candidates to retrieve per method
        rerank_limit: Max candidates to pass to reranker (default 15 for speed)
        store: Optional DocVectorStore instance (creates default if None)
        use_reranking: Whether to apply reranking
        use_hybrid: Whether to use hybrid search (dense + BM25)

    Returns:
        List of DocChunk objects, ranked by relevance
    """
    with mlflow.start_span(name="hybrid_retrieval", span_type="CHAIN") as retrieval_span:
        retrieval_span.set_inputs({"query": query, "top_k": top_k})

        if store is None:
            store = DocVectorStore(DEFAULT_DB_PATH)

        # 1. Embed query
        with mlflow.start_span(name="embed_query", span_type="TOOL") as embed_span:
            t0 = time.time()
            query_embedding = embed_text(query)
            embed_span.set_attributes({"duration_ms": (time.time() - t0) * 1000})

        ranked_lists: list[list[tuple[str, float]]] = []

        # 2. Dense chunk search
        with mlflow.start_span(name="dense_search", span_type="TOOL") as dense_span:
            t0 = time.time()
            chunk_results = store.search_chunks(query_embedding, limit=search_limit)
            if chunk_results:
                ranked_lists.append(chunk_results)
            dense_span.set_outputs({
                "num_results": len(chunk_results) if chunk_results else 0,
                "top_5_ids": [id for id, _ in (chunk_results or [])[:5]],
            })
            dense_span.set_attributes({"duration_ms": (time.time() - t0) * 1000})

        # 3. BM25 lexical search
        if use_hybrid:
            with mlflow.start_span(name="bm25_search", span_type="TOOL") as bm25_span:
                t0 = time.time()
                bm25_results = store.search_bm25(query, limit=search_limit)
                if bm25_results:
                    ranked_lists.append(bm25_results)
                bm25_span.set_outputs({
                    "num_results": len(bm25_results) if bm25_results else 0,
                    "top_5_ids": [id for id, _ in (bm25_results or [])[:5]],
                })
                bm25_span.set_attributes({"duration_ms": (time.time() - t0) * 1000})

        # 4. Question embedding search
        with mlflow.start_span(name="question_search", span_type="TOOL") as question_span:
            t0 = time.time()
            question_results = store.search_questions(query_embedding, limit=search_limit)
            if question_results:
                ranked_lists.append(question_results)
            question_span.set_outputs({
                "num_results": len(question_results) if question_results else 0,
                "top_5_ids": [id for id, _ in (question_results or [])[:5]],
            })
            question_span.set_attributes({"duration_ms": (time.time() - t0) * 1000})

        if not ranked_lists:
            retrieval_span.set_outputs({"num_results": 0, "total_tokens": 0})
            return []

        # 5. RRF fusion
        with mlflow.start_span(name="rrf_fusion", span_type="TOOL") as rrf_span:
            t0 = time.time()
            fused_results = reciprocal_rank_fusion(ranked_lists)
            candidate_ids = [doc_id for doc_id, _ in fused_results][:rerank_limit]
            chunks = store.get_chunks_by_ids(candidate_ids)
            chunk_map = {c.id: c for c in chunks}
            sorted_chunks = [chunk_map[cid] for cid in candidate_ids if cid in chunk_map]

            rrf_tokens = sum(count_tokens(c.content) for c in sorted_chunks)

            rrf_span.set_outputs({
                "num_candidates": len(sorted_chunks),
                "candidate_names": [c.name for c in sorted_chunks[:5]],
            })
            rrf_span.set_attributes({
                "duration_ms": (time.time() - t0) * 1000,
                "total_tokens": rrf_tokens,
            })

        if not use_reranking:
            final_chunks = sorted_chunks[:top_k]
            final_tokens = sum(count_tokens(c.content) for c in final_chunks)
            retrieval_span.set_outputs({
                "num_results": len(final_chunks),
                "result_names": [c.name for c in final_chunks],
            })
            retrieval_span.set_attributes({"total_tokens": final_tokens})
            return final_chunks

        # 6. Reranking
        with mlflow.start_span(name="reranking", span_type="TOOL") as rerank_span:
            t0 = time.time()
            reranker = get_reranker()
            documents = [chunk.content for chunk in sorted_chunks]
            rankings = reranker.rerank(query, documents, top_n=top_k)
            final_chunks = [sorted_chunks[r["index"]] for r in rankings]

            final_tokens = sum(count_tokens(c.content) for c in final_chunks)

            rerank_span.set_outputs({
                "result_names": [c.name for c in final_chunks],
                "scores": [f"{r['relevance_score']:.4f}" for r in rankings],
            })
            rerank_span.set_attributes({
                "duration_ms": (time.time() - t0) * 1000,
                "reranker_model": RERANKER_MODEL,
                "total_tokens": final_tokens,
            })

        retrieval_span.set_outputs({
            "num_results": len(final_chunks),
            "result_names": [c.name for c in final_chunks],
        })
        retrieval_span.set_attributes({"total_tokens": final_tokens})

        return final_chunks


def format_results(chunks: list[DocChunk]) -> str:
    """Format retrieved chunks as a string for display.

    Args:
        chunks: List of DocChunk objects

    Returns:
        Formatted string with chunk contents
    """
    if not chunks:
        return "No relevant documentation found."

    parts = []
    for i, chunk in enumerate(chunks, 1):
        header = f"## {i}. {chunk.name}"
        if chunk.module:
            header += f" ({chunk.module})"

        content = []
        content.append(header)
        if chunk.signature:
            content.append(f"```python\n{chunk.signature}\n```")
        content.append(chunk.content)
        parts.append("\n".join(content))

    return "\n\n---\n\n".join(parts)


def query_docs(query: str, top_k: int = 5) -> str:
    """Query documentation and return formatted results.

    This is the main entry point for the documentation query tool.

    Args:
        query: User query string
        top_k: Number of results to return

    Returns:
        Formatted documentation string
    """
    chunks = retrieve(query, top_k=top_k)
    return format_results(chunks)


if __name__ == "__main__":
    # Test retrieval
    from pathlib import Path

    db_path = Path("src/db/chroma_docs")
    if not db_path.exists():
        print("Database not found. Run indexer first.")
    else:
        store = DocVectorStore(db_path)
        print(f"Database has {store.count_chunks()} chunks")
        print(f"BM25 index has {store.bm25_index.count()} documents")

        query = "How do I get all walls from an IFC file?"
        print(f"\nQuery: {query}")

        # Test without reranking first (faster)
        print("\n--- Without reranking ---")
        results = retrieve(query, top_k=3, store=store, use_reranking=False)
        print(f"Found {len(results)} results:")
        for chunk in results:
            print(f"  - {chunk.name} ({chunk.chunk_type})")

        # Test with reranking
        print("\n--- With reranking ---")
        results = retrieve(query, top_k=3, store=store, use_reranking=True)
        print(f"Found {len(results)} results:")
        for chunk in results:
            print(f"  - {chunk.name} ({chunk.chunk_type})")
            print(f"    {chunk.content[:100]}...")
