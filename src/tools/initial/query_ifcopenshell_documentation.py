import os
import time

import mlflow
import requests
from dotenv import find_dotenv, load_dotenv

from src.util.python_executor import count_tokens

load_dotenv(find_dotenv())
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY")


def query_ifcopenshell_docs(query: str) -> str:
    """
    Retrieve documentation from IfcOpenShell based on a query, via the
    Context7 MCP endpoint (`/ifcopenshell/ifcopenshell`).

    Results are traced via MLflow when running within an active trace context.

    Args:
        query: Topic or query to focus the documentation on
            (e.g., "finds all entities of type `IfcWall`", "element bounding
            box", "clash detection").

    Returns:
        Documentation text as a string.

    Side Effect:
        Prints the retrieved documentation.
    """
    start = time.time()

    with mlflow.start_span(name="query_ifcopenshell_docs", span_type="TOOL") as span:
        span.set_inputs({"query": query})

        if not CONTEXT7_API_KEY:
            result = "Could not retrieve the information ; CONTEXT7_API_KEY missing."
        else:
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
                response = requests.post(
                    "https://mcp.context7.com/mcp",
                    json=payload,
                    headers=headers,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                if "error" in data:
                    result = f"API error: {data['error']}"
                elif "result" in data and "content" in data["result"]:
                    content = data["result"]["content"]
                    if isinstance(content, list):
                        result = "".join(
                            block["text"]
                            for block in content
                            if isinstance(block, dict) and "text" in block
                        )
                    elif isinstance(content, dict) and "text" in content:
                        result = content["text"]
                    else:
                        result = str(data.get("result", data))
                else:
                    result = str(data.get("result", data))
            except requests.exceptions.RequestException as e:
                result = f"Failed to query Context7 API: {str(e)}"

        duration = time.time() - start
        span.set_outputs({"result": result})
        span.set_attributes(
            {
                "duration_ms": duration * 1000,
                "result_tokens": count_tokens(result),
            }
        )

        print(result)
        return result


if __name__ == "__main__":
    query_ifcopenshell_docs("get bounding box element")
