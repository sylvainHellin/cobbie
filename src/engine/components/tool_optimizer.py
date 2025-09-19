import dspy
from typing import Literal, List, Optional

from src.config.agents import AGENT_CONFIGS, ToolOptimizerConfig
from src.engine.schemas import ModuleOutput, AgentOutput
from src.engine.util import get_logger, get_tools_description


class SignatureToolOptimizer(dspy.Signature):
    """
    Your role is to analyze chat histories between users and a BIM/IFC specialist AI assistant to identify opportunities for tool improvement.

    **Your Task:**
    Identify ways in which the tools used by a helpful AI assistant to answer users' questions can be improved. This AI assistant specialises in answering questions related to a BIM model using code. To perform this task, the assistant has access to various tools, including specialised Python functions that retrieve information from the BIM model.

    With this in mind, review the provided chat history and consider whether the current toolset could be optimised in any of the following ways:

    1. **Create a New Tool**
       - The assistant frequently writes repetitive or complex code for similar tasks
       - Common information retrieval patterns emerge that lack dedicated tools
       - Users repeatedly ask for functionality that requires multiple existing tools

    2. **Merge Existing Tools**
       - Two or more tools have significant functional overlap
       - The assistant shows confusion when choosing between similar tools
       - Multiple tools could be consolidated into a more comprehensive solution

    3. **Update an Existing Tool**
       - A tool was used but failed to meet the user's needs completely
       - The assistant had to supplement a tool with additional code
       - Tool limitations forced workarounds or suboptimal solutions

    4. **No Action Needed**
       - Current tools handled the requests effectively
       - No clear patterns of inefficiency or gaps identified

    **Tool Recommendation Guidelines**
       **Primary Goal**: Identify tools that reduce repetitive code patterns and minimize IFC OpenShell documentation queries

       **IFC/BIM-Specific Priorities:**
       - Target common IFC filtering patterns (interior/exterior, by material, by space, by property values)
       - Focus on repetitive property extraction workflows (Pset_* properties, geometric properties)
       - Prioritize tools that abstract frequent IFC relationship traversals

       **Tool Generality Guidelines:**
       - Favor tools serving broad use cases: `get_interior_elements`, `calculate_material_volumes`, `get_elements_by_property_value`
       - Avoid overly specific tools: `find_reinforced_medical_equipment_areas`, `get_blue_doors_in_kitchen`

       **When to Recommend Tools:**
       - Similar 5+ line code blocks appear across conversations
       - Documentation queries cluster around the same IFC concepts
       - Multiple existing tools needed for single user requests

       **Implementation Guidelines:**
       - **Recommend tools that involve**: Property extraction, element filtering, counting operations, basic calculations using existing IFC properties
       - **Consider carefully tools that involve**: Relationship traversal, simple geometric calculations from IFC geometry data
       - **Avoid recommending tools that involve**: Complex 3D spatial analysis, topology-dependent calculations, operations requiring external 3D engines
       - **When in doubt**: Favor simpler tools that work reliably with IfcOpenShell's direct property access over complex geometric computations
    """

    # Input fields
    chat_history: str = dspy.InputField(
        desc="Chat history between the user and the AI assistant."
    )
    available_tools: str = dspy.InputField(desc="The list of tools already available.")

    # Output fields
    reasoning: str = dspy.OutputField(
        desc="Step-by-step analysis of how the tools could be improved."
    )

    improvement: Literal[
        "create_new_tool",
        "merge_existing_tools",
        "update_existing_tool",
        "no_action_needed",
    ] = dspy.OutputField(
        desc="The type of improvement action recommended based on the analysis of the chat history and available tools."
    )

    new_tool_name: str = dspy.OutputField(
        desc="The name for the new tool to be created (for 'create_new_tool') or the name for the merged tool (for 'merge_existing_tools'). Should be descriptive and follow snake_case naming convention. Leave empty for 'no_action_needed' and 'update_existing_tool'."
    )

    existing_tool_names: List[str] = dspy.OutputField(
        desc="List of existing tool names that should be merged together (for 'merge_existing_tools') or the single tool name that needs updating (for 'update_existing_tool'). Leave empty for 'create_new_tool' and 'no_action_needed'."
    )

    requirements: str = dspy.OutputField(
        desc="Detailed requirements specification for the tool improvement. For new tools: describe functionality, input parameters, and expected output. For merging: explain how tools should be combined. For updates: specify what changes are needed. Leave empty for 'no_action_needed'."
    )


