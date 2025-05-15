# %% Section::setup
"""
Current implementation of the IfcAnswerEngineV3.

Tracing:
    1. Phoenix
    If running tracing with phoenix, need to run the server locally first
    ```bash
    python -m phoenix.server.main serve
    ```

    Then the trace can be observed at `http://0.0.0.0:6006/projects/`

    2. LangFuse
    If running tracing with Langfuse, trace can be seen on: https://cloud.langfuse.com/
"""

import base64
import os
import sqlite3
import uuid
import re
from datetime import datetime

from dotenv import find_dotenv, load_dotenv
from openinference.instrumentation.smolagents import SmolagentsInstrumentor
from smolagents import CodeAgent, tool
from smolagents.monitoring import LogLevel
from smolagents.agents import ActionStep
from typing import Literal
import opentelemetry.trace

from src.config import LANGUAGE_MODELS
from src.tools import TOOLS, web_search, query_ifcopenshell_documentation

# Load secrets
load_dotenv(find_dotenv())

# %% Section::config

# SQLite Database setup
DB_NAME = "smolagents_runs.db"
current_run_id = None
db_conn = None

# To store previous token counts per agent for calculating per-step tokens
previous_agent_token_counts = {}


def init_sqlite_db():
    global db_conn, previous_agent_token_counts
    previous_agent_token_counts = {}  # Reset for each script run / DB init
    db_conn = sqlite3.connect(DB_NAME)
    cursor = db_conn.cursor()

    table_columns_to_add = {
        "action_input_code": "TEXT",
        "input_tokens": "INTEGER",
        "output_tokens": "INTEGER",
    }
    for column_name, column_type in table_columns_to_add.items():
        try:
            cursor.execute(
                f"ALTER TABLE run_steps ADD COLUMN {column_name} {column_type}"
            )
            # print(f"[DB_SETUP] Added column '{column_name}' to 'run_steps' table.") # Optional print
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e).lower():
                pass
            else:
                raise

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS run_steps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id TEXT NOT NULL,
        agent_name TEXT,
        step_number INTEGER,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        model_output TEXT,
        action_input_code TEXT,
        action_output TEXT,
        observations TEXT,
        error TEXT,
        duration_s REAL,
        input_tokens INTEGER,    
        output_tokens INTEGER    
    )
    """)
    db_conn.commit()


# Select LLM
model = LANGUAGE_MODELS["llama4_maverick"]

# Q&A
QUESTION = "What is the height of the ceiling in room A203?"
GROUND_TRUTH = "The height of the ceiling in room A203 is 2.58 m."

# Tracing - Phoenix or Langfuse for OTel, SQLite is always active via callback
TRACING: Literal["phoenix", "langfuse"] = "phoenix"

if TRACING == "phoenix":
    from phoenix.otel import register

    register()
    SmolagentsInstrumentor().instrument(capture_llm_calls=True, capture_tool_calls=True)
    print("Phoenix tracing enabled.")

elif TRACING == "langfuse":
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    LANGFUSE_PUBLIC_KEY = os.environ["LANGFUSE_PUBLIC_KEY"]
    LANGFUSE_SECRET_KEY = os.environ["LANGFUSE_SECRET_KEY"]

    LANGFUSE_AUTH = base64.b64encode(
        f"{LANGFUSE_PUBLIC_KEY}:{LANGFUSE_SECRET_KEY}".encode()
    ).decode()
    os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"] = (
        "https://cloud.langfuse.com/api/public/otel"
    )
    os.environ["OTEL_EXPORTER_OTLP_HEADERS"] = f"Authorization=Basic {LANGFUSE_AUTH}"

    trace_provider = TracerProvider()
    trace_provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter()))
    opentelemetry.trace.set_tracer_provider(trace_provider)

    SmolagentsInstrumentor().instrument(
        tracer_provider=trace_provider, capture_llm_calls=True, capture_tool_calls=True
    )
    print("Langfuse tracing enabled.")


# Regex to extract code from the model_output (from smolagents.codes.CodeAgent.CODE_BLOCK_RE)
CODE_BLOCK_RE = re.compile(r"```(?:python|py)?\s*([\s\S]+?)\s*```")


# Custom callback for SQLite logging
def sqlite_log_callback(step_log: ActionStep, agent: CodeAgent) -> None:
    global db_conn, current_run_id, previous_agent_token_counts
    if not db_conn or not current_run_id:
        print("[SQLITE_CALLBACK_ERROR] DB connection or run_id not set.")
        return

    # Get current total token counts for this agent
    current_total_input = agent.monitor.total_input_token_count
    current_total_output = agent.monitor.total_output_token_count

    # Get previous counts for this agent, default to 0 if first step
    agent_key = (
        agent.name
    )  # Or id(agent) for more robustness if names can clash and agents are reused
    prev_counts = previous_agent_token_counts.get(agent_key, {"input": 0, "output": 0})

    step_input_tokens = current_total_input - prev_counts["input"]
    step_output_tokens = current_total_output - prev_counts["output"]

    log_data = {
        "run_id": current_run_id,
        "agent_name": agent.name,
        "step_number": None,
        "model_output": None,
        "action_input_code": None,
        "action_output": None,
        "observations": None,
        "error": None,
        "duration_s": None,
        "input_tokens": step_input_tokens,
        "output_tokens": step_output_tokens,
        "timestamp": datetime.now().isoformat(),
    }

    if hasattr(step_log, "step_number"):
        log_data["step_number"] = step_log.step_number

    raw_model_output = None
    if hasattr(step_log, "model_output") and step_log.model_output:
        raw_model_output = str(step_log.model_output)
        log_data["model_output"] = raw_model_output
        code_match = CODE_BLOCK_RE.search(raw_model_output)
        if code_match:
            log_data["action_input_code"] = code_match.group(1).strip()

    if hasattr(step_log, "action_output") and step_log.action_output:
        log_data["action_output"] = str(step_log.action_output)

    if hasattr(step_log, "observations") and step_log.observations:
        log_data["observations"] = str(step_log.observations)

    if hasattr(step_log, "error") and step_log.error:
        log_data["error"] = str(step_log.error)

    if hasattr(step_log, "duration") and step_log.duration:
        try:
            log_data["duration_s"] = float(step_log.duration.total_seconds())  # type: ignore (it works)
        except AttributeError:
            try:
                log_data["duration_s"] = float(step_log.duration)
            except (ValueError, TypeError):
                log_data["duration_s"] = None

    # Update previous_agent_token_counts for the next step of this agent
    previous_agent_token_counts[agent_key] = {
        "input": current_total_input,
        "output": current_total_output,
    }

    cursor = db_conn.cursor()
    try:
        cursor.execute(
            """
        INSERT INTO run_steps (run_id, agent_name, step_number, timestamp, model_output, action_input_code, action_output, observations, error, duration_s, input_tokens, output_tokens)
        VALUES (:run_id, :agent_name, :step_number, :timestamp, :model_output, :action_input_code, :action_output, :observations, :error, :duration_s, :input_tokens, :output_tokens)
        """,
            log_data,
        )
        db_conn.commit()
        print(
            f"[SQLITE_CALLBACK] Logged step for run_id {current_run_id}, agent {agent.name}, step {log_data['step_number']}"
        )
    except sqlite3.Error as e:
        print(f"[SQLITE_CALLBACK_ERROR] Failed to log step: {e}")


# %% Section::Managed agents
# %% Subsection::answer_verifier


# tools
@tool
def get_correct_answer(question_id: int) -> str:
    """
    Query the database and return the ground truth to the given question

    Args:
        question_id: The ID of the question for which the ground truth is to be returned.

    Returns:
        str: the correct answer
    """
    return GROUND_TRUTH


answer_verifier = CodeAgent(
    tools=[get_correct_answer],
    model=model,
    name="answer_verifier",
    description="Check your answer to see if it is correct.",
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[sqlite_log_callback],
)

tool_maker = CodeAgent(
    tools=[web_search, query_ifcopenshell_documentation],
    model=model,
    name="tool_maker",
    description="Generate a new tool based on the requirements provided. Test the new tool and return a code snippet of the tool implementation if it works.",
    additional_authorized_imports=[
        "ifcopenshell",
        "ifcopenshell.util.element",
        "ifcopenshell.util.shape",
        "ifcopenshell.util.placement",
        "ifcopenshell.util.geolocation",
        "ifcopenshell.util.system",
        "ifcopenshell.geom",
        "ifcopenshell.file",
        "ifcopenshell.entity_instance",
    ],
    max_print_outputs_length=2**12,  # 4.096
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[sqlite_log_callback],
)

# %% Section::Orchestrator agent
TASK_ORCHESTRATOR = """
Your task is to assess if you can answer the question using the existing tools and, if not, define the requirements to create a new tool.

