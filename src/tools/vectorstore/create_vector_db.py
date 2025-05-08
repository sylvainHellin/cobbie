# %%
# ==================== Set up ==================== #
import os
import json
import ast
import pandas as pd
from chromadb import PersistentClient
from dotenv import load_dotenv, find_dotenv
from tools.query_ifcopenshell_documentation import OllamaEmbeddingFunction

load_dotenv(find_dotenv())
ROOT_PATH = os.getenv("ROOT_PATH")

ollama_embed = OllamaEmbeddingFunction()
# %% Use ast to extract classes and functions from IfcOpenShell
if __name__ == "__main__":
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

    print(json.dumps(module_definitions, indent=2))
# %% Post-processing of the result and store them into a pandas DataFrame
# ==================== Tranform and store the data in a DataFrame ==================== #
if __name__ == "__main__":
    data = []
    for module_name, definitions in module_definitions.items():
        for definition in definitions:
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
    df = df_module_definitions[
        df_module_definitions["name"].apply(lambda name: name[0] != "_")
    ]

    # filter out the duplicated values
    df = df.drop_duplicates()

    # filter out entities with no description
    df = df[df["docstring"].apply(lambda x: x is not None)]

    df.head(30)
# %%
# ==================== Create the Embeddings and add them to the DataFrame ==================== #
if __name__ == "__main__":
    ollama_embed = OllamaEmbeddingFunction()
    ifdocuments = df.docstring.to_list()
    client = PersistentClient(path=os.path.join(ROOT_PATH, "src/db"))
    collection = client.create_collection(name="ifcopenshell", get_or_create=True)

    for idx, row in df.iterrows():
        embeddings = ollama_embed([row.docstring])
        collection.add(
            ids=[str(idx)],
            embeddings=embeddings,
            metadatas=[
                {
                    "name": row["name"],
                    "type": row.type,
                    "module": row.module_name,
                }
            ],
            documents=[row.docstring],
        )


# %% Test retrieval
if __name__ == "__main__":
    query = "Get the properties of an Entity."
    text_search = "propert"
    embd = ollama_embed([query])
    results = collection.query(
        query_embeddings=embd, n_results=10, where_document={"$contains": text_search}
    )
    print(results)
