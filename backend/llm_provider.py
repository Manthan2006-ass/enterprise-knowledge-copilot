"""
LLM Provider abstraction.

Set LLM_PROVIDER=groq  in .env to use Groq (cloud, blazing fast, ideal for deployment).
Set LLM_PROVIDER=ollama in .env to use Ollama (local, offline).

Both expose the same interface so chat.py and main.py don't need to care which one
is active — they just call chat_completion_sync() or chat_completion_stream().
"""
import os
from dotenv import load_dotenv

load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


def get_config():
    provider = os.getenv("LLM_PROVIDER", "groq").strip().lower()
    groq_api_key = os.getenv("GROQ_API_KEY", "").strip()
    groq_model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").strip()
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip()
    return {
        "provider": provider,
        "groq_api_key": groq_api_key,
        "groq_model": groq_model,
        "ollama_base_url": ollama_base_url,
        "ollama_model": ollama_model,
    }


def chat_completion_sync(messages: list[dict], temperature: float = 0.0) -> str:
    """
    Blocking (synchronous) chat completion.
    Returns the full assistant reply as a string.
    Used by condense_query() and suggested-questions generation.
    """
    cfg = get_config()
    if cfg["provider"] == "groq":
        from groq import Groq
        client = Groq(api_key=cfg["groq_api_key"])
        response = client.chat.completions.create(
            model=cfg["groq_model"],
            messages=messages,
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()
    else:
        from ollama import Client as OllamaClient
        client = OllamaClient(host=cfg["ollama_base_url"], timeout=300.0)
        response = client.chat(
            model=cfg["ollama_model"],
            messages=messages,
            options={"temperature": temperature},
        )
        return response["message"]["content"].strip()


def chat_completion_stream(messages: list[dict], temperature: float = 0.0):
    """
    Generator that yields tokens one by one.
    Used by stream_chat_response() in chat.py for SSE streaming.
    """
    cfg = get_config()
    if cfg["provider"] == "groq":
        from groq import Groq
        client = Groq(api_key=cfg["groq_api_key"])
        stream = client.chat.completions.create(
            model=cfg["groq_model"],
            messages=messages,
            temperature=temperature,
            stream=True,
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if token:
                yield token
    else:
        from ollama import Client as OllamaClient
        client = OllamaClient(host=cfg["ollama_base_url"], timeout=300.0)
        stream = client.chat(
            model=cfg["ollama_model"],
            messages=messages,
            options={"temperature": temperature},
            stream=True,
        )
        for chunk in stream:
            yield chunk["message"]["content"]
