import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
REQUEST_TIMEOUT = 40


def query(content: str, model: str = DEFAULT_MODEL) -> dict | None:
    """Sends a request to OpenRouter and returns parsed JSON."""
    if not OPENROUTER_API_KEY:
        logger.warning("OPENROUTER_API_KEY is not configured.")
        return None

    try:
        response = requests.post(
            url=OPENROUTER_URL,
            headers={
                "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": content}],
            },
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as exc:
        logger.warning("OpenRouter request failed: %s", exc)
        if 'response' in locals() and response is not None:
            logger.warning("OpenRouter response body: %s", response.text[:200])
        return None
