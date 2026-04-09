"""Hybrid storage for documentation chunks: ChromaDB (dense) + BM25 (sparse)."""

import pickle
import re
from pathlib import Path
from typing import cast

import chromadb
import numpy as np
from chromadb.config import Settings
from rank_bm25 import BM25Okapi

from src.docs_indexer.models import ChunkType, DocChunk

# Default database paths
DEFAULT_DB_PATH = Path("src/db/chroma_docs")
DEFAULT_BM25_PATH = Path("src/db/bm25_index.pkl")


def tokenize(text: str) -> list[str]:
    """Simple tokenizer for BM25."""
    # Lowercase and split on non-alphanumeric characters
    text = text.lower()
    tokens = re.findall(r"\b\w+\b", text)
    return tokens


class BM25Index:
    """BM25 index for lexical search."""

    def __init__(self, index_path: Path | str = DEFAULT_BM25_PATH):
        self.index_path = Path(index_path)
        self.bm25: BM25Okapi | None = None
        self.chunk_ids: list[str] = []
        self.corpus: list[list[str]] = []

        # Load existing index if available
        if self.index_path.exists():
            self._load()

    def _load(self):
        """Load BM25 index from disk."""
        with open(self.index_path, "rb") as f:
            data = pickle.load(f)
            self.chunk_ids = data["chunk_ids"]
            self.corpus = data["corpus"]
            if self.corpus:
                self.bm25 = BM25Okapi(self.corpus)

    def _save(self):
        """Save BM25 index to disk."""
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.index_path, "wb") as f:
            pickle.dump({"chunk_ids": self.chunk_ids, "corpus": self.corpus}, f)

    def clear(self):
        """Clear the index."""
        self.bm25 = None
        self.chunk_ids = []
        self.corpus = []
        if self.index_path.exists():
            self.index_path.unlink()

    def build(self, chunks: list[DocChunk]):
        """Build BM25 index from chunks.

        Args:
            chunks: List of DocChunk objects to index
        """
        self.chunk_ids = [chunk.id for chunk in chunks]
        # Combine name, signature, and content for better lexical matching
        self.corpus = [tokenize(chunk.to_embedding_text()) for chunk in chunks]
        self.bm25 = BM25Okapi(self.corpus)
        self._save()

    def search(self, query: str, limit: int = 25) -> list[tuple[str, float]]:
        """Search for chunks using BM25.

        Args:
            query: Query string
            limit: Maximum number of results

        Returns:
            List of (chunk_id, score) tuples, sorted by score descending
        """
        if self.bm25 is None or not self.chunk_ids:
            return []

        query_tokens = tokenize(query)
        scores = self.bm25.get_scores(query_tokens)

        # Get top-k indices
        top_indices = np.argsort(scores)[::-1][:limit]

        results = []
        for idx in top_indices:
            if scores[idx] > 0:  # Only include non-zero scores
                results.append((self.chunk_ids[idx], float(scores[idx])))

        return results

    def count(self) -> int:
        """Return number of indexed documents."""
        return len(self.chunk_ids)


