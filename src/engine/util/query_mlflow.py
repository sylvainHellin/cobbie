import json
import sys
import os
from typing import Literal, Optional, List, Tuple

from dotenv import load_dotenv, find_dotenv
import mlflow
from mlflow import MlflowClient
from mlflow.entities import Span, Experiment, Run, Trace

load_dotenv(find_dotenv())
ROOT_PATH = os.getenv("ROOT_PATH", "")
sys.path.append(ROOT_PATH)

from src.config import MLFLOW_URI
from src.engine.schemas import Chat, Message

mlflow.set_tracking_uri(MLFLOW_URI)
client = MlflowClient()

experiment_name = "Training"
run_name = "2025-07-24-09-17-10"
experiment = client.get_experiment_by_name(name=experiment_name)
assert experiment is not None, (
    f"Couldn't find an experiment with this name: {experiment_name}"
)
runs = client.search_runs(
    experiment_ids=[experiment.experiment_id],
)


def get_experiment_by_name(name: str) -> Optional[Experiment]:
    return client.get_experiment_by_name(name=name)


def get_runs(
    experiment: Experiment,
) -> List[Run]:
    paged_list = client.search_runs(experiment_ids=[experiment.experiment_id])
    output = [run for run in paged_list]
    return output


def get_run(
    runs: List[Run],
    run_name: str,
) -> Optional[Tuple[int, Run]]:
    for run in runs:
        if run_name == (run.data.tags.get("mlflow.runName")):
            return (run.info.run_id, run)


def get_traces(
    experiment: Experiment,
    run_id: Optional[str],
) -> List[Trace]:
    traces = [
        trace
        for trace in client.search_traces(
            experiment_ids=[experiment.experiment_id],
            run_id=run_id,
        )
    ]

    return traces


def get_spans(
    trace: Trace,
    span_type: Optional[
        Literal[
            "TOOL",
            "CHAIN",
            "PARSER",
            "UNKNOWN",
            "CHAT_MODEL",
            "LLM",
            "MODULE",
            "QUESTION",
        ]
    ],
) -> List[Span]:
    spans = [span for span in trace.data.spans]

    if span_type:
        filtered_spans = []

        for span in spans:
            spanType = span.attributes["mlflow.spanType"]
            if spanType == span_type:
                filtered_spans.append(span)

        return filtered_spans

    else:
        return spans


def get_chat_messages(span: Span) -> Chat:
    chat = Chat()
    if span.attributes["mlflow.spanType"] == "CHAT_MODEL":
        for msg in span.attributes["mlflow.chat.messages"]:
            role = msg["role"]
            content = msg["content"]
            chat.append_msg(Message(role=role, content=content))
    return chat


# TODO Continue here
for trace in traces:
    spans = [span for span in trace.data.spans]
    for span in spans:
        print(span.name)
        spanType = span.attributes["mlflow.spanType"]
        print(spanType)

        if span.attributes["mlflow.spanType"] == "CHAT_MODEL":
            model = span.attributes["model"]
            chat = get_chat_messages(span=span)
            chat.model = model
            attributes = span.attributes.keys()

        if spanType == "TOOL":
            if span.attributes["name"] == "python_interpreter":
                code = span.attributes["mlflow.spanInputs"]["python_code"]
                print_outputs, returned_value, is_final = span.attributes[
                    "mlflow.spanOutputs"
                ]

        if spanType == "CHAIN":
            print(json.dumps(span.attributes, indent=2))
        # print(span.attributes["mlflow.spanInputs"])
        # print(span.attributes["mlflow.spanOutputs"])
span_type = Optional[
    Literal[
        "TOOL",
        "CHAIN",
        "PARSER",
        "UNKNOWN",
        "CHAT_MODEL",
        "LLM",
        "MODULE",
        "QUESTION",
    ]
]
