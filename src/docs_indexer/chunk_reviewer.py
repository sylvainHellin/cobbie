"""Chunk reviewer using Claude Haiku to validate and generate questions."""

import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

import mlflow
from src.baml.baml_client import b
from src.baml.baml_client.types import ChunkReviewInput
from baml_py.baml_py import Collector
from loguru import logger

from src.docs_indexer.models import DocChunk


class ReviewResult:
    """Result of reviewing a documentation chunk."""

    def __init__(
        self,
        chunk: DocChunk,
        useful: bool,
        reason: str | None,
        questions: list[str],
        input_tokens: int = 0,
        output_tokens: int = 0,
        duration: float = 0.0,
    ):
        self.chunk = chunk
        self.useful = useful
        self.reason = reason
        self.questions = questions
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.duration = duration


def review_chunk(chunk: DocChunk, chunk_index: int) -> ReviewResult:
    """Review a single chunk and generate hypothetical questions.

    Each chunk review is tracked as a nested MLflow run with comprehensive logging.

    Uses Claude Haiku via BAML to:
    1. Determine if the chunk is useful
    2. Generate 3-5 hypothetical questions if useful

    Args:
        chunk: The documentation chunk to review
        chunk_index: Index of the chunk (for run naming)

    Returns:
        ReviewResult with all metadata
    """
    # Create a descriptive run name
    run_name = f"chunk_{chunk_index}_{chunk.chunk_type}_{chunk.name[:50]}"

    collector = Collector(name="ChunkReviewer")
    start_time = time.time()

    # Create nested run for this chunk
    with mlflow.start_run(run_name=run_name, nested=True):
        # Log all chunk metadata as parameters
        mlflow.log_params({
            "chunk_id": chunk.id,
            "chunk_index": chunk_index,
            "chunk_type": chunk.chunk_type,
            "chunk_name": chunk.name,
            "module": chunk.module or "N/A",
            "source_file": chunk.source_file,
            "line_start": chunk.line_start or 0,
            "parent": chunk.parent or "N/A",
            "content_length": len(chunk.content),
            "signature": (chunk.signature[:200] + "...") if chunk.signature and len(chunk.signature) > 200 else (chunk.signature or "N/A"),
        })

        # Create the BAML input
        input_data = ChunkReviewInput(
            chunk_type=chunk.chunk_type,
            name=chunk.name,
            module_path=chunk.module,
            signature=chunk.signature,
            content=chunk.content,
        )

        # Log the exact input that will be sent to the LLM
        with mlflow.start_span(name="LLM_ReviewDocChunk", span_type="LLM") as span:
            span.set_inputs({
                "chunk_type": input_data.chunk_type,
                "name": input_data.name,
                "module_path": input_data.module_path,
                "signature": input_data.signature,
                "content": input_data.content,
            })

            try:
                result = b.with_options(collector=collector).ReviewDocChunk(input_data)

                duration = time.time() - start_time

                # Extract token usage
                input_tokens = output_tokens = 0
                if collector.usage:
                    input_tokens = collector.usage.input_tokens or 0
                    output_tokens = collector.usage.output_tokens or 0

                questions = result.questions if result.useful else []

                # Log the LLM response in span
                span.set_outputs({
                    "useful": result.useful,
                    "reason": result.reason,
                    "questions": questions,
                    "questions_count": len(questions),
                })
                span.set_attributes({
                    "duration_seconds": duration,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                })
                span.set_status("OK")

                # Log metrics at run level
                mlflow.log_metrics({
                    "duration": duration,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "useful": 1 if result.useful else 0,
                    "questions_generated": len(questions),
                })

                # Log the full LLM response as params (for easy viewing in UI)
                mlflow.log_params({
                    "llm_response_useful": str(result.useful),
                    "llm_response_reason": (result.reason[:500] + "...") if result.reason and len(result.reason) > 500 else (result.reason or "N/A"),
                    "llm_response_questions_count": len(questions),
                })

                # Log each generated question as a separate param for visibility
                for i, q in enumerate(questions[:10]):  # Limit to first 10
                    mlflow.log_param(f"question_{i+1}", q[:200] if len(q) > 200 else q)

                mlflow.set_tag("status", "success")

                logger.debug(
                    f"Chunk {chunk_index} ({chunk.name}): "
                    f"useful={result.useful}, questions={len(questions)}, "
                    f"tokens={input_tokens + output_tokens}, duration={duration:.2f}s"
                )

                return ReviewResult(
                    chunk=chunk,
                    useful=result.useful,
                    reason=result.reason,
                    questions=questions,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    duration=duration,
                )

            except Exception as e:
                duration = time.time() - start_time
                error_msg = str(e)

                span.set_status("ERROR")
                span.set_attributes({"error": error_msg})

                mlflow.log_metrics({
                    "duration": duration,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "useful": 1,  # Mark as useful on error (conservative)
                    "questions_generated": 0,
                    "error": 1,
                })
                mlflow.log_param("error_message", error_msg[:500])
                mlflow.set_tag("status", "error")

                logger.warning(f"Failed to review chunk {chunk.name}: {e}")

                return ReviewResult(
                    chunk=chunk,
                    useful=True,  # Conservative: mark as useful on error
                    reason=f"Review failed: {e}",
                    questions=[],
                    input_tokens=0,
                    output_tokens=0,
                    duration=duration,
                )