Here is how you should proceed:
    1. Try to answer the question using a combination of the existing tools (as well as some code in between if useful)
    2. If you are missing a tool to answer this question, you can call the tool_maker, who will give you a code snippet for the new tool.
    3. Once you have all the tools you need, and you think you can answer the question, call the `answer_verifier` agent. This agent has access to the ground truth, and will tell you if your answer is correct.You MUST call him BEFORE answering the question with the `final_answer` tool.
        3.1 If the answer is correct, call the save_tool agent who will review the code snippet of the new tool, ensure it's format is compliant, and save it for future use.
        3.2 If the answer is incorrect, use the provided feedback to try to come to the right answer. If you think the error comes from the new tool, you can call the tool_maker again and ask him to fix it.
"""

# Set up the agent
agent = CodeAgent(
    tools=TOOLS,
    model=model,
    name="agent_orchestrator",
    additional_authorized_imports=[
        "ifcopenshell",
        "ifcopenshell.util.element",
        "ifcopenshell.util.shape",
        "ifcopenshell.util.placement",
        "ifcopenshell.util.geolocation",
        "ifcopenshell.util.system",
        "ifcopenshell.geom",
        "ifcopenshell.file",
        "ifcopenshell.entity_instance",
    ],
    max_print_outputs_length=2**12,  # 4.096
    managed_agents=[answer_verifier, tool_maker],
    verbosity_level=LogLevel.DEBUG,
    step_callbacks=[sqlite_log_callback],
)

# %% Section::run

# Initialize SQLite DB
init_sqlite_db()

# Generate a unique run ID for this execution
current_run_id = str(uuid.uuid4())
print(f"Starting agent run. SQLite Run ID: {current_run_id}")

# Get an OTel tracer
otel_tracer = opentelemetry.trace.get_tracer(__name__, "1.0")

try:
    # Start a parent OTel span for the entire agent.run() orchestration
    with otel_tracer.start_as_current_span(
        "main_agent_orchestration",
        attributes={"sqlite_run_id": current_run_id, "question": QUESTION},
    ):
        agent.run(
            task=TASK_ORCHESTRATOR,
            max_steps=30,
            additional_args={
                "path_to_ifc_file": "/Users/sylvainhellin/GitHub/ifcAnswerEngineV3/src/bim_models/duplex/arc.ifc",
                "question_id": 1,
                "question": QUESTION,
            },
        )
finally:
    if db_conn:
        db_conn.close()
        print("SQLite connection closed.")

# TODO: use the additional_arg argument when calling agent.run() to pass more information (like model path, etc.)

# # %%

# from smolagents import GradioUI

# GradioUI(agent).launch()
# # %%
