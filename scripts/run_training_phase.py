"""
The orchestration of the multi-agent system that generates, updates and prunes the tools
for extracting information from BIM models. These tools are then used by Cobbie at inference time.
"""

import argparse
import os
import time
from datetime import datetime
from enum import Enum, auto
from typing import Literal, Tuple, cast

import mlflow
from loguru import logger

from src.agents import (
    assess_helper_function,
    cobbie,
    create_helper_function,
    debug_helper_function,
    derive_binary_classification,
    identify_faulty_tool,
    identify_helper_function,
    verify_answer,
)
from src.config import LOG_LEVEL, ROOT_PATH
from src.db import TRAINSET
from src.db.query import (
    get_tools_ranked_by_deletion_score,
    increment_tool_inclusion,
    initialize_tool_metadata,
    update_tool_usage,
)
from src.schemas.training_context import Context
from src.util import (
    _create_function_from_source_code,
    delete_tool,
    extract_tools_used,
    generate_tools_docs,
    get_created_tools,
    get_function_code,
    save_new_tool,
    setup_logger,
)
from src.util.metrics import calculate_aggregate_metrics, log_qa_metrics
from src.util.mlflow_utils import determine_run_id

# Initialize logger
setup_logger()
LLM_NAME = "GLM 4.7"


# Enum to implement the state machine pattern for orchestrating the control flow of the training phase
class TrainingState(Enum):
    START = auto()
    RUN_COBBIE = auto()
    VERIFY_ANSWER = auto()

    # Path A: Correct answer
    IDENTIFY_NEW_TOOL = auto()
    CREATE_NEW_TOOL = auto()

    # Path B: Wrong answer
    IDENTIFY_FAULTY_TOOL = auto()
    DEBUG_FAULTY_TOOL = auto()

    # Tool testing (both paths)
    TEST_TOOL_WITH_COBBIE = auto()
    ASSESS_TOOL_USAGE = auto()
    DECIDE_TOOL_FATE = auto()

    # Terminal states
    END = auto()
    ERROR = auto()


# ============================================================================
# State Handler Functions
# ============================================================================


def handle_start_state(context: Context) -> Tuple[TrainingState, Context]:
    """
    Initialize tools for this QA pair.

    Steps:
    1. Check if tool count exceeds MAX_TOOLS
    2. Delete lowest-value tools if necessary
    3. Load remaining tools
    4. Track tool inclusion in database

    Returns:
        Next state: RUN_COBBIE
    """
    # Check tool count
    current_tools = get_created_tools()

    if len(current_tools) > context.max_tools:
        num_to_delete = len(current_tools) - context.max_tools
        logger.info(
            f"Tool count ({len(current_tools)}) exceeds MAX_TOOLS ({context.max_tools})"
        )
        logger.info(f"Deleting {num_to_delete} lowest-value tools...")

        # Get ranked tools by deletion score
        ranked_tools = get_tools_ranked_by_deletion_score(
            grace_period=context.grace_period,
        )

        # Delete top N by score
        deleted_count = 0
        for tool_name, score in ranked_tools[:num_to_delete]:
            logger.info(f"  Deleting '{tool_name}' (score={score:.1f})")
            if delete_tool(tool_name):
                deleted_count += 1

        logger.info(f"Deleted {deleted_count}/{num_to_delete} tools")

        # Log to MLflow
        if mlflow.active_run():
            mlflow.log_metrics(
                {
                    f"tools_deleted_at_q{context.global_question_num}": deleted_count,
                    "current_tool_count": len(get_created_tools()),
                }
            )

    # Load available tools
    context.tools = get_created_tools()

    # Track tool inclusion
    available_tool_names = list(context.tools.keys())
    increment_tool_inclusion(available_tool_names, context.global_question_num)

    logger.info(f"Loaded {len(context.tools)} tools for question {context.qa_pair.id}")

    return TrainingState.RUN_COBBIE, context


