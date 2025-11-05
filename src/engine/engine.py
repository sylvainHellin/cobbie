from typing import Callable, Dict, List, Optional, cast

import dspy
import mlflow

from src.engine.schemas import ModuleOutput
from src.engine.util import (
    get_logger,
    get_created_tools,
    create_code_prefix,
)
from src.engine.components import CodeAct
from src.engine.components.bim_qas import BIM_QAS
from src.engine.tools.primordial import (
    query_ifcopenshell_docs,
    web_search,
)

from src.config.agents import AGENT_CONFIGS, FUNCTION_BOILERPLATE, IfcAnswerEngineConfig


class IfcAnwerEngineSignature(dspy.Signature):
    """
    Answer any questions users have about a given BIM model.

    Keep in mind that the person asking the questions may not be a BIM expert. They may not have the .ifc model open in other software, so they may ask you questions using names for entities (e.g., room, material) that don't exactly match those used in the BIM model. You will need to determine the exact name/ID of any corresponding components yourself.

    When the information is not available in the BIM model:
    - Start with "This information is not available in the BIM model."
    - The missing information should be indicated when possible. For example, "The number of windows on the north façade cannot be determined because the BIM model is not georeferenced."

    When the answer is not definitive or calculations involve approximations:
    - Start with "The information is not directly available in the BIM model and cannot be calculated exactly."
    - If an estimation is possible, provide it, formulated like, "However, we can estimate..."
    """

    # Inputs
    question: str = dspy.InputField()
    path_ifc_model: str = dspy.InputField(
        desc="The path to the .ifc file of the BIM model."
    )

    # Outputs
    answer: str = dspy.OutputField(
        desc="The complete answer to the user's question. This field MUST ALWAYS be provided, even if you are still fetching some informations using the Python interpreter. Just return \"\" if you don't have an answer yet."
    )


class IfcAnswerEngine(dspy.Module):
    """
    This is an engine that can answer questions in natural language related to a BIM model in .ifc format.
    The engine has an 'inference' and a 'training' mode.
        In training mode, the engine has access to the ground truth and can dynamically generate new functions to try to answer the question.
        In inference mode, the engine does not have access to the ground truth and attempts to answer the question using the available tools.
    """

    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = {
            "web_search": web_search,
            "query_ifcopenshell_docs": query_ifcopenshell_docs,
        },
        additional_authorized_imports: Optional[List[str]] = None,
        config: Optional[IfcAnswerEngineConfig] = None,
        llm: Optional[dspy.LM] = None,  # Optional override
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.ifc_answer_engine
        self.lm = llm or self.config.llm.get_llm()

        self.max_iters = self.config.max_iters
        self.max_retry: int = self.config.max_retry
        self.log_level = self.config.log_level
        # Use provided LLM or get from config
        self.logger = get_logger(name="IfcAnswerEngine", log_level=self.log_level)
        self.additional_authorized_functions = additional_authorized_functions or {}
        self.additional_authorized_imports = additional_authorized_imports or []
        self.max_tokens_logs = self.config.max_tokens_logs
        self.max_tokens_output = self.config.max_tokens_output
        self.created_tools: Dict[str, Callable] = {}
        self.add_code_prefix = self.config.add_code_prefix

        if self.config.import_all_created_tools:
            self.created_tools = get_created_tools()
            self.additional_authorized_functions = (
                self.additional_authorized_functions | self.created_tools
            )

        self.engine = CodeAct(
            signature=IfcAnwerEngineSignature,
            tools=[fn for _, fn in self.additional_authorized_functions.items()].sort(
                key=lambda func: func.__name__
            ),
            max_iters=self.max_iters,
        )
        self.logger.info("IfcAnswerEngine initialized.")

    def forward(self, question: str, path_ifc_model: str = "") -> ModuleOutput:
        self.logger.info("Starting forward pass.")

        self.output = ModuleOutput()
        if self.add_code_prefix:
            code_prefix = create_code_prefix(
                path_ifc_model=path_ifc_model, imports_boilerplate=FUNCTION_BOILERPLATE
            )
        else:
            code_prefix = None

        self.engine._update_code_prefix(code_prefix=code_prefix)

        self.lm = self.config.llm.get_llm()
        with dspy.context(lm=self.lm, adapter=self.config.llm.adapter):
            # Start the loop: try to answer the question with existing tool
            try:
                prediction = self.engine(
                    question=question,
                    path_ifc_model=path_ifc_model,
                )
                self.output.result.answer = getattr(prediction, "answer", None)
                if self.output.result.answer is not None:
                    self.output.status = "success"
                else:
                    self.output.error_msg = "The agent could not return an answer."

            except Exception as e:
                self.output.error_msg = (
                    f"Error during the forward pass of the IfcAnswerEngine.\nError: {e}"
                )
                self.logger.error(self.output.error_msg)

            finally:
                self.output.update(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )

        return self.output


