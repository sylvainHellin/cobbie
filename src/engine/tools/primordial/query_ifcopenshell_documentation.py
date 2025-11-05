import os
import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())
CONTEXT7_API_KEY = os.getenv("CONTEXT7_API_KEY")


def query_ifcopenshell_docs(query: str, max_tokens: int = 2048) -> str:
    """
    Retrieves up-to-date information and code examples related to the provided query from the IFCopenshell documentation.

    Args:
        query: The topic or query to focus the documentation on (e.g., "file reading",
               "geometry", "IFC entities")
        max_tokens: Maximum number of tokens to retrieve (default: 2048)

    Returns:
        str: The documentation text as a string

    Example:
        >>> docs = query_ifcopenshell_docs("Using the IfcOpenShell Python API, write a script that opens an IFC4 file, finds all entities of type `IfcWall`, and prints their `GlobalId` attribute. The script should not modify or save the file.")
        >>> print(docs)
    """
    if not CONTEXT7_API_KEY:
        return "Could not retrieve the information ; API_KEY missing."

    url = "https://mcp.context7.com/mcp"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get-library-docs",
            "arguments": {
                "context7CompatibleLibraryID": "/ifcopenshell/ifcopenshell",
                "topic": query,
                "tokens": max_tokens,
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


if __name__ == "__main__":
    docs = query_ifcopenshell_docs(
        "reading IFC files and accessing entities", max_tokens=3000
    )
    print(f"Retrieved documentation: \n\n{docs}")
