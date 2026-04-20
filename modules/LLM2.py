import os

from openai import OpenAI

from dotenv import load_dotenv

load_dotenv()
PROXY_API_OPENAI_KEY = os.getenv("PROXY_API_OPENAI_KEY")

client = OpenAI(
    base_url="https://api.proxyapi.ru/openai/v1",
    api_key=PROXY_API_OPENAI_KEY,
)


def query(content):
    completion = client.chat.completions.create(
        extra_body={},
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": content
                    }
                ]
            }
        ]
    )
    print(completion)
    return completion.choices[0].message.content

#
# msg = "Привет, как звучит теорема Менелая?"
# print(query(msg))