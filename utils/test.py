from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="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",
)

completion = client.chat.completions.create(
    extra_headers={},
    extra_body={},
    model="meta-llama/llama-3.3-70b-instruct:free",
    messages=[
        {
            "role": "user",
            "content": "What is the meaning of life?"
        }
    ]
)
print(completion.choices[0].message.content)
