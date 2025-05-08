# %%
# ==================== Set up ==================== #
import json
from typing import Dict, Optional
from chromadb import PersistentClient, EmbeddingFunction, Embeddings, Documents
from ollama import embed
import numpy as np
from smolagents import tool
from pydantic import BaseModel, ValidationError
from config import VECTORSTORE_PATH

# Define Embedding Model to use
EMBEDDING_MODEL = "nomic-embed-text"


# Define a custom embedding function
class OllamaEmbeddingFunction(EmbeddingFunction):
    def __call__(self, documents: Documents) -> Embeddings:
        embd = embed(model=EMBEDDING_MODEL, input=documents)
        embeddings = [np.array(embd["embeddings"][0], dtype=np.float32)]
        return embeddings


# Move the client initialization into a function
def get_db_client():
    # client = PersistentClient(path=os.path.join(SRC_PATH, "db"))
    client = PersistentClient(path=VECTORSTORE_PATH)
    return client.get_collection(name="ifcopenshell")


# Define a custom embedding function
# !This should be the same as in the create_vector_db.py file
ollama_embed = OllamaEmbeddingFunction()


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
    verbose: bool = False,
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
        verbose (bool, optional): If True, prints detailed information about the query and results. Defaults to False.

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
        return {
            "error": "ValueError: n_results must be a positive integer."
        }  # Return error dict

    # Input validation for metadata_filter using Pydantic
    validated_metadata_filter = None
    if metadata_filter is not None:
        try:
            validated_metadata_filter = MetadataFilter(**metadata_filter)
        except ValidationError as e:
            return {
                "error": f"ValueError: Invalid metadata_filter: {e}"
            }  # Return error dict

    # create the embedding of the user's query

    try:
        embeddings = ollama_embed([query])
    except Exception as e:
        error_msg = f"Error generating embeddings: {e}"
        print(error_msg)  # Optionally keep printing for logs
        return {"error": error_msg}  # Return error dict

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
            query_embeddings=embeddings,
            n_results=n_results,
            where=where_metadata,
            where_document=where_document,
        )

    except Exception as e:
        error_msg = f"Error querying the database: {e}"
        print(error_msg)  # Optionally keep printing for logs
        return {"error": error_msg}  # Return error dict

    # print some details if verbose
    if verbose:
        print("=" * 50)
        print(f"\nRetrieval for the query: \n{query}\n")
        # restructured print output for better readability
        for i in range(len(results["ids"][0])):
            metadata = results["metadatas"][0][i]
            document = results["documents"][0][i]

            print("Metadata:")
            print(json.dumps(metadata, indent=2))
            print("\nDocument:")
            print(document)  # This will properly render the newlines
            print("\n" + "=" * 50)

    # create and return the successful response
    response = []
    for i in range(len(results["ids"][0])):
        elt = {
            "module": results["metadatas"][0][i]["module"],
            "type": results["metadatas"][0][i]["type"],
            "name": results["metadatas"][0][i]["name"],
            "docstring": results["documents"][0][i],
        }
        response.append(elt)

    # serialize and returnt the output
    return json.dumps(response, indent=2)


# %%
# ==================== Test the tools ==================== #
if __name__ == "__main__":
    query = "Get the properties of an Entity."

    # Example usage with valid metadata_filter
    res1 = query_ifcopenshell_documentation(
        query=query,
        verbose=False,
        docstring_filter="instance",
        metadata_filter={"field": "type", "operator": "$eq", "value": "function"},
    )

    print("=" * 50)
    print("Test with valid example:")
    # print(json.dumps(res1, indent=2))
    print(res1)

    # Example usage with INVALID metadata_filter (missing 'operator')
    print("=" * 50)
    print("Test with invalid example:")
    res2 = query_ifcopenshell_documentation(
        query="test query",
        metadata_filter={"field": "type", "value": "function"},  # Missing 'operator'
    )
    print(json.dumps(res2, indent=2))


# %%
