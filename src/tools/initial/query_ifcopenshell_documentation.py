import os
import time
from typing import Literal

import mlflow
import requests
from dotenv import find_dotenv, load_dotenv

from src.util.python_executor import count_tokens

load_dotenv(find_dotenv())
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY")

def _query_context7(query: str) -> str:
    """Query IfcOpenShell docs using Context7 API."""
    if not CONTEXT7_API_KEY:
        return "Could not retrieve the information ; API_KEY missing."

    url = "https://mcp.context7.com/mcp"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "query-docs",
            "arguments": {
                "libraryId": "/ifcopenshell/ifcopenshell",
                "query": query,
            },
        },
    }

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "CONTEXT7_API_KEY": CONTEXT7_API_KEY,
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()

        data = response.json()

        if "error" in data:
            return f"API error: {data['error']}"

        if "result" in data and "content" in data["result"]:
            content = data["result"]["content"]
            if isinstance(content, list):
                doc_text = ""
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        doc_text += block["text"]
                return doc_text
            elif isinstance(content, dict) and "text" in content:
                return content["text"]

        return str(data.get("result", data))

    except requests.exceptions.RequestException as e:
        return f"Failed to query Context7 API: {str(e)}"


def _query_custom(query: str) -> str:
    """Query IfcOpenShell docs using local vector store."""
    from src.docs_indexer.retriever import query_docs

    return query_docs(query, top_k=5)


def query_ifcopenshell_docs(query: str) -> None:
    """
    Retrieve and display documentation from IfcOpenShell based on a query.

    Uses either Context7 API or local vector store depending on DOC_BACKEND.
    Results are printed to stdout.

    Args:
        query: The topic or query to focus the documentation on (e.g., "finds all entities of type `IfcWall`", "element bounding box", "clash detection", etc.)

    Example:
        >>> query_ifcopenshell_docs("How to access element properties")
    """
    start = time.time()

    # Read DOC_BACKEND at runtime to allow configuration via environment variable
    doc_backend: Literal["context7", "custom"] = os.getenv("DOC_BACKEND", "custom")  # type: ignore

    with mlflow.start_span(name="query_ifcopenshell_docs", span_type="TOOL") as span:
        span.set_inputs({"query": query, "backend": doc_backend})

        if doc_backend == "context7":
            result = _query_context7(query)
        else:
            result = _query_custom(query)

        duration = time.time() - start
        result_tokens = count_tokens(result)

        span.set_outputs({"result": result})
        span.set_attributes({
            "backend": doc_backend,
            "duration_ms": duration * 1000,
            "result_tokens": result_tokens,
        })

        print(result)


if __name__ == "__main__":
    doc_backend = os.getenv("DOC_BACKEND", "custom")
    print(f"Using backend: {doc_backend}")
    docs = query_ifcopenshell_docs("get bounding box element")
    print(docs)