def handle_run_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Run Cobbie agent to answer the question.

    Actions:
    1. Generate tools documentation
    2. Call cobbie() with tools
    3. Store result, collector, history in context
    4. Log metrics to MLflow span

    Returns:
        Next state: VERIFY_ANSWER
    """
    # Get IFC model path
    ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

    logger.info(f"Running Cobbie for question: {context.qa_pair.question}")

    start_time = time.time()

    try:
        result, collector, history = cobbie(
            user_input=context.qa_pair.question,
            tools=context.tools,
            max_iterations=10,
            model_path=ifc_path,
            client="GLM_4_7",
        )

        context.cobbie_result = result
        context.cobbie_collector = collector
        context.cobbie_history = history
        context.cobbie_duration = time.time() - start_time

        logger.info(f"Cobbie completed in {context.cobbie_duration:.2f}s")
        logger.info(f"Cobbie answer: {result.answer}")

        return TrainingState.VERIFY_ANSWER, context

    except Exception as e:
        logger.error(f"Error running Cobbie: {e}")
        context.error_message = f"Cobbie error: {e}"
        context.cobbie_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_verify_answer(context: Context) -> Tuple[TrainingState, Context]:
    """
    Verify if Cobbie's answer is correct.

    Actions:
    1. Call verify_answer() with question, ground truth, system response
    2. Store result in context
    3. Branch based on classification

    Returns:
        Next state:
        - IDENTIFY_NEW_TOOL if classification == "correct"
        - IDENTIFY_FAULTY_TOOL if classification == "wrong"
        - END if classification == "abstained"
    """
    logger.info("Verifying answer...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")

        # Category must be an integer between 1-4
        category = context.qa_pair.category if context.qa_pair.category else 1

        result, collector = verify_answer(
            question=context.qa_pair.question,
            category=category,  # type: ignore
            ground_truth=context.qa_pair.ground_truth,
            system_response=context.cobbie_result.answer,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )

        context.verify_result = result
        classification = derive_binary_classification(result=result)
        context.verify_collector = collector
        context.verify_duration = time.time() - start_time

        logger.info(f"Verification result: {classification}")
        logger.info(f"Justification: {result.justification}")

        # Log the answer and all evaluation criteria for later access
        mlflow.log_params(
            {
                "justification": result.justification,
                "cobbie_answer": context.cobbie_result.answer,
                "abstention": str(result.abstention),
                "faithfulness": str(result.faithfulness),
                "completeness": str(result.completeness),
                "transparency": str(result.transparency),
                "relevance": str(result.relevance),
                "derived_classification": classification,
            }
        )

        # Track tool usage for this question
        available_tool_names = list(context.tools.keys())
        tools_used = extract_tools_used(context.cobbie_history, available_tool_names)
        is_correct = classification == "correct"
        update_tool_usage(tools_used, is_correct, context.global_question_num)

        # Log tool usage metrics to MLflow
        mlflow.log_metric(
            "num_tools_used", len(tools_used), step=context.global_question_num
        )

        logger.info(f"Tracked usage of {len(tools_used)} tools: {tools_used}")

        # Determine next state based on classification
        if classification == "correct":
            context.path_taken = "correct"
            logger.info("Answer CORRECT - Following Path A (identify new tool)")
            return TrainingState.IDENTIFY_NEW_TOOL, context
        elif classification == "wrong":
            context.path_taken = "wrong"
            logger.info("Answer WRONG - Following Path B (identify faulty tool)")
            return TrainingState.IDENTIFY_FAULTY_TOOL, context
        else:  # "abstained"
            context.path_taken = "abstained"
            logger.info("Answer ABSTAINED - Skipping both paths")
            return TrainingState.END, context

    except Exception as e:
        logger.error(f"Error verifying answer: {e}")
        context.error_message = f"Answer verification error: {e}"
        context.verify_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_identify_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Identify if a new helper function should be created (Path A: Correct answer).

    Actions:
    1. Generate existing tools documentation
    2. Call identify_helper_function() with history and question
    3. Store result in context
    4. Decide if tool creation is needed

    Returns:
        Next state:
        - CREATE_NEW_TOOL if new_tool == True
        - END if new_tool == False
    """
    logger.info("Identifying potential new tool...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")

        # Generate existing tools docs
        existing_tools_docs = generate_tools_docs(context.tools)

        # Construct full history with final answer
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector = identify_helper_function(
            history=full_history,
            example_question=context.qa_pair.question,
            existing_helper_functions=existing_tools_docs,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )

        context.identify_tool_result = result
        context.identify_tool_collector = collector
        context.identify_tool_duration = time.time() - start_time

        logger.info(f"Tool management action: {result.action}")
        logger.info(f"Tool name: {result.tool_name}")
        logger.info(f"Tool description: {result.tool_description}")

        # Handle new action field
        if result.action == "create_new":
            logger.info(f"Creating new tool: {result.tool_name}")
            context.tool_name = result.tool_name
            context.is_enhancement = False
            return TrainingState.CREATE_NEW_TOOL, context

        elif result.action == "enhance_existing":
            logger.info(f"Enhancing existing tool: {result.tool_name}")
            context.tool_name = result.tool_name
            context.is_enhancement = True
            return TrainingState.CREATE_NEW_TOOL, context

        else:  # "none"
            logger.info("No tool creation or enhancement needed")
            return TrainingState.END, context

    except Exception as e:
        logger.error(f"Error identifying new tool: {e}")
        context.error_message = f"Identify new tool error: {e}"
        context.identify_tool_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_create_new_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Create new tool OR enhance existing tool (Path A: Correct answer).

    CHANGED: No longer saves the tool immediately.
    Instead, transitions to TEST_TOOL_WITH_COBBIE for validation.

    Actions:
    1. Get IFC model path from QA pair
    2. Get other BIM models for testing
    3. If enhancing: Get existing implementation
    4. Call create_helper_function()
    5. If success: Mark as created/updated, transition to testing
    6. If failure: Log error

    Returns:
        Next state:
        - TEST_TOOL_WITH_COBBIE if success
        - ERROR if failure
    """
    action_verb = "Enhancing" if context.is_enhancement else "Creating"
    logger.info(f"{action_verb} tool: {context.tool_name}...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")
        if not context.identify_tool_result:
            raise ValueError("Identify tool result is None")
        if not context.tool_name:
            raise ValueError("Tool name is None")

        # Get IFC model path from the QA pair (same model used for answering)
        ifc_model_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

        if not ifc_model_path:
            raise ValueError("No IFC model path available for tool creation")

        # Get other BIM models for testing (from bim_models directory)
        bim_models_dir = os.path.join(ROOT_PATH, "src/db/bim_models")
        other_models = []
        if os.path.exists(bim_models_dir):
            other_models = [
                os.path.join(bim_models_dir, f)
                for f in os.listdir(bim_models_dir)
                if f.endswith(".ifc")
                and os.path.join(bim_models_dir, f) != ifc_model_path
            ][:3]  # Limit to 3 other models

        # Construct full history
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        # Get existing implementation if enhancing
        existing_implementation = None
        if context.is_enhancement:
            code_result = get_function_code(context.tool_name)
            if code_result.is_err():
                raise ValueError(
                    f"Could not retrieve tool code: {code_result.unwrap_err()}"
                )
            existing_implementation = code_result.unwrap()

        result, collector, creation_history = create_helper_function(
            history=full_history,
            example_question=context.qa_pair.question,
            example_answer=context.qa_pair.ground_truth,
            example_bim_model=ifc_model_path,
            other_bim_models_for_testing=other_models,
            function_name=context.identify_tool_result.tool_name,
            function_description=context.identify_tool_result.tool_description,
            is_enhancement=context.is_enhancement,
            existing_implementation=existing_implementation,
            max_iterations=15,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )

        context.create_tool_result = result
        context.create_tool_collector = collector
        context.create_tool_history = creation_history
        context.create_tool_duration = time.time() - start_time

        logger.info(f"Tool creation success: {result.success}")

        if result.success:
            # Don't save immediately - proceed to testing first
            if context.is_enhancement:
                logger.info(
                    f"Tool enhanced: {context.tool_name}, proceeding to testing"
                )
                context.tool_updated = True
            else:
                logger.info(
                    f"New tool created: {context.tool_name}, proceeding to testing"
                )
                context.tool_created = True

            return TrainingState.TEST_TOOL_WITH_COBBIE, context
        else:
            logger.warning(f"Tool creation was not successful: {result.thoughts}")
            context.error_message = f"Tool creation failed: {result.thoughts}"
            return TrainingState.ERROR, context

    except Exception as e:
        logger.error(f"Error creating new tool: {e}")
        context.error_message = f"Create tool error: {e}"
        context.create_tool_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_identify_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Identify if a faulty helper function caused the wrong answer (Path B: Wrong answer).

    Actions:
    1. Generate existing tools documentation
    2. Call identify_faulty_tool() with history, answers, and justification
    3. Store result in context
    4. Decide if tool debugging is needed

    Returns:
        Next state:
        - DEBUG_FAULTY_TOOL if faulty_tool == True
        - END if faulty_tool == False
    """
    logger.info("Identifying faulty tool...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")
        if not context.verify_result:
            raise ValueError("Verify result is None")

        # Generate existing tools docs
        existing_tools_docs = generate_tools_docs(context.tools)

        # Construct full history with final answer
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector = identify_faulty_tool(
            history=full_history,
            question=context.qa_pair.question,
            ground_truth=context.qa_pair.ground_truth,
            provided_answer=context.cobbie_result.answer,
            justification=context.verify_result.justification,
            existing_helper_functions=existing_tools_docs,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )

        context.identify_faulty_result = result
        context.identify_faulty_collector = collector
        context.identify_faulty_duration = time.time() - start_time

        logger.info(f"Faulty tool identified: {result.faulty_tool}")
        if result.faulty_tool:
            logger.info(f"Faulty tool name: {result.faulty_tool_name}")
            logger.info(f"Error description: {result.error_description}")
            logger.info(f"Confidence: {result.confidence}")

        # Decide next state
        if result.faulty_tool:
            context.tool_name = result.faulty_tool_name
            return TrainingState.DEBUG_FAULTY_TOOL, context
        else:
            logger.info("No faulty tool identified - error was due to other reasons")
            return TrainingState.END, context

    except Exception as e:
        logger.error(f"Error identifying faulty tool: {e}")
        context.error_message = f"Identify faulty tool error: {e}"
        context.identify_faulty_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_debug_faulty_tool(context: Context) -> Tuple[TrainingState, Context]:
    """
    Debug and fix a faulty helper function (Path B: Wrong answer).

    Actions:
    1. Get faulty tool source code with get_function_code()
    2. Get IFC model path from QA pair
    3. Call debug_helper_function()
    4. If success: Mark as updated, transition to testing
    5. If failure: Log error

    Returns:
        Next state:
        - TEST_TOOL_WITH_COBBIE if success
        - ERROR if failure
    """
    logger.info(f"Debugging faulty tool: {context.tool_name}...")

    start_time = time.time()

    try:
        if not context.cobbie_result:
            raise ValueError("Cobbie result is None")
        if not context.identify_faulty_result:
            raise ValueError("Identify faulty result is None")
        if not context.tool_name:
            raise ValueError("Tool name is None")

        # Get the faulty tool's source code
        faulty_code_result = get_function_code(context.tool_name)

        if faulty_code_result.is_err():
            raise ValueError(
                f"Could not retrieve faulty tool code: {faulty_code_result.unwrap_err()}"
            )

        faulty_implementation = faulty_code_result.unwrap()

        # Get IFC model path from the QA pair (same model used for answering)
        ifc_model_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

        if not ifc_model_path:
            raise ValueError("No IFC model path available for tool debugging")

        # Construct full history
        full_history = (
            f"{context.cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.cobbie_result.thoughts}\n"
            f"Answer: {context.cobbie_result.answer}"
        )

        result, collector, debug_history = debug_helper_function(
            faulty_function_name=context.tool_name,
            faulty_function_implementation=faulty_implementation,
            error_description=context.identify_faulty_result.error_description,
            history_faulty_tool_use=full_history,
            ifc_model_path=ifc_model_path,
            max_iterations=15,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )

        context.debug_tool_result = result
        context.debug_tool_collector = collector
        context.debug_tool_history = debug_history
        context.debug_tool_duration = time.time() - start_time

        logger.info(f"Tool debugging success: {result.success}")

        if result.success:
            # Don't save immediately - proceed to testing first
            logger.info(
                f"Faulty tool debugged: {context.tool_name}, proceeding to testing"
            )
            logger.info(f"Changes summary: {result.changes_summary}")
            context.tool_updated = True

            return TrainingState.TEST_TOOL_WITH_COBBIE, context
        else:
            logger.warning(f"Tool debugging was not successful: {result.thoughts}")
            context.error_message = f"Tool debugging failed: {result.thoughts}"
            return TrainingState.ERROR, context

    except Exception as e:
        logger.error(f"Error debugging faulty tool: {e}")
        context.error_message = f"Debug tool error: {e}"
        context.debug_tool_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_test_tool_with_cobbie(context: Context) -> Tuple[TrainingState, Context]:
    """
    Re-run Cobbie with enhanced question to test the new/updated tool.

    Actions:
    1. Temporarily add the new/updated tool to the tools dictionary
    2. Enhance the question to encourage using the tool
    3. Run Cobbie with the enhanced question
    4. Store test results in context
    5. Transition to assessment

    Returns:
        Next state: ASSESS_TOOL_USAGE
    """
    logger.info(f"Testing tool with Cobbie: {context.tool_name}...")

    start_time = time.time()

    try:
        # Assert tool_name is not None (should be set by previous states)
        assert context.tool_name is not None, "tool_name should be set before testing"

        # Get the tool implementation
        if context.create_tool_result:
            tool_implementation = context.create_tool_result.function_implementation
            logger.info(f"Testing newly created tool: {context.tool_name}")
        elif context.debug_tool_result:
            tool_implementation = context.debug_tool_result.fixed_implementation
            logger.info(f"Testing debugged tool: {context.tool_name}")
        else:
            raise ValueError("No tool implementation available for testing")

        creation_result = _create_function_from_source_code(
            function_name=context.tool_name,
            code=tool_implementation,
        )

        if creation_result.is_err():
            error_msg = (
                f"Failed to create function for testing: {creation_result.unwrap_err()}"
            )
            logger.error(error_msg)
            context.error_message = error_msg
            return TrainingState.ERROR, context

        new_tool = creation_result.unwrap()

        # Create a copy of tools with the new tool added
        test_tools = context.tools.copy()
        test_tools[context.tool_name] = new_tool

        logger.info(
            f"Tool '{context.tool_name}' added to test environment. Total tools: {len(test_tools)}"
        )

        # Enhance the question to guide tool usage
        enhanced_question = (
            f"{context.qa_pair.question}\n\n"
            f"NOTE: A helper function `{context.tool_name}` was recently created. "
            f"If it seems relevant, consider using it to help answer this question."
        )

        # Get IFC model path
        ifc_path = context.qa_pair.ifc.model_path if context.qa_pair.ifc else None

        # Run Cobbie with enhanced question and test tools
        result, collector, history = cobbie(
            user_input=enhanced_question,
            tools=test_tools,
            max_iterations=10,
            model_path=ifc_path,
            client="GLM_4_7",
        )

        context.test_cobbie_result = result
        context.test_cobbie_collector = collector
        context.test_cobbie_history = history
        context.test_cobbie_duration = time.time() - start_time

        logger.info(f"Tool testing Cobbie run completed: {result.answer[:100]}...")
        return TrainingState.ASSESS_TOOL_USAGE, context

    except Exception as e:
        logger.error(f"Error testing tool with Cobbie: {e}")
        context.error_message = f"Tool testing error: {e}"
        context.test_cobbie_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_assess_tool_usage(context: Context) -> Tuple[TrainingState, Context]:
    """
    Analyze if the tested tool was helpful during Cobbie's execution.

    Actions:
    1. Verify the test answer with verify_answer agent
    2. Get tool description from creation/debugging context
    3. Call assess_helper_function to analyze tool usage
    4. Store assessment in context
    5. Transition to decision state

    Returns:
        Next state: DECIDE_TOOL_FATE
    """
    logger.info(f"Assessing tool usage: {context.tool_name}...")

    start_time = time.time()

    try:
        # Assert tool_name is not None (should be set by previous states)
        assert context.tool_name is not None, (
            "tool_name should be set before assessment"
        )

        # Assert category is valid (1-4)
        assert context.qa_pair.category is not None and context.qa_pair.category in [
            1,
            2,
            3,
            4,
        ], "category must be 1-4"
        category = cast(Literal[1, 2, 3, 4], context.qa_pair.category)

        # Verify the test answer
        verify_start = time.time()
        assert context.test_cobbie_result is not None, (
            "The test_cobbie_result in context cannot be None at this step."
        )
        verify_result, verify_collector = verify_answer(
            question=context.qa_pair.question,
            category=category,
            ground_truth=context.qa_pair.ground_truth,
            system_response=context.test_cobbie_result.answer,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )
        context.test_verify_result = verify_result
        context.test_verify_collector = verify_collector
        context.test_verify_duration = time.time() - verify_start

        classification = derive_binary_classification(result=verify_result)
        logger.info(f"Test answer verified: {classification}")

        # Get tool description based on path
        if context.create_tool_result:
            assert context.identify_tool_result is not None
            tool_description = context.identify_tool_result.tool_description
        elif context.debug_tool_result:
            assert context.identify_faulty_result is not None
            tool_description = context.identify_faulty_result.error_description
        else:
            raise ValueError("No tool context available for assessment")

        # Construct full test history with final answer
        full_test_history = (
            f"{context.test_cobbie_history}\n\n"
            f"--- Final Answer ---\n"
            f"Thoughts: {context.test_cobbie_result.thoughts}\n"
            f"Answer: {context.test_cobbie_result.answer}"
        )

        # Assess tool usage
        assess_start = time.time()
        assessment, assessment_collector = assess_helper_function(
            execution_history=full_test_history,
            original_question=context.qa_pair.question,
            ground_truth_answer=context.qa_pair.ground_truth,
            tested_tool_name=context.tool_name,
            tested_tool_description=tool_description,
            final_answer=context.test_cobbie_result.answer,
            answer_correctness=classification,
            llm_provider="zai",
            llm_name=LLM_NAME,
        )
        context.tool_assessment = assessment
        context.tool_assessment_collector = assessment_collector
        context.tool_assessment_duration = time.time() - assess_start

        logger.info(
            f"Tool assessment completed: {assessment.recommendation} "
            f"(quality: {assessment.tool_usage_quality}, confidence: {assessment.confidence})"
        )

        context.tool_assessment_duration = time.time() - start_time
        return TrainingState.DECIDE_TOOL_FATE, context

    except Exception as e:
        logger.error(f"Error assessing tool usage: {e}")
        context.error_message = f"Tool assessment error: {e}"
        context.tool_assessment_duration = time.time() - start_time
        return TrainingState.ERROR, context


