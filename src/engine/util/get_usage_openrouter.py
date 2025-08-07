import requests
from dotenv import load_dotenv
import os


def get_usage_openrouter() -> float:
    """Retrieve the current usage data for the API key stored in the environment."""
    load_dotenv()
    openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
    response = requests.get(
        url="https://openrouter.ai/api/v1/auth/key",
        headers={"Authorization": f"Bearer {openrouter_api_key}"},
    )
    return float(response.json()["data"]["usage"])


if __name__ == "__main__":
    print(f"current balance: {get_usage_openrouter()}")