class BIMQASEngine(BIM_QAS):
    """
    BAML-based BIM Question Answering Engine that matches the IfcAnswerEngine interface.

    This class provides a drop-in replacement for IfcAnswerEngine using BAML
    instead of DSPy for the underlying language model interactions.
    """

    def __init__(
        self,
        additional_authorized_functions: Optional[Dict[str, Callable]] = {
            "web_search": web_search,
            "query_ifcopenshell_docs": query_ifcopenshell_docs,
        },
        additional_authorized_imports: Optional[List[str]] = None,
        config: Optional[IfcAnswerEngineConfig] = None,
        llm: Optional[dspy.LM] = None,  # For compatibility, not used in BAML
    ):
        # Map the IfcAnswerEngine parameters to BIM_QAS parameters
        max_iterations = config.max_iters if config else 10
        add_code_prefix = config.add_code_prefix if config else False
        max_tokens_logs = config.max_tokens_logs if config else 2**12
        log_level = config.log_level if config else "INFO"

        super().__init__(
            additional_authorized_functions=additional_authorized_functions,
            additional_authorized_imports=additional_authorized_imports,
            config=config,
            llm=llm,
            max_iterations=max_iterations,
            add_code_prefix=add_code_prefix,
            max_tokens_logs=max_tokens_logs,
            log_level=log_level
        )

        self.logger.info("BIMQASEngine (BAML) initialized.")


def create_engine(
    config: Optional[IfcAnswerEngineConfig] = None,
    llm: Optional[dspy.LM] = None,
    engine_type: Optional[str] = None
) -> IfcAnswerEngine | BIMQASEngine:
    """
    Factory function to create the appropriate engine based on configuration.

    Args:
        config: Engine configuration (optional)
        llm: Language model (optional, only used for DSPy engine)
        engine_type: Override engine type ("dspy" or "baml", optional)

    Returns:
        IfcAnswerEngine or BIMQASEngine instance
    """
    # Use provided config or default
    if config is None:
        config = AGENT_CONFIGS.ifc_answer_engine

    # Determine engine type
    if engine_type is None:
        engine_type = config.engine_type

    # Create appropriate engine
    if engine_type == "baml":
        logger = get_logger(name="EngineFactory", log_level=config.log_level)
        logger.info("Creating BAML-based BIMQASEngine")
        return BIMQASEngine(
            additional_authorized_functions={
                "web_search": web_search,
                "query_ifcopenshell_docs": query_ifcopenshell_docs,
            },
            config=config,
            llm=llm  # For compatibility, not used in BAML
        )
    elif engine_type == "dspy":
        logger = get_logger(name="EngineFactory", log_level=config.log_level)
        logger.info("Creating DSPy-based IfcAnswerEngine")
        return IfcAnswerEngine(
            config=config,
            llm=llm
        )
    else:
        raise ValueError(f"Unknown engine type: {engine_type}. Use 'dspy' or 'baml'")


if __name__ == "__main__":
    # Test the IfcAnswerEngine
    ifc_model_path = "/Users/sylvainhellin/GitHub/4_phd/cobbie/src/experiment/bim_models/duplex/arc.ifc"
    question = "What is the height of the bedroomns on the first floor?"

    mlflow.dspy.autolog()  # type: ignore
    mlflow.set_tracking_uri("http://127.0.0.1:5000")
    mlflow.set_experiment("IfcAnswerEngine")

    dspy.configure_cache(enable_disk_cache=False)

    # Initialize the engine - LLM comes from config now!
    engine = IfcAnswerEngine()

    # Run the test
    output = cast(
        ModuleOutput, engine(question=question, path_ifc_model=ifc_model_path)
    )
    print(output.model_dump_json(indent=2))
