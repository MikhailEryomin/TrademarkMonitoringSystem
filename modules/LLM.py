import requests
from dotenv import load_dotenv
import os
import json

load_dotenv()
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')


def query(content):
    return requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        },
        data=json.dumps({
            "model": "meta-llama/llama-3.3-70b-instruct",
            "messages": [
                {
                    "role": "user",
                    "content": f"{content}"
                }
            ]
        })
    )