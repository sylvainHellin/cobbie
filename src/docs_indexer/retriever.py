"""Retrieval pipeline for documentation queries."""

from sentence_transformers import CrossEncoder

from src.docs_indexer.embedder import embed_text
from src.docs_indexer.models import DocChunk
from src.docs_indexer.storage import DEFAULT_DB_PATH, DocVectorStore

# Reranker model
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

# Global reranker instance (lazy loaded)
_reranker: CrossEncoder | None = None


def get_reranker() -> CrossEncoder:
    """Get or create the reranker model instance."""
    global _reranker
    if _reranker is None:
        print(f"Loading reranker model: {RERANKER_MODEL}...")
        _reranker = CrossEncoder(RERANKER_MODEL)
        print("Reranker loaded.")
    return _reranker


def retrieve(
    query: str,
    top_k: int = 5,
    search_limit: int = 25,
    store: DocVectorStore | None = None,
    use_reranking: bool = True,
) -> list[DocChunk]:
    """Retrieve relevant documentation chunks for a query.

    Args:
        query: User query string
        top_k: Number of final results to return
        search_limit: Number of candidates to retrieve before reranking
        store: Optional DocVectorStore instance (creates default if None)
        use_reranking: Whether to apply cross-encoder reranking

    Returns:
        List of DocChunk objects, ranked by relevance
    """
    if store is None:
        store = DocVectorStore(DEFAULT_DB_PATH)

    # Embed query
    query_embedding = embed_text(query)

    # Search both chunks and questions
    chunk_results = store.search_chunks(query_embedding, limit=search_limit)
    question_results = store.search_questions(query_embedding, limit=search_limit)

    # Dedupe by chunk_id, keeping best score
    chunk_scores: dict[str, float] = {}
    for chunk_id, distance in chunk_results:
        if chunk_id not in chunk_scores or distance < chunk_scores[chunk_id]:
            chunk_scores[chunk_id] = distance

    for chunk_id, distance in question_results:
        if chunk_id not in chunk_scores or distance < chunk_scores[chunk_id]:
            chunk_scores[chunk_id] = distance

    if not chunk_scores:
        return []

    # Get unique chunk IDs sorted by score
    sorted_ids = sorted(chunk_scores.keys(), key=lambda x: chunk_scores[x])

    # Retrieve chunk objects
    chunks = store.get_chunks_by_ids(sorted_ids)
    chunk_map = {c.id: c for c in chunks}
    sorted_chunks = [chunk_map[cid] for cid in sorted_ids if cid in chunk_map]

    if not use_reranking:
        return sorted_chunks[:top_k]

    # Rerank with cross-encoder
    reranker = get_reranker()
    pairs = [(query, chunk.content) for chunk in sorted_chunks]
    scores = reranker.predict(pairs)

    # Sort by reranker score (higher is better)
    ranked = sorted(zip(sorted_chunks, scores), key=lambda x: x[1], reverse=True)

    return [chunk for chunk, _ in ranked[:top_k]]


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

    db_path = Path("src/db/doc_vectors.db")
    if not db_path.exists():
        print("Database not found. Run indexer first.")
    else:
        store = DocVectorStore(db_path)
        print(f"Database has {store.count_chunks()} chunks")

        query = "How do I get all walls from an IFC file?"
        print(f"\nQuery: {query}")

        results = retrieve(query, top_k=3, store=store)
        print(f"\nFound {len(results)} results:")

        for chunk in results:
            print(f"\n- {chunk.name} ({chunk.chunk_type})")
            print(f"  {chunk.content[:100]}...")
