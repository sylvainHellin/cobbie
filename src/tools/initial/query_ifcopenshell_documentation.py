import os
import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY")


def query_ifcopenshell_docs(query: str) -> str:
    """
    Retrieves and print up-to-date information and code examples related to the provided query from the IFCopenshell documentation.

    Args:
        query: The topic or query to focus the documentation on (e.g., "finds all entities of type `IfcWall`", "element bounding box", "clash detection", etc.)
        max_tokens: Maximum number of tokens to retrieve (default: 2048)

    Returns:
        str: The documentation text as a string

    Side Effect:
        print the retrieved documentation

    Example:
        >>> query_ifcopenshell_docs("How to access element properties")
    """
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
                print(doc_text)
                return doc_text
            elif isinstance(content, dict) and "text" in content:
                print(content["text"])
                return content["text"]

        print(str(data.get("result", data)))
        return str(data.get("result", data))

    except requests.exceptions.RequestException as e:
        return f"Failed to query Context7 API: {str(e)}"


if __name__ == "__main__":
    docs = query_ifcopenshell_docs(
        "get bounding box element")
