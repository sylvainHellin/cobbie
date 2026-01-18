"""Data models for documentation chunks."""

from dataclasses import dataclass, field
from typing import Literal


ChunkType = Literal["function", "class", "method", "module", "tutorial_section"]


@dataclass
class DocChunk:
    """A semantically meaningful chunk of documentation."""

    id: str
    content: str
    chunk_type: ChunkType
    name: str
    source_file: str
    module: str | None = None
    signature: str | None = None
    line_start: int | None = None
    parent: str | None = None
    questions: list[str] = field(default_factory=list)

    def to_embedding_text(self) -> str:
        """Format chunk for embedding."""
        parts = [self.name]
        if self.signature:
            parts.append(self.signature)
        parts.append(self.content)
        return "\n".join(parts)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage."""
        return {
            "id": self.id,
            "content": self.content,
            "chunk_type": self.chunk_type,
            "name": self.name,
            "source_file": self.source_file,
            "module": self.module,
            "signature": self.signature,
            "line_start": self.line_start,
            "parent": self.parent,
        }