def handle_decide_tool_fate(context: Context) -> Tuple[TrainingState, Context]:
    """
    Decide whether to keep, discard, or flag the tool based on assessment.

    Actions:
    1. Examine the assessment recommendation
    2. Make final decision on tool fate
    3. Save tool if recommended (keep_tool)
    4. Log decision and rationale
    5. Update context metadata

    Returns:
        Next state: END
    """
    logger.info(f"Deciding fate of tool: {context.tool_name}...")

    try:
        # Assert tool_name is not None (should be set by previous states)
        assert context.tool_name is not None, (
            "tool_name should be set before deciding fate"
        )

        assessment = context.tool_assessment
        assert assessment is not None

        # Get tool implementation
        if context.create_tool_result:
            tool_implementation = context.create_tool_result.function_implementation
        elif context.debug_tool_result:
            tool_implementation = context.debug_tool_result.fixed_implementation
        else:
            raise ValueError("No tool implementation available")

        # Decision logic based on recommendation
        if assessment.recommendation == "keep_tool":
            # Tool is helpful, save it permanently
            save_success = save_new_tool(
                function_name=context.tool_name,
                function_implementation=tool_implementation,
                global_question_num=context.global_question_num,
            )

            if save_success:
                context.tool_saved = True
                logger.info(
                    f"✅ Tool '{context.tool_name}' validated and saved permanently\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Details: {assessment.usage_details[:200]}..."
                )

                # Reload tools to include the new one
                context.tools = get_created_tools()
                logger.info(f"Tools reloaded. Now have {len(context.tools)} tools")

                return TrainingState.END, context
            else:
                logger.error(f"Failed to save tool: {context.tool_name}")
                context.error_message = f"Failed to save tool: {context.tool_name}"
                return TrainingState.ERROR, context

        elif assessment.recommendation == "discard_tool":
            # Tool is not useful or harmful, discard it
            context.tool_saved = False

            # If we were debugging a faulty tool (Path B), delete it from disk
            if context.path_taken == "wrong":
                delete_success = delete_tool(context.tool_name)
                if delete_success:
                    logger.info(
                        f"❌ Tool '{context.tool_name}' discarded and deleted from disk\n"
                        f"   Quality: {assessment.tool_usage_quality}\n"
                        f"   Confidence: {assessment.confidence}\n"
                        f"   Reason: {assessment.usage_details[:200]}..."
                    )
                else:
                    logger.error(
                        f"Failed to delete discarded tool: {context.tool_name}"
                    )
                    context.error_message = (
                        f"Failed to delete discarded tool: {context.tool_name}"
                    )
                    return TrainingState.ERROR, context
            else:
                # Path A enhancement failed - keep original working version
                logger.info(
                    f"❌ Tool '{context.tool_name}' enhancement discarded (original preserved)\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Reason: {assessment.usage_details[:200]}..."
                )

            return TrainingState.END, context

        elif assessment.recommendation == "improve_tool":
            # Tool has potential but needs work
            context.tool_saved = False

            # If we were debugging a faulty tool (Path B), delete it from disk
            if context.path_taken == "wrong":
                delete_success = delete_tool(context.tool_name)
                if delete_success:
                    logger.info(
                        f"⚠️  Tool '{context.tool_name}' needs improvement - deleted from disk\n"
                        f"   Quality: {assessment.tool_usage_quality}\n"
                        f"   Confidence: {assessment.confidence}\n"
                        f"   Issues: {assessment.usage_details[:200]}..."
                    )
                else:
                    logger.error(
                        f"Failed to delete tool needing improvement: {context.tool_name}"
                    )
                    context.error_message = (
                        f"Failed to delete tool: {context.tool_name}"
                    )
                    return TrainingState.ERROR, context
            else:
                # Path A enhancement needs work - keep original working version
                logger.info(
                    f"⚠️  Tool '{context.tool_name}' enhancement needs improvement (original preserved)\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Issues: {assessment.usage_details[:200]}..."
                )

            return TrainingState.END, context

        else:  # unclear
            # Path B (faulty tool): Delete it - defensive approach
            if context.path_taken == "wrong":
                context.tool_saved = False
                delete_success = delete_tool(context.tool_name)
                if delete_success:
                    logger.info(
                        f"❓ Tool '{context.tool_name}' assessment unclear - deleted (defensive)\n"
                        f"   Quality: {assessment.tool_usage_quality}\n"
                        f"   Confidence: {assessment.confidence}\n"
                        f"   Note: {assessment.usage_details[:200]}..."
                    )
                else:
                    logger.error(f"Failed to delete unclear tool: {context.tool_name}")
                    context.error_message = (
                        f"Failed to delete tool: {context.tool_name}"
                    )
                    return TrainingState.ERROR, context

                return TrainingState.END, context

            # Path A enhancement: Keep original working version (don't save unclear enhancement)
            elif context.is_enhancement:
                context.tool_saved = False
                logger.info(
                    f"❓ Tool '{context.tool_name}' enhancement unclear - original preserved\n"
                    f"   Quality: {assessment.tool_usage_quality}\n"
                    f"   Confidence: {assessment.confidence}\n"
                    f"   Note: {assessment.usage_details[:200]}..."
                )
                return TrainingState.END, context

            # Path A create_new: Save tentatively with benefit of doubt
            else:
                save_success = save_new_tool(
                    function_name=context.tool_name,
                    function_implementation=tool_implementation,
                    global_question_num=context.global_question_num,
                )

                if save_success:
                    context.tool_saved = True
                    logger.info(
                        f"❓ New tool '{context.tool_name}' assessment unclear, saved tentatively\n"
                        f"   Quality: {assessment.tool_usage_quality}\n"
                        f"   Confidence: {assessment.confidence}\n"
                        f"   Note: {assessment.usage_details[:200]}..."
                    )

                    # Reload tools
                    context.tools = get_created_tools()
                    return TrainingState.END, context
                else:
                    logger.error(f"Failed to save tool: {context.tool_name}")
                    context.error_message = f"Failed to save tool: {context.tool_name}"
                    return TrainingState.ERROR, context

    except Exception as e:
        logger.error(f"Error deciding tool fate: {e}")
        context.error_message = f"Tool fate decision error: {e}"
        return TrainingState.ERROR, context


