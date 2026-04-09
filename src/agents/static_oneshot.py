"""
Static One-Shot Baseline: generate code once, execute once, synthesize answer.

Two-agent architecture:
  Agent 1 (StaticCodeGenerator) → code execution → Agent 2 (StaticAnswerSynthesizer)
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
from src.schemas.agent_error import AgentError, CobbiResult
from src.util.baml_retry import call_baml_with_retry
from src.util.fallback_code_parser import try_parse_code_action
from src.util.extract_raw_prompt import extract_raw_prompt
from src.util.generate_tools_docs import generate_tools_docs
from src.util.python_executor import execute_python, setup_interpreter


def static_oneshot(
    user_input: str,
    tools: Dict[str, Callable],
    model_path: Optional[str] = None,
    client: str = "GLM_4_7",
    mlflow_run_id: Optional[str] = None,
) -> CobbiResult:
    """
    Static one-shot baseline for BIM question answering.

    Generates code once, executes it once, and synthesizes an answer from the output.
    No iterative exploration loop — isolates the value of COBBIE's multi-turn approach.

    Args:
        user_input: The question to answer
        tools: Dictionary of available tools/functions for code execution
        model_path: Optional path to IFC model file
        client: BAML client name (default: GLM_4_7)
        mlflow_run_id: Optional MLflow run ID to continue

    Returns:
        CobbiResult with answer, collector, and execution history
    """
    logger.info(f"[STATIC] Answering question: {user_input[:100]}...")

    # Create collector and client registry (same pattern as cobbie())
    collector = Collector(name="StaticOneshot")
    client_registry = baml_py.ClientRegistry()
    client_registry.set_primary(client)

    # Prepare tools
    tools_docs = generate_tools_docs(tools)
    interpreter = setup_interpreter(model_path, tools)

    # MLflow run context
    active_run = mlflow.active_run()
    if mlflow_run_id:
        run_context_manager = mlflow.start_run(run_id=mlflow_run_id)
    elif active_run:
        run_context_manager = nullcontext()
    else:
        run_context_manager = mlflow.start_run(run_name="StaticOneshot")

    with run_context_manager:
        if not active_run:
            mlflow.log_params(
                {
                    "component": "StaticOneshot",
                    "model_path": model_path or "None",
                    "tools_count": len(tools),
                    "client": client,
                    "tools": ", ".join(tools.keys()),
                }
            )

        with mlflow.start_span(name="StaticOneshot", span_type="CHAIN") as main_span:
            main_span.set_inputs(
                {
                    "user_input": user_input,
                    "model_path": model_path or "None",
                    "tools_count": len(tools),
                }
            )

            start_time = time.time()

            # ── Step 1: Code Generation ──────────────────────────────
            with mlflow.start_span(
                name="code_generation", span_type="LLM"
            ) as gen_span:
                gen_span.set_inputs(
                    {
                        "user_input": user_input,
                        "available_tools": tools_docs,
                        "model_path": model_path or "None",
                    }
                )

                code_gen_start = time.time()
                code_result = call_baml_with_retry(
                    lambda: b.with_options(
                        collector=collector,
                        client_registry=client_registry,
                    ).StaticCodeGenerator(
                        user_input=user_input,
                        available_tools=tools_docs,
                        model_path=model_path,
                    ),
                    context_name="StaticCodeGenerator",
                )
                code_gen_duration = time.time() - code_gen_start

                if isinstance(code_result, AgentError):
                    # Try fallback parser before giving up
                    fallback = try_parse_code_action(code_result)
                    if fallback is not None:
                        logger.info(
                            "[STATIC] Fallback parser recovered CodeAction "
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

                # Extract token usage for code generation
                gen_input_tokens = 0
                gen_output_tokens = 0
                if collector.last and collector.last.usage:
                    gen_input_tokens = collector.last.usage.input_tokens or 0
                    gen_output_tokens = collector.last.usage.output_tokens or 0

                # Capture rendered prompt
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

            # ── Step 2: Code Execution ───────────────────────────────
            with mlflow.start_span(
                name="code_execution", span_type="TOOL"
            ) as exec_span:
                exec_span.set_inputs(
                    {
                        "python_code": code_result.python_code,
                    }
                )

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

            # ── Step 3: Answer Synthesis ─────────────────────────────
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
                    # Build partial history even on synthesis failure
                    history = _format_history(code_result, execution_output)
                    return CobbiResult(
                        error=answer_result, collector=collector, history=history
                    )

                # Extract token usage for answer synthesis
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

            # Combined token usage
            total_input_tokens = 0
            total_output_tokens = 0
            if collector and hasattr(collector, "usage") and collector.usage:
                total_input_tokens = collector.usage.input_tokens or 0
                total_output_tokens = collector.usage.output_tokens or 0
            total_tokens = total_input_tokens + total_output_tokens

            mlflow.log_metrics(
                {
                    "static_input_tokens": total_input_tokens,
                    "static_output_tokens": total_output_tokens,
                    "static_total_tokens": total_tokens,
                    "static_execution_time": total_duration,
                    "static_success": 1,
                    "static_calls_count": len(collector.logs)
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
                }
            )
            main_span.set_status("OK")

            logger.info(
                f"[STATIC] Tokens: {total_tokens} -- Latency: {total_duration:.2f}s"
            )

            return CobbiResult(
                answer=answer_result, collector=collector, history=history
            )


def _format_history(code_action: CodeAction, execution_output: str) -> str:
    """Format execution history for tool usage tracking compatibility."""
    return (
        f"--- Static One-Shot ---\n"
        f"Thoughts: {code_action.thoughts}\n\n"
        f"Code:\n{code_action.python_code}\n\n"
        f"Result:\n{execution_output}\n"
    )
