# %% SET UP
import os
import requests
import json
from dotenv import load_dotenv, find_dotenv
from src.engine.util import get_logger
from src.config import LOG_LEVEL

load_dotenv(find_dotenv())

PERPLEXITY_API_KEY = os.environ["PERPLEXITY_API_KEY"]


# %%
def web_search(
    query: str,
    model: str = "sonar",
) -> str:
    """
    Performs an AI-powered web search using Perplexity's Sonar API, which provides real-time
    search results with natural language responses. The function is designed to help find
    and explain technical information, particularly about programming and libraries.

    Args:
        query (str): The search query. For best results, make queries specific and include
            relevant technical terms (e.g., "IfcOpenShell", "Python", specific function names).
        model (str, optional): The model to use for the search.
            Defaults to "sonar".
            Available models are: "sonar", "sonar-pro", "sonar-reasoning", "sonar-reasoning-pro".
            - sonar: Base model for general queries
            - sonar-pro: Enhanced version with better accuracy
            - sonar-reasoning: Optimized for complex analytical queries
            - sonar-reasoning-pro: Most capable model for technical analysis

    Returns:
        str: A natural language response synthesized from web search results.
             On success (status code 200), returns a detailed explanation or answer.
             On failure, returns an error message string containing the status code and error details.
    """
    logger = get_logger("web_search", log_level=LOG_LEVEL)
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
