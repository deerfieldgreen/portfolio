


se this Model and API endpoint

from openai import OpenAI

client = OpenAI(
api_key="",
base_url="https://api.novita.ai/openai"
)

response = client.chat.completions.create(
model="qwen/qwen3.5-397b-a17b",
messages=[
{"role": "system", "content": "You are a helpful assistant."},
{"role": "user", "content": "Hello, how are you?"}
],
max_tokens=64000,
temperature=0.7
)

print(response.choices[0].message.content)