class DocVectorStore:
    """Hybrid vector store: ChromaDB for dense embeddings + BM25 for lexical search."""

    def __init__(
        self,
        db_path: Path | str = DEFAULT_DB_PATH,
        bm25_path: Path | str = DEFAULT_BM25_PATH,
    ):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize persistent ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(anonymized_telemetry=False),
        )

        # Create collections for chunks and questions.
        # sync_threshold=100 ensures the HNSW segment is fully flushed to disk
        # (default 1000 leaves small collections only partially persisted in the WAL,
        # which causes "HNSW segment reader: Nothing found on disk" errors on cold start).
        self.chunks_collection = self.client.get_or_create_collection(
            name="doc_chunks",
            metadata={"hnsw:space": "cosine", "hnsw:sync_threshold": 100},
        )
        self.questions_collection = self.client.get_or_create_collection(
            name="doc_questions",
            metadata={"hnsw:space": "cosine", "hnsw:sync_threshold": 100},
        )

        # Initialize BM25 index
        self.bm25_index = BM25Index(bm25_path)

    def clear(self):
        """Clear all data from the collections and BM25 index."""
        # Delete and recreate ChromaDB collections
        self.client.delete_collection("doc_chunks")
        self.client.delete_collection("doc_questions")

        self.chunks_collection = self.client.create_collection(
            name="doc_chunks",
            metadata={"hnsw:space": "cosine"},
        )
        self.questions_collection = self.client.create_collection(
            name="doc_questions",
            metadata={"hnsw:space": "cosine"},
        )

        # Clear BM25 index
        self.bm25_index.clear()

    def insert_chunk(
        self,
        chunk: DocChunk,
        embedding: np.ndarray,
        question_embeddings: list[tuple[str, np.ndarray]] | None = None,
    ):
        """Insert a chunk with its embedding and optional question embeddings.

        Args:
            chunk: The documentation chunk
            embedding: The chunk's embedding vector
            question_embeddings: List of (question_text, embedding) tuples
        """
        # Insert chunk with embedding
        self.chunks_collection.add(
            ids=[chunk.id],
            embeddings=[embedding.tolist()],
            metadatas=[
                {
                    "name": chunk.name,
                    "chunk_type": chunk.chunk_type,
                    "module": chunk.module or "",
                    "signature": chunk.signature or "",
                    "source_file": chunk.source_file,
                    "line_start": chunk.line_start or 0,
                    "parent": chunk.parent or "",
                }
            ],
            documents=[chunk.content],
        )

        # Insert question embeddings if provided
        if question_embeddings:
            for idx, (question_text, q_embedding) in enumerate(question_embeddings):
                question_id = f"{chunk.id}_q{idx}"
                self.questions_collection.add(
                    ids=[question_id],
                    embeddings=[q_embedding.tolist()],
                    metadatas=[{"chunk_id": chunk.id}],
                    documents=[question_text],
                )

    def insert_chunks_batch(
        self,
        chunks: list[DocChunk],
        embeddings: np.ndarray,
        all_question_embeddings: list[list[tuple[str, np.ndarray]]] | None = None,
    ):
        """Insert multiple chunks with their embeddings.

        Args:
            chunks: List of documentation chunks
            embeddings: Array of shape (len(chunks), EMBEDDING_DIM)
            all_question_embeddings: List of question embeddings per chunk
        """
        # Prepare batch data for chunks
        ids = [chunk.id for chunk in chunks]
        emb_list = [embeddings[i].tolist() for i in range(len(chunks))]
        metadatas: list[dict[str, str | int]] = [
            {
                "name": chunk.name,
                "chunk_type": chunk.chunk_type,
                "module": chunk.module or "",
                "signature": chunk.signature or "",
                "source_file": chunk.source_file,
                "line_start": chunk.line_start or 0,
                "parent": chunk.parent or "",
            }
            for chunk in chunks
        ]
        documents = [chunk.content for chunk in chunks]

        # Insert chunks in batch
        self.chunks_collection.add(
            ids=ids,
            embeddings=emb_list,
            metadatas=metadatas,  # type: ignore[arg-type]
            documents=documents,
        )

        # Insert questions in batch
        if all_question_embeddings:
            q_ids = []
            q_embeddings = []
            q_metadatas = []
            q_documents = []

            for i, chunk in enumerate(chunks):
                if i < len(all_question_embeddings):
                    for q_idx, (question_text, q_embedding) in enumerate(
                        all_question_embeddings[i]
                    ):
                        q_ids.append(f"{chunk.id}_q{q_idx}")
                        q_embeddings.append(q_embedding.tolist())
                        q_metadatas.append({"chunk_id": chunk.id})
                        q_documents.append(question_text)

            if q_ids:
                self.questions_collection.add(
                    ids=q_ids,
                    embeddings=q_embeddings,
                    metadatas=q_metadatas,
                    documents=q_documents,
                )

        # Build BM25 index
        self.bm25_index.build(chunks)

    def search_chunks(
        self, query_embedding: np.ndarray, limit: int = 25
    ) -> list[tuple[str, float]]:
        """Search for similar chunks by dense embedding.

        Args:
            query_embedding: Query vector of shape (EMBEDDING_DIM,)
            limit: Maximum number of results

        Returns:
            List of (chunk_id, distance) tuples, sorted by distance ascending
        """
        results = self.chunks_collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=limit,
            include=["distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        # Combine ids and distances
        ids = results["ids"][0]
        distances = results["distances"][0] if results["distances"] else [0.0] * len(ids)

        return list(zip(ids, distances))

    def search_bm25(self, query: str, limit: int = 25) -> list[tuple[str, float]]:
        """Search for similar chunks using BM25 lexical search.

        Args:
            query: Query string
            limit: Maximum number of results

        Returns:
            List of (chunk_id, score) tuples, sorted by score descending
        """
        return self.bm25_index.search(query, limit)

    def search_questions(
        self, query_embedding: np.ndarray, limit: int = 25
    ) -> list[tuple[str, float]]:
        """Search for similar questions by embedding.

        Args:
            query_embedding: Query vector of shape (EMBEDDING_DIM,)
            limit: Maximum number of results

        Returns:
            List of (chunk_id, distance) tuples, sorted by distance ascending
        """
        results = self.questions_collection.query(
            query_embeddings=[query_embedding.tolist()],
            n_results=limit,
            include=["metadatas", "distances"],
        )

        if not results["ids"] or not results["ids"][0]:
            return []

        # Extract chunk_ids from metadata
        metadatas = results["metadatas"][0] if results["metadatas"] else []
        distances = results["distances"][0] if results["distances"] else []

        chunk_results = []
        for i, metadata in enumerate(metadatas):
            chunk_id = metadata.get("chunk_id", "")
            distance = distances[i] if i < len(distances) else 0.0
            chunk_results.append((chunk_id, distance))

        return chunk_results

    def get_chunk_by_id(self, chunk_id: str) -> DocChunk | None:
        """Retrieve a chunk by its ID."""
        results = self.chunks_collection.get(
            ids=[chunk_id],
            include=["metadatas", "documents"],
        )

        if not results["ids"]:
            return None

        metadata = results["metadatas"][0] if results["metadatas"] else {}
        document = results["documents"][0] if results["documents"] else ""

        return DocChunk(
            id=chunk_id,
            content=cast(str, document),
            chunk_type=cast(ChunkType, metadata.get("chunk_type", "function")),
            name=cast(str, metadata.get("name", "")),
            module=cast(str | None, metadata.get("module") or None),
            signature=cast(str | None, metadata.get("signature") or None),
            source_file=cast(str, metadata.get("source_file", "")),
            line_start=cast(int | None, metadata.get("line_start") or None),
            parent=cast(str | None, metadata.get("parent") or None),
        )

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[DocChunk]:
        """Retrieve multiple chunks by their IDs."""
        if not chunk_ids:
            return []

        results = self.chunks_collection.get(
            ids=chunk_ids,
            include=["metadatas", "documents"],
        )

        if not results["ids"]:
            return []

        chunks = []
        for i, chunk_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if results["metadatas"] else {}
            document = results["documents"][i] if results["documents"] else ""

            chunks.append(
                DocChunk(
                    id=chunk_id,
                    content=cast(str, document),
                    chunk_type=cast(ChunkType, metadata.get("chunk_type", "function")),
                    name=cast(str, metadata.get("name", "")),
                    module=cast(str | None, metadata.get("module") or None),
                    signature=cast(str | None, metadata.get("signature") or None),
                    source_file=cast(str, metadata.get("source_file", "")),
                    line_start=cast(int | None, metadata.get("line_start") or None),
                    parent=cast(str | None, metadata.get("parent") or None),
                )
            )

        return chunks

    def count_chunks(self) -> int:
        """Count total number of chunks in the database."""
        return self.chunks_collection.count()

    def count_questions(self) -> int:
        """Count total number of questions in the database."""
        return self.questions_collection.count()


if __name__ == "__main__":
    # Test storage
    import tempfile

    from src.docs_indexer.embedder import embed_chunk, embed_text

    # Create temp database for testing
    with tempfile.TemporaryDirectory() as tmpdir:
        test_db = Path(tmpdir) / "test_chroma"
        test_bm25 = Path(tmpdir) / "test_bm25.pkl"

        store = DocVectorStore(test_db, test_bm25)

        # Create test chunks
        chunks = [
            DocChunk(
                id="test_001",
                content="This is a test documentation chunk about getting walls.",
                chunk_type="function",
                name="get_walls",
                source_file="test.py",
                module="test.module",
                signature="def get_walls(model) -> list",
                line_start=10,
            ),
            DocChunk(
                id="test_002",
                content="This function retrieves all windows from an IFC model.",
                chunk_type="function",
                name="get_windows",
                source_file="test.py",
                module="test.module",
                signature="def get_windows(model) -> list",
                line_start=20,
            ),
        ]

        # Embed and store
        embeddings = np.array([embed_chunk(c) for c in chunks])
        store.insert_chunks_batch(chunks, embeddings)

        print(f"Stored {store.count_chunks()} chunks")
        print(f"BM25 index has {store.bm25_index.count()} documents")

        # Test dense search
        query = "get walls from IFC"
        query_emb = embed_text(query)

        dense_results = store.search_chunks(query_emb, limit=5)
        print(f"\nDense search results: {dense_results}")

        # Test BM25 search
        bm25_results = store.search_bm25(query, limit=5)
        print(f"BM25 search results: {bm25_results}")

        # Retrieve
        retrieved = store.get_chunk_by_id("test_001")
        print(f"\nRetrieved chunk: {retrieved.name if retrieved else None}")

        print("\nTest passed!")
