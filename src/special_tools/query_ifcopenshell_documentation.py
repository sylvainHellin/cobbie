# %%
# ==================== Set up ==================== #
import json
from typing import Dict, Optional
from chromadb import PersistentClient
from smolagents import tool
from pydantic import BaseModel, ValidationError
from src.config import VECTORSTORE_PATH, LOG_LEVEL
from src.util import get_logger


# Move the client initialization into a function
def get_db_client():
    # client = PersistentClient(path=os.path.join(SRC_PATH, "db"))
    client = PersistentClient(path=VECTORSTORE_PATH)
    return client.get_collection(name="ifcopenshell")


# Define Pydantic Models for Input Validation
class MetadataFilter(BaseModel):
    field: str
    operator: str
    value: str


# %%
# ==================== Define tools to query the DB ==================== #
@tool
def query_ifcopenshell_documentation(
    query: str,
    n_results: int = 10,
    metadata_filter: Optional[Dict] = None,
    docstring_filter: Optional[str] = None,
) -> str:
    """Queries the documentation vector database to find semantically similar documentation entries.

    This function performs semantic similarity search to find relevant IfcOpenShell documentation
    based on a natural language description. For best results, the query should:
    - Describe the desired functionality in simple, clear terms
    - Focus on the core operation (e.g., "get entity attributes" rather than "how do I get attributes?")
    - Use terminology similar to the documentation (e.g., "entity", "property", "attribute")
    - Avoid implementation details or specific use cases

    Example queries:
    - "Get properties of an IFC entity"
    - "Create new IFC entity"
    - "Convert geometry to shape"

    Args:
        query (str): Natural language description of the desired functionality.
        n_results (int, optional): The maximum number of results to return. Defaults to 10.
        metadata_filter (Optional[Dict], optional): A dictionary to filter results based on metadata. Defaults to None.
            The dictionary should conform to the structure defined by the `MetadataFilter` Pydantic model:
            `{"field": field_name, "operator": operator, "value": filter_value}`
            Possible fields are: "name", "type", "module".
            Possible operators are:
                - "$eq": equal to (string, int, float)
                - "$ne": not equal to (string, int, float)
                - "$gt": greater than (int, float)
                - "$gte": greater than or equal to (int, float)
                - "$lt": less than (int, float)
                - "$lte": less than or equal to (int, float)
        docstring_filter (str, optional): A string to filter results based on whether the docstring contains this expression. Defaults to None.

    Returns:
        str: A JSON-serialized string containing either:
             - A list of matching documentation entries, where each entry is a dictionary with
               keys: "module", "type", "name", "docstring"
             - An error message in the format: {"error": "error description"}

    Example Response:
        [
            {
                "module": "ifcopenshell.util.element",
                "type": "function",
                "name": "get_properties",
                "docstring": "Gets all properties of an IFC entity..."
            }
        ]
    """
    logger = get_logger("query_ifc_documentation", log_level=LOG_LEVEL)
    logger.info("Tool called.")
    logger.debug(f"Query: {query}")
    logger.debug(f"n_results: {n_results}")
    logger.debug(f"metadata_filter: {metadata_filter}")
    logger.debug(f"docstring_filter: {docstring_filter}")

    # Add input validation for query
    if not query or not query.strip():
        return json.dumps({"error": "Query string cannot be empty"})

    # Add input validation for docstring_filter
    if docstring_filter is not None and not isinstance(docstring_filter, str):
        return json.dumps({"error": "docstring_filter must be a string"})

    # Get a fresh client connection for each query
    collection = get_db_client()

    # Input validation for n_results
    if not isinstance(n_results, int) or n_results <= 0:
        return "ValueError: n_results must be a positive integer."

    # Input validation for metadata_filter using Pydantic
    validated_metadata_filter = None
    if metadata_filter is not None:
        try:
            validated_metadata_filter = MetadataFilter(**metadata_filter)
        except ValidationError as e:
            return f"ValueError: Invalid metadata_filter: {e}"

    # structure the db query to include filters if passed as arguments
    where_document = {"$contains": docstring_filter} if docstring_filter else None

    where_metadata = (
        {
            validated_metadata_filter.field: {
                validated_metadata_filter.operator: validated_metadata_filter.value
            }
        }
        if validated_metadata_filter is not None
        else None
    )

    # query the similar elements from the db
    try:
        results = collection.query(
            query_texts=[query],  # Add the query text for semantic search
            n_results=n_results,
            where=where_metadata,  # type:ignore
            where_document=where_document,  # type:ignore
        )
        logger.info("Database query completed successfully.")

    except Exception as e:
        error_msg = f"Error querying the database: {e}"
        logger.error(error_msg)
        return f"error: {error_msg}"

    # Log the results at debug level
    for i in range(len(results["ids"][0])):
        metadata = None
        document = None
        if results["metadatas"] is not None and results["metadatas"][0] is not None:
            metadata = results["metadatas"][0][i]
        if results["documents"] is not None and results["documents"][0] is not None:
            document = results["documents"][0][i]

        if metadata is not None:
            logger.debug(f"Result {i + 1} Metadata: {json.dumps(metadata, indent=2)}")
        if document is not None:
            logger.debug(f"Result {i + 1} Document: {document}")

    # create and return the successful response
    response = []
    for i in range(len(results["ids"][0])):
        elt = {
            "module": (results["metadatas"] or [[]])[0][i]["module"],
            "type": (results["metadatas"] or [[]])[0][i]["type"],
            "name": (results["metadatas"] or [[]])[0][i]["name"],
            "docstring": (results["documents"] or [[]])[0][i],
        }
        response.append(elt)

    # serialize and return the output
    return json.dumps(response, indent=2)


# %%
# ==================== Test the tools ==================== #
if __name__ == "__main__":
    query = "Get the properties of an Entity."

    # Example usage with valid metadata_filter
    res1 = query_ifcopenshell_documentation(
        query=query,
        docstring_filter="instance",
        metadata_filter={"field": "type", "operator": "$eq", "value": "function"},
    )

    print("\n", "=" * 50, "\n")
    print("<Test with valid example>")
    print(f"Query: {query}\n")
    print(res1)

    # Example usage with INVALID metadata_filter (missing 'operator')
    print("=" * 50)
    print("<Test with invalid example (missing operator in metadata filter)>")
    res2 = query_ifcopenshell_documentation(
        query="test with invalid metadata filters",
        metadata_filter={"field": "type", "value": "function"},  # Missing 'operator'
    )
    print(json.dumps(res2, indent=2))
