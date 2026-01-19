# %% SET UP
import json
import os

import requests
from dotenv import find_dotenv, load_dotenv
from loguru import logger

load_dotenv(find_dotenv())

PERPLEXITY_API_KEY = os.environ["PERPLEXITY_API_KEY"]


# %%
def web_search(
    query: str,
    model: str = "sonar",
) -> str:
    """
    Performs an AI-powered web search.

    Args:
        query (str): The search query. For best results, make queries specific and include
            relevant technical terms (e.g., "IfcOpenShell", "Python", specific function names).

    Returns:
        str: A natural language response synthesized from web search results.
    """
    logger.info("Tool called.")
    logger.debug(f"Query: {query}")
    logger.debug(f"Model: {model}")

    # API endpoint
    url = "https://api.perplexity.ai/chat/completions"

    # hearder
    headers = {
        "Authorization": f"Bearer {PERPLEXITY_API_KEY}",
        "Content-Type": "application/json",
    }

    # System prompt
    system = "You are an artificial intelligence assistant and you need to engage in a helpful, detailed, polite conversation with a user."

    # User's question (formating)
    messages = [
        {
            "role": "system",
            "content": (system),
        },
        {
            "role": "user",
            "content": (query),
        },
    ]

    # payload for http request
    payload = {
        "model": model,
        "messages": messages,
    }

    logger.debug(
        f"Making request to Perplexity API with payload: {json.dumps(payload, indent=2)}"
    )

    # get the response from perplexity API
    response = requests.post(url, json=payload, headers=headers)

    # serialize it and return it
    if response.status_code == 200:
        result = json.loads(response.text)["choices"][0]["message"]["content"]
        logger.info("Successfully received response from Perplexity API")
        logger.debug(
            f"Response content: {result[:200]}..."
        )  # Log first 200 chars of response
        return result
    else:
        error_msg = f"Error when trying to get the answer.\nstatus_code: {response.status_code}."
        logger.error(f"API request failed: {error_msg}")
        return error_msg

    del logger


# %% Test
if __name__ == "__main__":
    # arguments
    question = "How can I get a list of all doors from an .ifc model using IfcOpenShell in python?"

    response1 = web_search(query=question)
    print(response1)
    print("=" * 50, "\n")


# %%
