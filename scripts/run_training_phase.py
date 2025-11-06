"""
The orchestration of the multi-agent system that generates, updates and prunes the tools for extracting information from BIM models. These tools are then used by Cobbie at inference time.
"""

from typing import Tuple
from src.agents import (
    answer_verifier,
    cobbie,
    create_helper_function,
    identify_helper_function,
)
from src.experiment.datasets import TRAINSET
from src.experiment.db.models import IfcBench
from enum import Enum, auto
from pydantic import BaseModel

# Enum to implement the state machine pattern for orchestrating the control flow of the training phase
class TrainingState(Enum):
    start = auto(),
    process_question = auto(),
    verify_answer = auto(),
    identify_new_tool = auto(),
    identify_faulty_tool = auto(),
    error = auto(),
    end = auto(),

# Object to handle the context added by each agent for each qa_pair processing
class Context(BaseModel):
    qa_pair: IfcBench
    # continue with all results types from each agents, e.g. FinalAnswer. Initialize to None

# def main function for calling the right function to process the current state
def process_state(state: TrainingState, context: Context) -> Tuple[TrainingState, Context]:
    new_state = TrainingState.error
    updated_context = context

    if state == TrainingState.start:
        new_state, updated_context = handle_start_state(context=context)

    # TODO handle each possible state
    return new_state, updated_context

# Loop through each question
for qa_pair in TRAINSET:
    # TODO: Start the main mlflow run

    # init the context and state for this pass
    context: Context = Context(qa_pair=qa_pair)
    state: TrainingState = TrainingState.start

    while state not in [TrainingState.end, TrainingState.error]:
        state, context = process_state(state, context)


# def functions for handling each state; They all should take the context as input, and return an updated version of it, with the new state
def handle_start_state(context: Context) -> Tuple[TrainingState, Context]:
    # start the mlflow nested run,
    return TrainingState.process_question, context

# TODO implement functions to handle each state
