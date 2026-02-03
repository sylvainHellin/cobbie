"""Main indexer orchestration for building the documentation vector store."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import mlflow
from loguru import logger

from src.docs_indexer.chunk_reviewer import (
    ReviewResult,
    filter_useful_chunks,
    review_chunk,
)
from src.docs_indexer.embedder import embed_chunks, embed_texts
from src.docs_indexer.parser_python import extract_all_python_docstrings
from src.docs_indexer.parser_rst import parse_all_rst_tutorials
from src.docs_indexer.storage import DEFAULT_DB_PATH, DocVectorStore

# MLflow configuration
MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
MLFLOW_EXPERIMENT_NAME = "DocIndexing"

# Paths
IFCOPENSHELL_DOCS_PATH = Path("src/docs_indexer/external/ifcopenshell-docs/src/ifcopenshell-python")
IFCOPENSHELL_PATH = IFCOPENSHELL_DOCS_PATH / "ifcopenshell"
DOCS_PATH = IFCOPENSHELL_DOCS_PATH / "docs"

# Cache file for review results (to avoid re-running expensive LLM calls)
REVIEW_CACHE_PATH = Path("src/db/doc_review_cache.json")


def progress_callback(completed: int, total: int):
    """Print progress update."""
    print(f"  Progress: {completed}/{total} ({100 * completed / total:.1f}%)")


def load_review_cache() -> dict[str, dict]:
    """Load cached review results."""
    if REVIEW_CACHE_PATH.exists():
        with open(REVIEW_CACHE_PATH) as f:
            return json.load(f)
    return {}


def save_review_cache(cache: dict[str, dict]):
    """Save review results to cache."""
    REVIEW_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REVIEW_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def run_indexing(
    skip_review: bool = False,
    max_workers: int = 5,
    db_path: Path = DEFAULT_DB_PATH,
):
    """Run the full indexing pipeline.

    Creates an MLflow run with nested runs for each chunk review.

    Args:
        skip_review: If True, skip LLM review and use all chunks
        max_workers: Number of parallel workers for LLM review
        db_path: Path to the vector database
    """
    # Set up MLflow tracking
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT_NAME)

    run_name = f"DocIndexing_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"

    with mlflow.start_run(run_name=run_name):
        # Log configuration parameters
        mlflow.log_params({
            "skip_review": skip_review,
            "max_workers": max_workers,
            "db_path": str(db_path),
            "ifcopenshell_path": str(IFCOPENSHELL_PATH),
            "docs_path": str(DOCS_PATH),
        })

        print("=" * 60)
        print("IfcOpenShell Documentation Indexer")
        print(f"MLflow run: {run_name}")
        print("=" * 60)

        # ================================================================
        # Step 1: Parse documentation
        # ================================================================
        print("\n[1/5] Parsing documentation...")
        with mlflow.start_span(name="ParseDocumentation", span_type="CHAIN") as span:
            print("  Parsing RST tutorials...")
            rst_chunks = parse_all_rst_tutorials(DOCS_PATH)

            print("  Parsing Python docstrings...")
            python_chunks = extract_all_python_docstrings(IFCOPENSHELL_PATH)

            all_chunks = rst_chunks + python_chunks

            span.set_outputs({
                "rst_chunks": len(rst_chunks),
                "python_chunks": len(python_chunks),
                "total_chunks": len(all_chunks),
            })

        print(f"  Total chunks extracted: {len(all_chunks)}")
        mlflow.log_metrics({
            "rst_chunks_parsed": len(rst_chunks),
            "python_chunks_parsed": len(python_chunks),
            "total_chunks_parsed": len(all_chunks),
        })

        # Track token/duration metrics from review step
        total_review_input_tokens = 0
        total_review_output_tokens = 0
        total_review_duration = 0.0
        chunks_reviewed = 0
        chunks_from_cache = 0

        # ================================================================
        # Step 2: Review chunks (or skip)
        # ================================================================
        print("\n[2/5] Reviewing chunks...")
        if skip_review:
            print("  Skipping LLM review (using all chunks)")
            useful_chunks = all_chunks
            all_results: list[ReviewResult] = []
            mlflow.set_tag("review_mode", "skipped")

            # Still load cached questions if available
            cache = load_review_cache()
            questions_loaded = 0
            for chunk in useful_chunks:
                cached = cache.get(chunk.id)
                if cached and cached.get("questions"):
                    chunk.questions = cached["questions"]
                    questions_loaded += 1
            if questions_loaded:
                print(f"  Loaded cached questions for {questions_loaded} chunks")
            else:
                logger.warning("No cached questions found — question search will be empty")
        else:
            mlflow.set_tag("review_mode", "llm_review")

            # Check cache
            cache = load_review_cache()
            chunks_to_review = []
            cached_results: list[ReviewResult] = []

            for chunk in all_chunks:
                if chunk.id in cache:
                    # Use cached result
                    cached = cache[chunk.id]
                    if cached["useful"]:
                        chunk.questions = cached["questions"]
                        cached_results.append(
                            ReviewResult(
                                chunk=chunk,
                                useful=True,
                                reason=None,
                                questions=cached["questions"],
                            )
                        )
                    chunks_from_cache += 1
                else:
                    chunks_to_review.append(chunk)

            print(f"  Cached: {len(cached_results)} chunks")
            print(f"  To review: {len(chunks_to_review)} chunks")

            mlflow.log_metrics({
                "chunks_from_cache": chunks_from_cache,
                "chunks_to_review": len(chunks_to_review),
            })

            if chunks_to_review:
                print(f"  Reviewing with max_workers={max_workers}...")

                # Review each chunk with its own nested MLflow run
                new_results: list[ReviewResult] = []

                for idx, chunk in enumerate(chunks_to_review):
                    print(f"  [{idx + 1}/{len(chunks_to_review)}] Reviewing: {chunk.name[:60]}...")

                    result = review_chunk(chunk, idx)
                    new_results.append(result)

                    # Accumulate metrics
                    total_review_input_tokens += result.input_tokens
                    total_review_output_tokens += result.output_tokens
                    total_review_duration += result.duration
                    chunks_reviewed += 1

                    # Update cache and save immediately after each review
                    cache[result.chunk.id] = {
                        "useful": result.useful,
                        "reason": result.reason,
                        "questions": result.questions,
                    }
                    save_review_cache(cache)

                logger.info(f"Review complete. Cache has {len(cache)} entries")

                all_results = cached_results + new_results
            else:
                all_results = cached_results

            useful_chunks = filter_useful_chunks(all_results)
            not_useful = len(all_results) - len(useful_chunks)
            print(f"  Useful chunks: {len(useful_chunks)} (filtered out {not_useful})")

        # Log review metrics
        mlflow.log_metrics({
            "chunks_reviewed": chunks_reviewed,
            "review_input_tokens": total_review_input_tokens,
            "review_output_tokens": total_review_output_tokens,
            "review_total_tokens": total_review_input_tokens + total_review_output_tokens,
            "review_duration": total_review_duration,
            "useful_chunks": len(useful_chunks),
            "filtered_chunks": len(all_chunks) - len(useful_chunks),
        })

        # ================================================================
        # Step 3: Embed chunks
        # ================================================================
        print("\n[3/5] Embedding chunks...")
        with mlflow.start_span(name="EmbedChunks", span_type="CHAIN") as span:
            chunk_embeddings = embed_chunks(useful_chunks, batch_size=32)
            span.set_outputs({"chunks_embedded": len(useful_chunks)})
        print(f"  Embedded {len(useful_chunks)} chunks")

        # ================================================================
        # Step 4: Embed questions
        # ================================================================
        print("\n[4/5] Embedding questions...")
        with mlflow.start_span(name="EmbedQuestions", span_type="CHAIN") as span:
            all_question_embeddings: list[list[tuple[str, Any]]] = []
            total_questions = 0

            for chunk in useful_chunks:
                if chunk.questions:
                    q_embeddings = embed_texts(chunk.questions, batch_size=32)
                    question_pairs = list(zip(chunk.questions, q_embeddings))
                    all_question_embeddings.append(question_pairs)
                    total_questions += len(chunk.questions)
                else:
                    all_question_embeddings.append([])

            span.set_outputs({
                "total_questions": total_questions,
                "chunks_with_questions": sum(1 for q in all_question_embeddings if q),
            })

        print(f"  Embedded {total_questions} questions")
        mlflow.log_metric("total_questions_generated", total_questions)

        # ================================================================
        # Step 5: Store in database
        # ================================================================
        print("\n[5/5] Storing in database...")
        with mlflow.start_span(name="StoreInDatabase", span_type="CHAIN") as span:
            store = DocVectorStore(db_path)
            store.clear()  # Clear existing data

            store.insert_chunks_batch(
                useful_chunks, chunk_embeddings, all_question_embeddings
            )
            stored_chunks = store.count_chunks()
            stored_questions = store.count_questions()

            span.set_outputs({
                "stored_chunks": stored_chunks,
                "stored_questions": stored_questions,
            })

        print(f"  Stored {stored_chunks} chunks")
        print(f"  Stored {stored_questions} questions")

        # Log final metrics
        mlflow.log_metrics({
            "stored_chunks": stored_chunks,
            "stored_questions": stored_questions,
        })

        # Set completion tag
        mlflow.set_tag("status", "completed")

        print("\n" + "=" * 60)
        print("Indexing complete!")
        print(f"Database: {db_path}")
        print(f"MLflow run: {run_name}")
        print("=" * 60)

        # Print summary
        print("\nSummary:")
        print(f"  - Total chunks parsed: {len(all_chunks)}")
        print(f"  - Chunks reviewed (LLM): {chunks_reviewed}")
        print(f"  - Chunks from cache: {chunks_from_cache}")
        print(f"  - Useful chunks: {len(useful_chunks)}")
        print(f"  - Questions generated: {total_questions}")
        print(f"  - Review tokens: {total_review_input_tokens + total_review_output_tokens}")
        print(f"  - Review duration: {total_review_duration:.1f}s")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Index IfcOpenShell documentation")
    parser.add_argument(
        "--skip-review",
        action="store_true",
        help="Skip LLM review and use all chunks",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=1,  # Default to 1 for cleaner MLflow tracking
        help="Number of parallel workers for LLM review (default: 1 for clean MLflow tracking)",
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default=str(DEFAULT_DB_PATH),
        help=f"Path to the vector database (default: {DEFAULT_DB_PATH})",
    )

    args = parser.parse_args()
    run_indexing(
        skip_review=args.skip_review,
        max_workers=args.max_workers,
        db_path=Path(args.db_path),
    )