class ToolOptimizer(dspy.Module):
    """
    A DSPy module that analyzes chat histories to identify opportunities for tool improvement.
    """

    def __init__(
        self,
        config: Optional[ToolOptimizerConfig] = None,
        lm: Optional[dspy.LM] = None,
    ):
        super().__init__()
        # Use provided config or default config
        self.config = config or AGENT_CONFIGS.tool_optimizer
        self.lm = lm or self.config.llm.get_llm()

        self.tool_optimizer = dspy.ChainOfThought(SignatureToolOptimizer)
        self.log_level = self.config.log_level
        self.logger = get_logger(name="ToolOptimizer", log_level=self.log_level)

    def forward(
        self,
        chat_history: str,
        available_tools: Optional[str] = None,
    ) -> ModuleOutput:
        """
        Analyze a chat history to identify opportunities for tool improvement.

        Args:
            chat_history: A string containing the conversation between the user and the AI assistant.
            available_tools (Optional): A serialised list of existing tools and their descriptions. If this is set to None, a description will be created for all existing tools.

        Returns:
            ModuleOutput containing:
            - result.reasoning: Step-by-step analysis
            - result.improvement: Type of improvement action recommended
            - result.new_tool_name: Name for new/merged tool (if applicable)
            - result.existing_tool_names: List of existing tool names to merge/update (if applicable)
            - result.requirements: Detailed requirements specification
            - status: "success" or "error"
            - error_msg: Error description (if status is "error")
        """

        with dspy.context(lm=self.lm):
            self.logger.info("Starting tool optimization analysis")
            self.output = ModuleOutput()

            try:
                self.logger.debug(
                    f"Analyzing chat history of length: {len(chat_history)}"
                )
                available_tools = (
                    available_tools if available_tools else get_tools_description()
                )

                prediction = self.tool_optimizer(
                    chat_history=chat_history,
                    available_tools=available_tools,
                )

                self.logger.info(
                    f"Tool optimization completed. Improvement type: {getattr(prediction, 'improvement', None)}"
                )

                self.output.result = AgentOutput(
                    reasoning=getattr(prediction, "reasoning", None),
                    improvement=getattr(prediction, "improvement", None),
                    function_name=getattr(prediction, "new_tool_name", None),
                    existing_tool_names=getattr(
                        prediction, "existing_tool_names", None
                    ),
                    function_requirements=getattr(prediction, "requirements", None),
                )
                self.output.status = "success"

                self.logger.info("Tool optimization analysis completed successfully")

            except Exception as e:
                error_msg = f"Error during tool optimization analysis: {str(e)}"
                self.logger.error(error_msg)
                self.output.error_msg = error_msg

            finally:
                self.output.update(
                    lm=self.lm,
                    cost_input_tokens=self.config.llm.cost_input_token,
                    cost_output_tokens=self.config.llm.cost_output_token,
                )

        return self.output


if __name__ == "__main__":
    from typing import cast
    import mlflow

    def main(
        chat_history: str,
    ):
        # setup mlflow
        mlflow.dspy.autolog()  # type: ignore
        mlflow.set_tracking_uri("http://127.0.0.1:5000")
        mlflow.set_experiment("ToolOptimizer")

        # setup the tool optimizer
        tool_optimizer = ToolOptimizer()

        # analyze the chat history
        result = cast(ModuleOutput, tool_optimizer(chat_history=chat_history))

        print(f"Tool optimization result: {result.model_dump_json(indent=2)}")

    ##########################################
    # Test data - example chat history
    chat_history = """
        User: How many interior doors are there in this building?
        Assistant: I'll help you count the interior doors in the building. Let me retrieve all doors and filter for interior ones.

        [The assistant uses get_elements_by_type to get doors, then manually filters using IsExternal property]

        Assistant: Based on my analysis, there are 10 interior doors in the building. I found this by:
        1. Retrieving all 14 doors using get_elements_by_type
        2. Checking each door's Pset_DoorCommon properties
        3. Filtering for doors where IsExternal is False
        4. Counting the remaining doors

        User: That was quite a lot of steps just to count interior doors. Do you have to do this manually every time?
        Assistant: You're right, this is a repetitive process. Currently I have to manually filter doors by checking their IsExternal property each time someone asks about interior doors specifically. This could be simplified with a dedicated function.
    """

    main(
        chat_history=chat_history,
    )