# ============================================================================
# State Machine Dispatcher
# ============================================================================


def process_state(
    state: TrainingState, context: Context
) -> Tuple[TrainingState, Context]:
    """
    Dispatcher function that routes to the appropriate state handler.

    Args:
        state: Current training state
        context: Context with all agent results and metadata

    Returns:
        Tuple of (next_state, updated_context)
    """
    if state == TrainingState.START:
        return handle_start_state(context)
    elif state == TrainingState.RUN_COBBIE:
        return handle_run_cobbie(context)
    elif state == TrainingState.VERIFY_ANSWER:
        return handle_verify_answer(context)
    elif state == TrainingState.IDENTIFY_NEW_TOOL:
        return handle_identify_new_tool(context)
    elif state == TrainingState.CREATE_NEW_TOOL:
        return handle_create_new_tool(context)
    elif state == TrainingState.IDENTIFY_FAULTY_TOOL:
        return handle_identify_faulty_tool(context)
    elif state == TrainingState.DEBUG_FAULTY_TOOL:
        return handle_debug_faulty_tool(context)
    elif state == TrainingState.TEST_TOOL_WITH_COBBIE:
        return handle_test_tool_with_cobbie(context)
    elif state == TrainingState.ASSESS_TOOL_USAGE:
        return handle_assess_tool_usage(context)
    elif state == TrainingState.DECIDE_TOOL_FATE:
        return handle_decide_tool_fate(context)
    else:
        logger.error(f"Unknown state: {state}")
        context.error_message = f"Unknown state: {state}"
        return TrainingState.ERROR, context


