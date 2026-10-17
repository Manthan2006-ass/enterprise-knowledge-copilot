import os
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "openai/gpt-oss-20b"

def get_config():
    return {
        "provider": os.getenv("LLM_PROVIDER", "groq").strip().lower(),
        "groq_api_key": os.getenv("GROQ_API_KEY", "").strip(),
        "groq_model": os.getenv("GROQ_MODEL", DEFAULT_MODEL).strip(),
    }

def chat_completion_sync(messages: list[dict], temperature: float = 0.0) -> str:
    cfg = get_config()
    if cfg["provider"] == "groq":
        from groq import Groq, NotFoundError
        client = Groq(api_key=cfg["groq_api_key"])
        try:
            response = client.chat.completions.create(
                model=cfg["groq_model"],
                messages=messages,
                temperature=temperature,
            )
        except NotFoundError:
            # Automatic fallback if the specified model string fails
            response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=temperature,
            )
        return (response.choices[0].message.content or "").strip()

def chat_completion_stream(messages: list[dict], temperature: float = 0.0):
    cfg = get_config()
    if cfg["provider"] == "groq":
        from groq import Groq, NotFoundError
        client = Groq(api_key=cfg["groq_api_key"])
        try:
            stream = client.chat.completions.create(
                model=cfg["groq_model"],
                messages=messages,
                temperature=temperature,
                stream=True,
            )
        except NotFoundError:
            stream = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=messages,
                temperature=temperature,
                stream=True,
            )
        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if token:
                yield token