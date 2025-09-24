from typing import List, Optional, Tuple, Dict
import json

import mlflow
from mlflow import MlflowClient
from mlflow.entities import Experiment, Run, Trace, RunData


class CustomMLFlowClient(MlflowClient):
    run: Optional[Run] = None
    runData: Optional[RunData] = None
    experiment: Optional[Experiment] = None
    traces: Optional[List[Trace]] = None
    metrics: Optional[Dict] = None

    def set_experiment_by_name(self, name: str):
        self.experiment = self.get_experiment_by_name(name=name)

    def get_runs(
        self,
    ) -> List[Run]:
        runs = []
        if self.experiment is not None:
            paged_list = self.search_runs(
                experiment_ids=[self.experiment.experiment_id]
            )
            runs = [run for run in paged_list]
        return runs

    def set_run_by_name(
        self,
        name: str,
    ) -> Optional[Tuple[int, Run]]:
        runs = self.get_runs()
        for run in runs:
            if name == (run.data.tags.get("mlflow.runName")):
                self.run = run
                self.runData = run.data
                self.metrics = run.data.metrics

    def setup(
        self,
        experiment_name: str,
        run_name: str,
    ):
        self.set_experiment_by_name(name=experiment_name)
        self.set_run_by_name(name=run_name)
        self.set_traces()

    def dump_run_metrics(self):
        print(json.dumps(getattr(self.runData, "metrics", {}), indent=2))

    def set_traces(self) -> None:
        self.traces = []

        if self.experiment is not None and self.run is not None:
            for trace in self.search_traces(
                experiment_ids=[self.experiment.experiment_id],
                run_id=self.run.info.run_id,
            ):
                self.traces.append(trace)

    def get_similarity_scores(self) -> List[float]:
        scores: List[float] = []
        for trace in self.traces or []:
            score = float(trace.info.to_dict().get("tags", {}).get("similarity score"))
            if score is not None:
                scores.append(score)
        return scores


if __name__ == "__main__":
    from src.config import MLFLOW_URI

    mlflow.set_tracking_uri(MLFLOW_URI)
    client = CustomMLFlowClient()

    # Define paramenters
    experiment_name = "Training"
    run_name = "2025-09-24-14-47-45"

    # Setup the client
    client.setup(
        experiment_name=experiment_name,
        run_name=run_name,
    )

    # print(client.experiment)
    # print(client.run)
    client.dump_run_metrics()
    scores = client.get_similarity_scores()
    for score in scores[:5]:
        print(score)

    correct_answer = []
    for score in scores:
        if isinstance(score, str):
            print(score)

            print(type(score))
        if score >= 0.85:
            correct_answer.append(1)
        else:
            correct_answer.append(0)
    acc = sum(correct_answer) / len(correct_answer)
    print(f"Accuracy of the run: {acc}")

    for idx, trace in enumerate(client.traces[:5]) if client.traces is not None else []:
        print(f"\n#### Trace Nr. {idx + 1} info ####\n")
        # print(json.dumps(trace.info.to_dict(), indent=2))
        print(
            f"Similarity score: {trace.info.to_dict().get('tags', {}).get('similarity score')}"
        )
        # print("\n#### Trace data ####\n")
        # print(trace.data)


# TODO Continue here
# for trace in traces:
#     spans = [span for span in trace.data.spans]
#     for span in spans:
#         print(span.name)
#         spanType = span.attributes["mlflow.spanType"]
#         print(spanType)

#         if span.attributes["mlflow.spanType"] == "CHAT_MODEL":
#             model = span.attributes["model"]
#             chat = get_chat_messages(span=span)
#             chat.model = model
#             attributes = span.attributes.keys()

#         if spanType == "TOOL":
#             if span.attributes["name"] == "python_interpreter":
#                 code = span.attributes["mlflow.spanInputs"]["python_code"]
#                 print_outputs, returned_value, is_final = span.attributes[
#                     "mlflow.spanOutputs"
#                 ]

#         if spanType == "CHAIN":
#             print(json.dumps(span.attributes, indent=2))
#         # print(span.attributes["mlflow.spanInputs"])
#         # print(span.attributes["mlflow.spanOutputs"])
# span_type = Optional[
#     Literal[
#         "TOOL",
#         "CHAIN",
#         "PARSER",
#         "UNKNOWN",
#         "CHAT_MODEL",
#         "LLM",
#         "MODULE",
#         "QUESTION",
#     ]
# ]
