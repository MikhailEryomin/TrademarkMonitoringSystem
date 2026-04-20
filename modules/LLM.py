import logging
import os

import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://api.proxyapi.ru/openrouter/v1/chat/completions"
DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"
REQUEST_TIMEOUT = 40


def query(content: str, model: str = DEFAULT_MODEL):
    response = requests.post(
        url=OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "max_tokens": 300
        },
        timeout=REQUEST_TIMEOUT,
    )

    completion = response.json()
    return completion["choices"][0]["message"]["content"]


# msg = "Привет, как звучит теорема Менелая?"
# print(query(msg))
