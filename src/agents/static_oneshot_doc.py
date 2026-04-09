"""
Doc-augmented Static One-Shot: plan doc queries, fetch docs, generate code, execute, synthesize.

Pipeline:
  Step 0 -- DocQueryPlanner        (which APIs do I need?)
  Step 1 -- Doc fetching            (retrieve + dedup + format)
  Step 2 -- DocStaticCodeGenerator  (code gen with pre-fetched doc_context)
  Step 3 -- Code execution
  Step 4 -- StaticAnswerSynthesizer
"""

import time
from contextlib import nullcontext
from typing import Callable, Dict, Optional

import mlflow
from baml_py import baml_py
from baml_py.baml_py import Collector
from loguru import logger

from src.baml.baml_client import b
from src.baml.baml_client.types import CodeAction
from src.docs_indexer.retriever import format_results, retrieve
from src.schemas.agent_error import AgentError, CobbiResult
from src.util.baml_retry import call_baml_with_retry
from src.util.fallback_code_parser import try_parse_code_action
from src.util.extract_raw_prompt import extract_raw_prompt
from src.util.python_executor import execute_python, setup_interpreter


# Defaults for doc context limits
MAX_DOC_CHUNKS = 10  # max deduped chunks to keep (was unbounded, typically 15-25)
MAX_DOC_CHARS = 16_000  # hard cap on doc_context string length (~4k tokens)


