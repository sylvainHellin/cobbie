"""SQLite-vec storage for documentation chunks and embeddings."""

import sqlite3
import struct
from pathlib import Path

import numpy as np
import sqlite_vec

from src.docs_indexer.embedder import EMBEDDING_DIM
from src.docs_indexer.models import DocChunk

# Default database path
DEFAULT_DB_PATH = Path("src/db/doc_vectors.db")


def _serialize_f32(vector: np.ndarray) -> bytes:
    """Serialize a numpy array to bytes for sqlite-vec."""
    return struct.pack(f"{len(vector)}f", *vector.astype(np.float32))


def _deserialize_f32(data: bytes) -> np.ndarray:
    """Deserialize bytes to a numpy array."""
    return np.array(struct.unpack(f"{len(data) // 4}f", data), dtype=np.float32)


class DocVectorStore:
    """Vector store for documentation chunks using sqlite-vec."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with sqlite-vec loaded."""
        conn = sqlite3.connect(str(self.db_path))
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn

    def _init_db(self):
        """Initialize the database schema."""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Create chunks table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS doc_chunks (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                chunk_type TEXT NOT NULL,
                name TEXT NOT NULL,
                module TEXT,
                signature TEXT,
                source_file TEXT NOT NULL,
                line_start INTEGER,
                parent TEXT
            )
        """)

        # Create questions table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS doc_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chunk_id TEXT NOT NULL REFERENCES doc_chunks(id),
                question TEXT NOT NULL
            )
        """)

        # Create chunk embeddings virtual table
        cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunk_embeddings USING vec0(
                chunk_id TEXT PRIMARY KEY,
                embedding FLOAT[{EMBEDDING_DIM}]
            )
        """)

        # Create question embeddings virtual table
        cursor.execute(f"""
            CREATE VIRTUAL TABLE IF NOT EXISTS doc_question_embeddings USING vec0(
                question_id INTEGER PRIMARY KEY,
                embedding FLOAT[{EMBEDDING_DIM}]
            )
        """)

        conn.commit()
        conn.close()

    def clear(self):
        """Clear all data from the database."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM doc_question_embeddings")
        cursor.execute("DELETE FROM doc_chunk_embeddings")
        cursor.execute("DELETE FROM doc_questions")
        cursor.execute("DELETE FROM doc_chunks")

        conn.commit()
        conn.close()

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
        conn = self._get_connection()
        cursor = conn.cursor()

        # Insert chunk metadata
        cursor.execute(
            """
            INSERT OR REPLACE INTO doc_chunks
            (id, content, chunk_type, name, module, signature, source_file, line_start, parent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chunk.id,
                chunk.content,
                chunk.chunk_type,
                chunk.name,
                chunk.module,
                chunk.signature,
                chunk.source_file,
                chunk.line_start,
                chunk.parent,
            ),
        )

        # Insert chunk embedding
        cursor.execute(
            "INSERT OR REPLACE INTO doc_chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
            (chunk.id, _serialize_f32(embedding)),
        )

        # Insert question embeddings if provided
        if question_embeddings:
            for question_text, q_embedding in question_embeddings:
                cursor.execute(
                    "INSERT INTO doc_questions (chunk_id, question) VALUES (?, ?)",
                    (chunk.id, question_text),
                )
                question_id = cursor.lastrowid
                cursor.execute(
                    "INSERT INTO doc_question_embeddings (question_id, embedding) VALUES (?, ?)",
                    (question_id, _serialize_f32(q_embedding)),
                )

        conn.commit()
        conn.close()

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
        conn = self._get_connection()
        cursor = conn.cursor()

        for i, chunk in enumerate(chunks):
            # Insert chunk metadata
            cursor.execute(
                """
                INSERT OR REPLACE INTO doc_chunks
                (id, content, chunk_type, name, module, signature, source_file, line_start, parent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    chunk.id,
                    chunk.content,
                    chunk.chunk_type,
                    chunk.name,
                    chunk.module,
                    chunk.signature,
                    chunk.source_file,
                    chunk.line_start,
                    chunk.parent,
                ),
            )

            # Insert chunk embedding
            cursor.execute(
                "INSERT OR REPLACE INTO doc_chunk_embeddings (chunk_id, embedding) VALUES (?, ?)",
                (chunk.id, _serialize_f32(embeddings[i])),
            )

            # Insert question embeddings if provided
            if all_question_embeddings and i < len(all_question_embeddings):
                for question_text, q_embedding in all_question_embeddings[i]:
                    cursor.execute(
                        "INSERT INTO doc_questions (chunk_id, question) VALUES (?, ?)",
                        (chunk.id, question_text),
                    )
                    question_id = cursor.lastrowid
                    cursor.execute(
                        "INSERT INTO doc_question_embeddings (question_id, embedding) VALUES (?, ?)",
                        (question_id, _serialize_f32(q_embedding)),
                    )

        conn.commit()
        conn.close()

    def search_chunks(
        self, query_embedding: np.ndarray, limit: int = 25
    ) -> list[tuple[str, float]]:
        """Search for similar chunks by embedding.

        Args:
            query_embedding: Query vector of shape (EMBEDDING_DIM,)
            limit: Maximum number of results

        Returns:
            List of (chunk_id, distance) tuples, sorted by distance ascending
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT chunk_id, distance
            FROM doc_chunk_embeddings
            WHERE embedding MATCH ?
            AND k = ?
            """,
            (_serialize_f32(query_embedding), limit),
        )

        results = cursor.fetchall()
        conn.close()
        return results

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
        conn = self._get_connection()
        cursor = conn.cursor()

        # First get question matches from vec0
        cursor.execute(
            """
            SELECT question_id, distance
            FROM doc_question_embeddings
            WHERE embedding MATCH ?
            AND k = ?
            """,
            (_serialize_f32(query_embedding), limit),
        )
        question_results = cursor.fetchall()

        if not question_results:
            conn.close()
            return []

        # Then join with questions table to get chunk_ids
        question_ids = [r[0] for r in question_results]
        distances = {r[0]: r[1] for r in question_results}

        placeholders = ",".join("?" * len(question_ids))
        cursor.execute(
            f"""
            SELECT id, chunk_id FROM doc_questions
            WHERE id IN ({placeholders})
            """,
            question_ids,
        )

        results = [(row[1], distances[row[0]]) for row in cursor.fetchall()]
        conn.close()

        # Sort by distance
        results.sort(key=lambda x: x[1])
        return results

    def get_chunk_by_id(self, chunk_id: str) -> DocChunk | None:
        """Retrieve a chunk by its ID."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT id, content, chunk_type, name, module, signature,
                   source_file, line_start, parent
            FROM doc_chunks
            WHERE id = ?
            """,
            (chunk_id,),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            return DocChunk(
                id=row[0],
                content=row[1],
                chunk_type=row[2],
                name=row[3],
                module=row[4],
                signature=row[5],
                source_file=row[6],
                line_start=row[7],
                parent=row[8],
            )
        return None

    def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[DocChunk]:
        """Retrieve multiple chunks by their IDs."""
        conn = self._get_connection()
        cursor = conn.cursor()

        placeholders = ",".join("?" * len(chunk_ids))
        cursor.execute(
            f"""
            SELECT id, content, chunk_type, name, module, signature,
                   source_file, line_start, parent
            FROM doc_chunks
            WHERE id IN ({placeholders})
            """,
            chunk_ids,
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            DocChunk(
                id=row[0],
                content=row[1],
                chunk_type=row[2],
                name=row[3],
                module=row[4],
                signature=row[5],
                source_file=row[6],
                line_start=row[7],
                parent=row[8],
            )
            for row in rows
        ]

    def count_chunks(self) -> int:
        """Count total number of chunks in the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM doc_chunks")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def count_questions(self) -> int:
        """Count total number of questions in the database."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM doc_questions")
        count = cursor.fetchone()[0]
        conn.close()
        return count


