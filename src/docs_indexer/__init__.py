"""Documentation indexer for IfcOpenShell docs.

This module provides tools to:
1. Parse RST and Python source files
2. Extract semantically meaningful chunks
3. Generate hypothetical questions via Claude
4. Embed and store in sqlite-vec
5. Retrieve relevant documentation
"""

from src.docs_indexer.indexer import run_indexing
from src.docs_indexer.models import DocChunk
from src.docs_indexer.retriever import query_docs, retrieve

__all__ = ["DocChunk", "query_docs", "retrieve", "run_indexing"]