# ============================================================================
# Main Training Loop
# ============================================================================


def main():
    """Main training loop."""
    # Parse arguments
    parser = argparse.ArgumentParser(description="Run training phase")
    parser.add_argument(
        "--start", type=int, required=True, help="Start index (required)"
    )
    parser.add_argument(
        "--end",
        type=int,
        default=None,
        help="End index (optional, defaults to end of trainset)",
    )
    parser.add_argument(
        "--continue",
        dest="continue_run",
        type=str,
        required=False,
        help="Continue specific run ID (requires --start and --end)",
    )
    parser.add_argument(
        "--max-tools",
        type=int,
        default=16,
        help="Maximum number of tools to maintain (default: 16)",
    )
    parser.add_argument(
        "--grace-period",
        type=int,
        default=8,
        help="Questions to protect new tools from deletion (default: 8)",
    )
    args = parser.parse_args()

    # Set default end if not provided
    end_index = args.end if args.end else len(TRAINSET)
    dataset = TRAINSET[args.start : end_index]

    logger.info(f"Starting training phase with {len(dataset)} QA pairs")
    logger.info(f"Dataset range: {args.start} to {end_index - 1}")

    # Setup MLflow
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("Training")

    # Determine run ID and name
    if args.continue_run:
        # Continuing existing run with explicit run_id
        run_id = determine_run_id(args.continue_run)
        run_name = None  # Don't set a new name when continuing
        logger.info(f"Continuing existing MLflow run: {run_id}")
        logger.info(f"Processing questions {args.start} to {end_index - 1}")
    else:
        # Creating new run
        run_id = None
        run_name = f"TRAINING_{datetime.now().strftime('%Y-%m-%d-%H-%M-%S')}"
        logger.info(f"Creating new MLflow run: {run_name}")

    # Main MLflow run
    with mlflow.start_run(run_id=run_id, run_name=run_name):
        # Initialize tool metadata for existing tools
        initialized_count = initialize_tool_metadata(args.start)
        if initialized_count > 0:
            logger.info(f"Initialized metadata for {initialized_count} existing tools")

        initial_tools = get_created_tools()

        # Log immutable configuration parameters (only for new runs)
        if run_id is None:
            mlflow.log_params(
                {
                    "model_name": LLM_NAME,
                    "provider_name": "zai",
                    "component": "Training",
                    "max_tools": args.max_tools,
                    "grace_period": args.grace_period,
                }
            )

        # Log/update batch information as metrics (works for both new and continued runs)
        # Get previous total if continuing
        previous_total = 0
        if run_id is not None:
            active_run = mlflow.active_run()
            if active_run is not None:
                previous_total = int(
                    active_run.data.metrics.get("total_samples_processed", 0)
                )

        mlflow.log_metrics(
            {
                "batch_start_index": args.start,
                "batch_end_index": end_index - 1,  # Inclusive end
                "batch_size": len(dataset),
                "total_samples_processed": previous_total + len(dataset),
                "current_tools_count": len(initial_tools),
            }
        )

        # Track results for aggregate metrics
        qa_results = []

        # Process each QA pair
        for idx, qa_pair in enumerate(dataset):
            logger.info(f"\n{'=' * 80}")
            logger.info(f"Processing QA {idx + 1}/{len(dataset)}: {qa_pair.id}")
            logger.info(f"Question: {qa_pair.question}")
            logger.info(f"Ground truth: {qa_pair.ground_truth}")
            logger.info(f"{'=' * 80}")

            # Create nested run for this QA pair
            qa_run_name = f"question_{idx + args.start}_{qa_pair.id}"

            with mlflow.start_run(run_name=qa_run_name, nested=True):
                # Log QA-level parameters
                mlflow.log_params(
                    {
                        "question_id": qa_pair.id,
                        "question": qa_pair.question,
                        "ground_truth": qa_pair.ground_truth,
                        "category": qa_pair.category,
                        "ifc_model_path": qa_pair.ifc.model_path
                        if qa_pair.ifc
                        else None,
                    }
                )

                # Initialize context and state
                global_question_num = args.start + idx
                context = Context(
                    qa_pair=qa_pair,
                    global_question_num=global_question_num,
                    max_tools=args.max_tools,
                    grace_period=args.grace_period,
                )
                state = TrainingState.START

                # State machine loop with single main span
                try:
                    with mlflow.start_span(name="TrainingQA", span_type="CHAIN"):
                        while state not in [TrainingState.END, TrainingState.ERROR]:
                            state, context = process_state(state, context)

                    # Log QA-level metrics
                    qa_result = log_qa_metrics(context)
                    qa_results.append(qa_result)

                    if state == TrainingState.ERROR:
                        logger.error(
                            f"QA {qa_pair.id} ended with error: {context.error_message}"
                        )
                        mlflow.set_tag("status", "ERROR")
                    else:
                        logger.info(f"QA {qa_pair.id} completed successfully")
                        mlflow.set_tag("status", "success")

                except Exception as e:
                    logger.error(
                        f"Unexpected error processing QA {qa_pair.id}: {e}",
                        exc_info=True,
                    )
                    qa_results.append(
                        {
                            "question_id": qa_pair.id,
                            "classification": "unknown",
                            "tool_created": False,
                            "tool_updated": False,
                            "error": True,
                            "total_tokens": 0,
                            "total_duration": 0,
                        }
                    )
                    mlflow.set_tag("status", "exception")
                    # Continue to next QA pair

        # Calculate and log aggregate metrics
        aggregate_metrics = calculate_aggregate_metrics(qa_results)
        if aggregate_metrics:
            mlflow.log_metrics(aggregate_metrics)

        logger.info(f"\n{'=' * 80}")
        logger.info("Training Phase Complete")
        logger.info(f"{'=' * 80}")
        logger.info(f"Total QA pairs: {aggregate_metrics.get('total_qa_pairs', 0)}")
        logger.info(f"Correct answers: {aggregate_metrics.get('correct_answers', 0)}")
        logger.info(f"Wrong answers: {aggregate_metrics.get('wrong_answers', 0)}")
        logger.info(f"Abstained: {aggregate_metrics.get('abstained_answers', 0)}")
        logger.info(f"Tools created: {aggregate_metrics.get('tools_created', 0)}")
        logger.info(f"Tools updated: {aggregate_metrics.get('tools_updated', 0)}")
        logger.info(f"Errors: {aggregate_metrics.get('errors', 0)}")
        logger.info(f"Success rate: {aggregate_metrics.get('success_rate', 0):.2%}")

        # Get final tool count
        final_tools = get_created_tools()
        logger.info(
            f"Final tool count: {len(final_tools)} (started with {len(initial_tools)})"
        )


if __name__ == "__main__":
    main()
