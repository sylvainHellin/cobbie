"""Embedding module with Ollama and sentence-transformers backends."""

import os

import numpy as np
import ollama

from src.docs_indexer.models import DocChunk

# Embedding dimension (qwen3-embedding:0.6b default)
EMBEDDING_DIM = 1024

# Backend configuration
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "ollama")
OLLAMA_MODEL = "qwen3-embedding:0.6b"
ST_MODEL_NAME = "BAAI/bge-m3"

# Global sentence-transformers model instance (lazy loaded, fallback only)
_st_model = None


def _get_st_model():
    """Get or create the sentence-transformers model instance (fallback)."""
    global _st_model
    if _st_model is None:
        from sentence_transformers import SentenceTransformer

        print(f"Loading sentence-transformers model: {ST_MODEL_NAME}...")
        _st_model = SentenceTransformer(ST_MODEL_NAME)
        print("Model loaded.")
    return _st_model


def _embed_ollama(texts: list[str]) -> np.ndarray:
    """Embed texts using Ollama."""
    response = ollama.embed(model=OLLAMA_MODEL, input=texts)
    return np.array(response.embeddings, dtype=np.float32)


def _embed_sentence_transformers(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed texts using sentence-transformers (fallback)."""
    model = _get_st_model()
    return model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=len(texts) > 10,
        convert_to_numpy=True,
    )


def embed_text(text: str) -> np.ndarray:
    """Embed a single text string.

    Returns:
        numpy array of shape (EMBEDDING_DIM,)
    """
    return embed_texts([text])[0]


def embed_texts(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed multiple text strings.

    Args:
        texts: List of strings to embed
        batch_size: Batch size for encoding (only used for sentence-transformers)

    Returns:
        numpy array of shape (len(texts), EMBEDDING_DIM)
    """
    if EMBEDDING_BACKEND == "ollama":
        # Ollama handles batching internally, but we batch for progress feedback
        if len(texts) <= batch_size:
            return _embed_ollama(texts)

        # Batch large requests with progress
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            print(f"Embedding batch {i // batch_size + 1}/{(len(texts) - 1) // batch_size + 1}...")
            all_embeddings.append(_embed_ollama(batch))
        return np.vstack(all_embeddings)
    else:
        return _embed_sentence_transformers(texts, batch_size=batch_size)


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
        numpy array of shape (len(chunks), EMBEDDING_DIM)
    """
    texts = [chunk.to_embedding_text() for chunk in chunks]
    return embed_texts(texts, batch_size=batch_size)


def embed_questions(questions: list[str], batch_size: int = 32) -> np.ndarray:
    """Embed hypothetical questions.

    Args:
        questions: List of question strings
        batch_size: Batch size for encoding

    Returns:
        numpy array of shape (len(questions), EMBEDDING_DIM)
    """
    return embed_texts(questions, batch_size=batch_size)


if __name__ == "__main__":
    # Test embeddings
    print(f"Testing embedder (backend={EMBEDDING_BACKEND})...")

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
