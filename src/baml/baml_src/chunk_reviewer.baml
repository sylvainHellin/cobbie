// BAML function for reviewing documentation chunks and generating hypothetical questions

class ChunkReviewInput {
  chunk_type string
  name string
  module_path string?
  signature string?
  content string
}

class ChunkReviewOutput {
  useful bool @description("Whether this chunk is useful for answering user questions about IfcOpenShell")
  reason string? @description("If not useful, explain why (e.g., 'too short', 'internal implementation detail', 'no useful information')")
  questions string[] @description("3-5 hypothetical questions that a user might ask that this chunk would answer")
}

function ReviewDocChunk(input: ChunkReviewInput) -> ChunkReviewOutput {
  client GLM_4_7
  prompt #"
    You are reviewing documentation chunks for a RAG system about IfcOpenShell, a Python library for working with IFC/BIM (Building Information Modeling) files.

    ## Chunk to review:
    Type: {{ input.chunk_type }}
    Name: {{ input.name }}
    {% if input.module_path %}Module: {{ input.module_path }}{% endif %}
    {% if input.signature %}Signature: {{ input.signature }}{% endif %}

    Content:
    {{ input.content }}

    ## Tasks:
    1. Determine if this chunk is useful for answering user questions about IfcOpenShell.
       - Mark as NOT useful if: it's an internal implementation detail, too short/vague, or doesn't provide actionable information.
       - Mark as useful if: it explains how to do something, documents an API, or provides useful context.

    2. If useful, generate 3-5 hypothetical questions that a user might ask that this chunk would answer.
       - Questions should be natural (how users actually phrase things)
       - Cover different ways to ask about the same functionality
       - Include both specific questions ("How do I get all walls from an IFC file?") and conceptual questions ("How does element filtering work in IfcOpenShell?")
       - Focus on practical use cases

    {{ ctx.output_format }}
  "#
}
