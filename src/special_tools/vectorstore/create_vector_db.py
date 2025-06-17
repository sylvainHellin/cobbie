# %%
# ==================== Set up ==================== #
import os
import json
import ast
import pandas as pd
from chromadb import PersistentClient, Collection
from dotenv import load_dotenv, find_dotenv
import sys

# Add the src directory to the Python path
sys.path.append(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
from src.config import VECTORSTORE_PATH

load_dotenv(find_dotenv())
ROOT_PATH = os.getenv("ROOT_PATH", "")


# %% Use ast to extract classes and functions from IfcOpenShell
def extract_module_definitions():
    """Extract documentation from IfcOpenShell modules and return module definitions dict."""
    # ==================== Extract documentation from IfcOpenShell ==================== #
    relevant_python_files = [
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/util/element.py",
            "ifcopenshell.util.element",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/util/shape.py",
            "ifcopenshell.util.shape",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/util/placement.py",
            "ifcopenshell.util.placement",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/util/geolocation.py",
            "ifcopenshell.util.geolocation",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/util/system.py",
            "ifcopenshell.util.system",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/geom/main.py",
            "ifcopenshell.geom",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/file.py",
            "ifcopenshell.file",
        ),
        (
            ".venv/lib/python3.12/site-packages/ifcopenshell/entity_instance.py",
            "ifcopenshell.entity_instance",
        ),
        # (".venv/lib/python3.12/site-packages/ifcopenshell/ifcopenshell_wrapper.py", "ifcopenshell.ifcopenshell_wrapper"),
        # (".venv/lib/python3.12/site-packages/ifcopenshell/stream.py", "ifcopenshell.stream"),
        # (".venv/lib/python3.12/site-packages/ifcopenshell/sql.py", "ifcopenshell.sql")
    ]

    relevant_python_files = [
        (os.path.join(ROOT_PATH, file_path), module_name)
        for (file_path, module_name) in relevant_python_files
    ]
    module_definitions = {}

    # Loop through all the relevant packages to extract the functions and classes docstrings
    for file_path, module_name in relevant_python_files:
        try:
            with open(file_path, "r") as f:
                source_code = f.read()

        except FileNotFoundError:
            print(f"File not found: {file_path}")
            continue

        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            continue

        try:
            tree = ast.parse(source_code)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            continue

        definitions = []
        other_types = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                node_type = "function" if isinstance(node, ast.FunctionDef) else "Class"
                docstring = ast.get_docstring(node)
                definitions.append(
                    {"name": node.name, "docstring": docstring, "type": node_type}
                )
            else:
                other_types[str(type(node))] = ""

        module_definitions[module_name] = definitions  # module_name might be None now

    return module_definitions


if __name__ == "__main__":
    module_definitions = extract_module_definitions()
    print(json.dumps(module_definitions, indent=2))


# %% Post-processing of the result and store them into a pandas DataFrame
# ==================== Tranform and store the data in a DataFrame ==================== #
def process_module_definitions(module_definitions: dict) -> pd.DataFrame:
    """Process module definitions into a pandas DataFrame with filtered results."""
    data = []
    for module_name, definitions in module_definitions.items():
        for definition in definitions:
            # Only add entries that have a non-None docstring
            if definition["docstring"] is not None:
                data.append(
                    {
                        "module_name": module_name,
                        "name": definition["name"],
                        "type": definition["type"],
                        "docstring": definition["docstring"],
                    }
                )

    df_module_definitions = pd.DataFrame(data)

    # filter out private methods/class
    mask = ~df_module_definitions["name"].str.startswith("_")
    df = df_module_definitions[mask].copy()

    # filter out the duplicated values
    df = df.drop_duplicates()

    # Additional validation to ensure no NaN values
    df = df.dropna(subset=["docstring", "name", "type", "module_name"])

    return df


# %%
# ==================== Create the Embeddings and add them to the DataFrame ==================== #
def create_vector_db(df):
    """Create vector database from DataFrame and return the collection."""
    client = PersistentClient(path=VECTORSTORE_PATH)
    collection = client.create_collection(name="ifcopenshell", get_or_create=True)

    # Additional validation before adding to collection
    valid_rows = df.dropna(subset=["docstring", "name", "type", "module_name"])

    for idx, row in valid_rows.iterrows():
        if (
            pd.isna(row.docstring)
            or pd.isna(row.name)
            or pd.isna(row.type)
            or pd.isna(row.module_name)
        ):
            continue

        collection.add(
            ids=[str(idx)],
            metadatas=[
                {
                    "name": row["name"],
                    "type": row.type,
                    "module": row.module_name,
                }
            ],
            documents=[row.docstring],
        )

    return collection


# %% Test retrieval
def test_retrieval(collection: Collection):
    """Test retrieval from the vector database."""
    query = "Get the properties of an Entity."
    text_search = "propert"
    results = collection.query(
        query_texts=[query], n_results=10, where_document={"$contains": text_search}
    )
    return results


if __name__ == "__main__":
    # Extract module definitions
    module_definitions = extract_module_definitions()

    # Process into DataFrame
    df = process_module_definitions(module_definitions)
    print("DataFrame head:")
    print(df.head(30))

    # Create vector database
    collection = create_vector_db(df)

    # Test retrieval
    results = test_retrieval(collection)
    print("\nTest retrieval results:")
    print(results)
