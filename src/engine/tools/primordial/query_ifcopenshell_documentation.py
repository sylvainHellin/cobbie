# %%
# ==================== Set up ==================== #
import json
import os
import sys

from chromadb import PersistentClient
from chromadb.errors import NotFoundError
from dotenv import find_dotenv, load_dotenv

_ = load_dotenv(find_dotenv())
ROOT_PATH = os.getenv("ROOT_PATH")
assert ROOT_PATH is not None

sys.path.insert(0, ROOT_PATH)
from src.config import LOG_LEVEL, VECTORSTORE_PATH  # noqa: E402
from src.engine.util import get_logger  # noqa: E402


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
) -> str:
    """Queries the documentation from the IfcOpenShell library using natural language.

    Args:
        query (str): Natural language description of the desired functionality.

    Returns:
        str: A JSON-serialized string containing a list of matching documentation entries, where each entry is a dictionary with keys: "module", "type", "name", "docstring"
    """
    logger = get_logger("query_ifc_documentation", log_level=LOG_LEVEL)
    logger.info(f"Query: {query}")
    logger.debug(f"n_results: {n_results}")

    # Add input validation for query
    if not query or not query.strip():
        error_msg = "Query string cannot be empty"
        logger.error(f"INPUT VALIDATION ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # Input validation for n_results
    if not isinstance(n_results, int) or n_results <= 0:
        error_msg = "n_results must be a positive integer"
        logger.error(f"INPUT VALIDATION ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # Get database connection with proper error handling
    try:
        logger.debug("Connecting to IfcOpenShell documentation database...")
        collection = get_db_client()
        logger.debug("✓ Database connection successful")
    except NotFoundError as e:
        error_msg = f"Database setup issue: {str(e)}"
        logger.error(f"DATABASE ERROR: {error_msg}")
        return json.dumps({"error": error_msg})
    except Exception as e:
        error_msg = f"Database connection failed: {str(e)}"
        logger.error(f"DATABASE ERROR: {error_msg}")
        return json.dumps({"error": error_msg})

    # query the similar elements from the db
    try:
        results = collection.query(
            query_texts=[query],  # Add the query text for semantic search
            n_results=n_results,
        )
        logger.debug(
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

        logger.debug(f"✓ Successfully formatted {len(response)} results for return")
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
