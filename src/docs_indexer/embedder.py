"""Embedding module using sentence-transformers."""

import numpy as np
from sentence_transformers import SentenceTransformer

from src.docs_indexer.models import DocChunk

# Default embedding model
MODEL_NAME = "all-mpnet-base-v2"
EMBEDDING_DIM = 768

# Global model instance (lazy loaded)
_model: SentenceTransformer | None = None


def get_model() -> SentenceTransformer:
    """Get or create the embedding model instance."""
    global _model
    if _model is None:
        print(f"Loading embedding model: {MODEL_NAME}...")
        _model = SentenceTransformer(MODEL_NAME)
        print("Model loaded.")
    return _model


def embed_text(text: str) -> np.ndarray:
    """Embed a single text string.

    Returns:
        numpy array of shape (768,)
    """
    model = get_model()
    return model.encode(text, convert_to_numpy=True)


def embed_texts(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed multiple text strings.

    Args:
        texts: List of strings to embed
        batch_size: Batch size for encoding

    Returns:
        numpy array of shape (len(texts), 768)
    """
    model = get_model()
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
    )


def embed_chunk(chunk: DocChunk) -> np.ndarray:
    """Embed a documentation chunk.

    Combines name, signature, and content for better retrieval.
    """
    return embed_text(chunk.to_embedding_text())


def embed_chunks(chunks: list[DocChunk], batch_size: int = 32) -> np.ndarray:
    """Embed multiple documentation chunks.

    Args:
        chunks: List of DocChunk objects
        batch_size: Batch size for encoding

    Returns:
        numpy array of shape (len(chunks), 768)
    """
    texts = [chunk.to_embedding_text() for chunk in chunks]
    return embed_texts(texts, batch_size=batch_size)


def embed_questions(questions: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed hypothetical questions.

    Args:
        questions: List of question strings
        batch_size: Batch size for encoding

    Returns:
        numpy array of shape (len(questions), 768)
    """
    return embed_texts(questions, batch_size=batch_size)


if __name__ == "__main__":
    # Test embeddings
    print("Testing embedder...")

    # Test single text
    text = "How do I get all walls from an IFC file?"
    embedding = embed_text(text)
    print(f"Single text embedding shape: {embedding.shape}")

    # Test batch
    texts = [
        "How do I open an IFC file?",
        "How do I get all walls?",
        "What is IfcOpenShell?",
    ]
    embeddings = embed_texts(texts)
    print(f"Batch embedding shape: {embeddings.shape}")

    # Test with a sample chunk
    from pathlib import Path

    from src.docs_indexer.parser_python import extract_docstrings_from_file

    ifcopenshell_path = Path(
        "external/ifcopenshell-docs/src/ifcopenshell-python/ifcopenshell"
    )
    chunks = extract_docstrings_from_file(
        ifcopenshell_path / "util" / "element.py",
        ifcopenshell_path.parent,
    )[:3]

    chunk_embeddings = embed_chunks(chunks)
    print(f"Chunk embeddings shape: {chunk_embeddings.shape}")