def review_chunks_batch(
    chunks: list[DocChunk],
    max_workers: int = 5,
    progress_callback: Callable[[int, int], None] | None = None,
) -> list[ReviewResult]:
    """Review multiple chunks with threading for parallelism.

    Note: When running with multiple workers, MLflow nested runs may interleave.
    For cleaner tracking, use max_workers=1.

    Args:
        chunks: List of chunks to review
        max_workers: Number of concurrent threads
        progress_callback: Optional callback(completed, total) for progress updates

    Returns:
        List of review results
    """
    results: list[ReviewResult] = []
    total = len(chunks)
    completed = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks with their index
        future_to_chunk = {
            executor.submit(review_chunk, chunk, idx): (chunk, idx)
            for idx, chunk in enumerate(chunks)
        }

        # Collect results as they complete
        for future in as_completed(future_to_chunk):
            chunk, idx = future_to_chunk[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                # On error, mark as useful but with no questions
                logger.warning(f"Failed to review chunk {chunk.name}: {e}")
                results.append(
                    ReviewResult(
                        chunk=chunk,
                        useful=True,
                        reason=f"Review failed: {e}",
                        questions=[],
                    )
                )

            completed += 1
            if progress_callback:
                progress_callback(completed, total)

    return results


def filter_useful_chunks(results: list[ReviewResult]) -> list[DocChunk]:
    """Filter results to only useful chunks, adding questions to chunk objects."""
    useful_chunks = []

    for result in results:
        if result.useful:
            chunk = result.chunk
            chunk.questions = result.questions
            useful_chunks.append(chunk)

    return useful_chunks


if __name__ == "__main__":
    # Test with a sample chunk
    from pathlib import Path

    from src.docs_indexer.parser_python import extract_docstrings_from_file

    ifcopenshell_path = Path(
        "src/docs_indexer/external/ifcopenshell-docs/src/ifcopenshell-python/ifcopenshell"
    )

    # Get a sample chunk
    chunks = extract_docstrings_from_file(
        ifcopenshell_path / "util" / "element.py",
        ifcopenshell_path.parent,
    )

    if chunks:
        sample = chunks[0]
        print(f"Testing with chunk: {sample.name}")
        print(f"Content preview: {sample.content[:200]}...")

        result = review_chunk(sample, 0)
        print(f"\nUseful: {result.useful}")
        print(f"Reason: {result.reason}")
        print(f"Questions: {result.questions}")