def static_oneshot_doc(
    user_input: str,
    tools: Dict[str, Callable],
    model_path: Optional[str] = None,
    client: str = "GLM_4_7",
    mlflow_run_id: Optional[str] = None,
    max_doc_chunks: int = MAX_DOC_CHUNKS,
    max_doc_chars: int = MAX_DOC_CHARS,
) -> CobbiResult:
    """
    Doc-augmented static one-shot baseline for BIM question answering.

    Extends the plain static one-shot by first planning documentation queries
    and fetching relevant IfcOpenShell API docs before code generation.

    Args:
        user_input: The question to answer
        tools: Dictionary of available tools/functions for code execution
                (should be empty for this system -- no tool use during generation)
        model_path: Optional path to IFC model file
        client: BAML client name (default: GLM_4_7)
        mlflow_run_id: Optional MLflow run ID to continue

    Returns:
        CobbiResult with answer, collector, and execution history
    """
    logger.info(f"[STATIC-DOC] Answering question: {user_input[:100]}...")

    # Single shared collector across all LLM calls
    collector = Collector(name="StaticOneshotDoc")
    client_registry = baml_py.ClientRegistry()
    client_registry.set_primary(client)

    # Prepare interpreter (tools passed for execution env, not for prompt)
    interpreter = setup_interpreter(model_path, tools)

    # MLflow run context
    active_run = mlflow.active_run()
    if mlflow_run_id:
        run_context_manager = mlflow.start_run(run_id=mlflow_run_id)
    elif active_run:
        run_context_manager = nullcontext()
    else:
        run_context_manager = mlflow.start_run(run_name="StaticOneshotDoc")

    with run_context_manager:
        if not active_run:
            mlflow.log_params(
                {
                    "component": "StaticOneshotDoc",
                    "model_path": model_path or "None",
                    "tools_count": len(tools),
                    "client": client,
                }
            )

        with mlflow.start_span(name="StaticOneshotDoc", span_type="CHAIN") as main_span:
            main_span.set_inputs(
                {
                    "user_input": user_input,
                    "model_path": model_path or "None",
                    "tools_count": len(tools),
                }
            )

            start_time = time.time()

            # ── Step 0: Doc Planning ─────────────────────────────────
            with mlflow.start_span(
                name="doc_planning", span_type="LLM"
            ) as plan_span:
                plan_span.set_inputs(
                    {
                        "user_input": user_input,
                        "model_path": model_path or "None",
                    }
                )

                plan_start = time.time()
                plan_result = call_baml_with_retry(
                    lambda: b.with_options(
                        collector=collector,
                        client_registry=client_registry,
                    ).DocQueryPlanner(
                        user_input=user_input,
                        model_path=model_path,
                    ),
                    context_name="DocQueryPlanner",
                )
                plan_duration = time.time() - plan_start

                if isinstance(plan_result, AgentError):
                    plan_span.set_outputs(
                        {
                            "error": plan_result.error_message,
                            "error_type": plan_result.error_type,
                        }
                    )
                    plan_span.set_status("ERROR")
                    main_span.set_status("ERROR")
                    return CobbiResult(error=plan_result, collector=collector, history="")

                plan_input_tokens = 0
                plan_output_tokens = 0
                if collector.last and collector.last.usage:
                    plan_input_tokens = collector.last.usage.input_tokens or 0
                    plan_output_tokens = collector.last.usage.output_tokens or 0

                queries = plan_result.queries[:5]
                plan_span.set_outputs(
                    {
                        "thoughts": plan_result.thoughts,
                        "queries": queries,
                    }
                )
                plan_span.set_attributes(
                    {
                        "llm.client": client,
                        "input_tokens": plan_input_tokens,
                        "output_tokens": plan_output_tokens,
                        "latency": plan_duration,
                        "query_count": len(queries),
                    }
                )
                plan_span.set_status("OK")

            # ── Step 1: Doc Fetching ─────────────────────────────────
            with mlflow.start_span(
                name="doc_fetching", span_type="TOOL"
            ) as fetch_span:
                fetch_span.set_inputs({"queries": queries})

                fetch_start = time.time()

                # Retrieve chunks for each query, deduplicate by chunk.id
                seen_ids: dict[str, object] = {}
                for query in queries:
                    chunks = retrieve(query)
                    for chunk in chunks:
                        if chunk.id not in seen_ids:
                            seen_ids[chunk.id] = chunk

                deduped_chunks = list(seen_ids.values())[:max_doc_chunks]
                doc_context = format_results(deduped_chunks)  # type: ignore[arg-type]

                # Hard cap on character length to keep prompt manageable
                if len(doc_context) > max_doc_chars:
                    logger.info(
                        f"[STATIC-DOC] Truncating doc_context from "
                        f"{len(doc_context):,} to {max_doc_chars:,} chars"
                    )
                    doc_context = doc_context[:max_doc_chars] + "\n\n[... documentation truncated ...]"
                fetch_duration = time.time() - fetch_start

                fetch_span.set_outputs(
                    {
                        "doc_chunk_count": len(deduped_chunks),
                        "doc_context_length": len(doc_context),
                    }
                )
                fetch_span.set_attributes(
                    {
                        "latency": fetch_duration,
                        "doc_query_count": len(queries),
                        "doc_chunk_count": len(deduped_chunks),
                    }
                )
                fetch_span.set_status("OK")

            mlflow.log_metrics(
                {
                    "doc_query_count": len(queries),
                    "doc_chunk_count": len(deduped_chunks),
                }
            )

            # ── Step 2: Code Generation ──────────────────────────────
            with mlflow.start_span(
                name="code_generation", span_type="LLM"
            ) as gen_span:
                gen_span.set_inputs(
                    {
                        "user_input": user_input,
                        "model_path": model_path or "None",
                        "doc_context_length": len(doc_context),
                    }
                )

                code_gen_start = time.time()
                code_result = call_baml_with_retry(
                    lambda: b.with_options(
                        collector=collector,
                        client_registry=client_registry,
                    ).DocStaticCodeGenerator(
                        user_input=user_input,
                        model_path=model_path,
                        doc_context=doc_context,
                    ),
                    context_name="DocStaticCodeGenerator",
                )
                code_gen_duration = time.time() - code_gen_start

                if isinstance(code_result, AgentError):
                    # Try fallback parser before giving up
                    fallback = try_parse_code_action(code_result)
                    if fallback is not None:
                        logger.info(
                            "[STATIC-DOC] Fallback parser recovered CodeAction "
                            f"from failed BAML response ({len(fallback.python_code)} chars)"
                        )
                        code_result = fallback
                    else:
                        gen_span.set_outputs(
                            {
                                "error": code_result.error_message,
                                "error_type": code_result.error_type,
                            }
                        )
                        gen_span.set_status("ERROR")
                        main_span.set_status("ERROR")
                        return CobbiResult(error=code_result, collector=collector, history="")

                gen_input_tokens = 0
                gen_output_tokens = 0
                if collector.last and collector.last.usage:
                    gen_input_tokens = collector.last.usage.input_tokens or 0
                    gen_output_tokens = collector.last.usage.output_tokens or 0

                rendered_prompt = extract_raw_prompt(collector)

                gen_span.set_outputs(
                    {
                        "thoughts": code_result.thoughts,
                        "python_code": code_result.python_code,
                    }
                )
                gen_span.set_attributes(
                    {
                        "llm.client": client,
                        "input_tokens": gen_input_tokens,
                        "output_tokens": gen_output_tokens,
                        "latency": code_gen_duration,
                    }
                )
                gen_span.set_status("OK")

            # ── Step 3: Code Execution ───────────────────────────────
            with mlflow.start_span(
                name="code_execution", span_type="TOOL"
            ) as exec_span:
                exec_span.set_inputs({"python_code": code_result.python_code})

                exec_start = time.time()
                execution_output = execute_python(
                    python_code=code_result.python_code,
                    tools=tools,
                    model_path=model_path,
                    interpreter=interpreter,
                )
                exec_duration = time.time() - exec_start

                exec_span.set_outputs({"execution_output": execution_output})
                exec_span.set_attributes({"latency": exec_duration})
                exec_span.set_status("OK")

            # ── Step 4: Answer Synthesis ─────────────────────────────
            with mlflow.start_span(
                name="answer_synthesis", span_type="LLM"
            ) as synth_span:
                synth_span.set_inputs(
                    {
                        "user_input": user_input,
                        "code": code_result.python_code,
                        "execution_output": execution_output,
                    }
                )

                synth_start = time.time()
                answer_result = call_baml_with_retry(
                    lambda: b.with_options(
                        collector=collector,
                        client_registry=client_registry,
                    ).StaticAnswerSynthesizer(
                        user_input=user_input,
                        code=code_result.python_code,
                        execution_output=execution_output,
                    ),
                    context_name="StaticAnswerSynthesizer",
                )
                synth_duration = time.time() - synth_start

                if isinstance(answer_result, AgentError):
                    synth_span.set_outputs(
                        {
                            "error": answer_result.error_message,
                            "error_type": answer_result.error_type,
                        }
                    )
                    synth_span.set_status("ERROR")
                    main_span.set_status("ERROR")
                    history = _format_history(code_result, execution_output)
                    return CobbiResult(
                        error=answer_result, collector=collector, history=history
                    )

                synth_input_tokens = 0
                synth_output_tokens = 0
                if collector.last and collector.last.usage:
                    synth_input_tokens = collector.last.usage.input_tokens or 0
                    synth_output_tokens = collector.last.usage.output_tokens or 0

                synth_span.set_outputs(
                    {
                        "thoughts": answer_result.thoughts,
                        "answer": answer_result.answer,
                    }
                )
                synth_span.set_attributes(
                    {
                        "llm.client": client,
                        "input_tokens": synth_input_tokens,
                        "output_tokens": synth_output_tokens,
                        "latency": synth_duration,
                    }
                )
                synth_span.set_status("OK")

            # ── Finalize ─────────────────────────────────────────────
            total_duration = time.time() - start_time

            total_input_tokens = 0
            total_output_tokens = 0
            if collector and hasattr(collector, "usage") and collector.usage:
                total_input_tokens = collector.usage.input_tokens or 0
                total_output_tokens = collector.usage.output_tokens or 0
            total_tokens = total_input_tokens + total_output_tokens

            mlflow.log_metrics(
                {
                    "static_doc_input_tokens": total_input_tokens,
                    "static_doc_output_tokens": total_output_tokens,
                    "static_doc_total_tokens": total_tokens,
                    "static_doc_execution_time": total_duration,
                    "static_doc_success": 1,
                    "static_doc_calls_count": len(collector.logs)
                    if hasattr(collector, "logs")
                    else 0,
                }
            )

            history = _format_history(code_result, execution_output)

            main_span.set_outputs(
                {
                    "answer": answer_result.answer,
                    "reasoning": answer_result.thoughts,
                    "execution_time": total_duration,
                }
            )
            main_span.set_attributes(
                {
                    "token_usage.input_tokens": total_input_tokens,
                    "token_usage.output_tokens": total_output_tokens,
                    "token_usage.total_tokens": total_tokens,
                    "execution_time_seconds": total_duration,
                    "system_prompt": rendered_prompt or "",
                    "doc_query_count": len(queries),
                    "doc_chunk_count": len(deduped_chunks),
                }
            )
            main_span.set_status("OK")

            logger.info(
                f"[STATIC-DOC] Tokens: {total_tokens} -- Latency: {total_duration:.2f}s "
                f"-- Docs: {len(queries)} queries, {len(deduped_chunks)} chunks"
            )

            return CobbiResult(
                answer=answer_result, collector=collector, history=history
            )


def _format_history(code_action: CodeAction, execution_output: str) -> str:
    """Format execution history for tool usage tracking compatibility."""
    return (
        f"--- Static One-Shot (Doc-Augmented) ---\n"
        f"Thoughts: {code_action.thoughts}\n\n"
        f"Code:\n{code_action.python_code}\n\n"
        f"Result:\n{execution_output}\n"
    )