if __name__ == "__main__":
    # Test storage
    import tempfile

    from src.docs_indexer.embedder import embed_chunk, embed_text

    # Create temp database for testing
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        test_db = Path(f.name)

    store = DocVectorStore(test_db)

    # Create a test chunk
    chunk = DocChunk(
        id="test_001",
        content="This is a test documentation chunk about getting walls.",
        chunk_type="function",
        name="get_walls",
        source_file="test.py",
        module="test.module",
        signature="def get_walls(model) -> list",
        line_start=10,
    )

    # Embed and store
    embedding = embed_chunk(chunk)
    questions = [
        "How do I get all walls?",
        "What function retrieves walls from a model?",
    ]
    question_embeddings = [(q, embed_text(q)) for q in questions]

    store.insert_chunk(chunk, embedding, question_embeddings)

    print(f"Stored chunk. Total chunks: {store.count_chunks()}")
    print(f"Total questions: {store.count_questions()}")

    # Search
    query = "get walls from IFC"
    query_emb = embed_text(query)

    chunk_results = store.search_chunks(query_emb, limit=5)
    print(f"\nChunk search results: {chunk_results}")

    question_results = store.search_questions(query_emb, limit=5)
    print(f"Question search results: {question_results}")

    # Retrieve
    retrieved = store.get_chunk_by_id("test_001")
    print(f"\nRetrieved chunk: {retrieved.name if retrieved else None}")

    # Cleanup
    test_db.unlink()
    print("\nTest passed!")
