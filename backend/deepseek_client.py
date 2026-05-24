from openai import AsyncOpenAI
from config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

_client = None


def get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_BASE_URL,
        )
    return _client


async def chat_stream(messages: list, temperature: float = 0.7, max_tokens: int = 4096):
    client = get_client()
    stream = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        stream=True,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


async def chat_single(messages: list, temperature: float = 0.7, max_tokens: int = 4096) -> str:
    client = get_client()
    response = await client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=messages,
        stream=False,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content or ""
