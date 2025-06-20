# %%
# ==================== Set up ==================== #
import json
from typing import Optional
from chromadb import PersistentClient
from chromadb.errors import NotFoundError
from src.config import VECTORSTORE_PATH, LOG_LEVEL
from src.engine.util import get_logger


# Move the client initialization into a function
def get_db_client():
    """
    Get the ChromaDB collection for IfcOpenShell documentation.

    Returns:
        Collection: The IfcOpenShell documentation collection

    Raises:
        NotFoundError: If the collection doesn't exist
        Exception: For other database connection issues
    """
    logger = get_logger("get_db_client", log_level=LOG_LEVEL)

    try:
        logger.debug(f"Connecting to database at: {VECTORSTORE_PATH}")
        client = PersistentClient(path=VECTORSTORE_PATH)

        # List available collections for debugging
        collections = client.list_collections()
        collection_names = [c.name for c in collections]
        logger.debug(f"Available collections: {collection_names}")

        # Try to get the collection
        collection = client.get_collection(name="ifcopenshell")
        logger.debug("Successfully connected to ifcopenshell collection")
        return collection

    except NotFoundError as e:
        error_msg = "IfcOpenShell documentation collection not found. You may need to run the vector database creation script first."
        logger.error(error_msg)
        raise NotFoundError(error_msg) from e

    except Exception as e:
        error_msg = (
            f"Failed to connect to vector database at {VECTORSTORE_PATH}: {str(e)}"
        )
        logger.error(error_msg)
        raise Exception(error_msg) from e


# %%
# ==================== Define tools to query the DB ==================== #
def query_ifcopenshell_documentation(
    query: str,
    n_results: int = 10,
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
    logger.info("IfcOpenShell documentation query tool called")
    logger.debug(f"Query: {query}")
    logger.debug(f"n_results: {n_results}")
    logger.debug(f"docstring_filter: {docstring_filter}")

    # Add input validation for query
    if not query or not query.strip():
        error_msg = "Query string cannot be empty"
        logger.error(f"INPUT VALIDATION ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # Add input validation for docstring_filter
    if docstring_filter is not None and not isinstance(docstring_filter, str):
        error_msg = "docstring_filter must be a string"
        logger.error(f"INPUT VALIDATION ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # Input validation for n_results
    if not isinstance(n_results, int) or n_results <= 0:
        error_msg = "n_results must be a positive integer"
        logger.error(f"INPUT VALIDATION ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # Get database connection with proper error handling
    try:
        logger.info("Connecting to IfcOpenShell documentation database...")
        collection = get_db_client()
        logger.info("✓ Database connection successful")
    except NotFoundError as e:
        error_msg = f"Database setup issue: {str(e)}"
        logger.error(f"DATABASE ERROR: {error_msg}")
        return json.dumps({"error": error_msg})
    except Exception as e:
        error_msg = f"Database connection failed: {str(e)}"
        logger.error(f"DATABASE ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # Structure the db query to include docstring filter if provided
    where_document = {"$contains": docstring_filter} if docstring_filter else None

    logger.debug(f"Database query filters - where_document: {where_document}")

    # query the similar elements from the db
    try:
        logger.info("Executing semantic search query...")
        results = collection.query(
            query_texts=[query],  # Add the query text for semantic search
            n_results=n_results,
            where_document=where_document,  # type:ignore
        )
        logger.info(
            f"✓ Database query completed successfully. Found {len(results['ids'][0]) if results['ids'] else 0} results"
        )

    except Exception as e:
        error_msg = f"Error executing database query: {str(e)}"
        logger.error(f"QUERY ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

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
            logger.debug(
                f"Result {i + 1} Document: {document[:200]}..."
                if len(document) > 200
                else f"Result {i + 1} Document: {document}"
            )

    # create and return the successful response
    try:
        response = []
        for i in range(len(results["ids"][0])):
            elt = {
                "module": (results["metadatas"] or [[]])[0][i]["module"],
                "type": (results["metadatas"] or [[]])[0][i]["type"],
                "name": (results["metadatas"] or [[]])[0][i]["name"],
                "docstring": (results["documents"] or [[]])[0][i],
            }
            response.append(elt)

        logger.info(f"✓ Successfully formatted {len(response)} results for return")
        # serialize and return the output
        return json.dumps(response, indent=2)

    except Exception as e:
        error_msg = f"Error formatting query results: {str(e)}"
        logger.error(f"FORMATTING ERROR: {error_msg}")
        return json.dumps({"error": error_msg})


# %%
# ==================== Test the tools ==================== #
if __name__ == "__main__":
    query = "Get the properties of an Entity."

    # Example usage with docstring filter
    res1 = query_ifcopenshell_documentation(
        query=query,
        docstring_filter="instance",
    )

    print("\n", "=" * 50, "\n")
    print("<Test with docstring filter>")
    print(f"Query: {query}\n")
    print(res1)

    # Example usage without any filters
    print("=" * 50)
    print("<Test without filters>")
    res2 = query_ifcopenshell_documentation(
        query="Get IFC elements by type", n_results=5
    )
    print(res2)
