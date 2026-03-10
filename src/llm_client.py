"""Centralized LLM client with support for OpenAI-compatible and native Ollama APIs."""

import openai
import logging
from typing import Any

from config import Config

logger = logging.getLogger(__name__)


class _OllamaResponseCompat:
    """Wraps a native Ollama ChatResponse to match the OpenAI response shape.

    Callers only access response.choices[0].message.content, so this is all
    that needs to be emulated.
    """

    class _Message:
        def __init__(self, content: str):
            self.content = content

    class _Choice:
        def __init__(self, content: str):
            self.message = _OllamaResponseCompat._Message(content)

    def __init__(self, content: str):
        self.choices = [self._Choice(content)]


class LLMClient:
    """LLM client that supports both the OpenAI-compatible API and the native
    Ollama API.

    When ``OLLAMA_HOST`` is configured, the native Ollama client is used so
    that Ollama-specific options (``num_ctx``, ``keep_alive``, etc.) are sent
    via the proper wire format.  Otherwise the standard OpenAI client is used
    with Ollama extras injected through ``extra_body``.
    """

    def __init__(self):
        if Config.OLLAMA_HOST:
            import ollama

            self._ollama_client = ollama.AsyncClient(host=Config.OLLAMA_HOST)
            self._openai_client = None
            self._extra_body = None
            logger.info(f"Using native Ollama API at {Config.OLLAMA_HOST}")
        else:
            self._ollama_client = None
            self._openai_client = openai.AsyncOpenAI(
                api_key=Config.OPENAI_API_KEY,
                base_url=Config.OPENAI_BASE_URL,
            )
            self._extra_body = Config.get_ollama_extra_body()
            if self._extra_body:
                logger.info(f"Ollama extra_body configured: {self._extra_body}")

    async def create_chat_completion(self, **kwargs) -> Any:
        """Create a chat completion.

        When using the native Ollama client the response is wrapped to expose
        the same ``choices[0].message.content`` interface as the OpenAI SDK.
        """
        if self._ollama_client is not None:
            return await self._ollama_chat(**kwargs)

        if self._extra_body:
            caller_extra = kwargs.pop("extra_body", None) or {}
            merged = {**self._extra_body, **caller_extra}
            kwargs["extra_body"] = merged

        return await self._openai_client.chat.completions.create(**kwargs)

    async def _ollama_chat(self, **kwargs) -> _OllamaResponseCompat:
        """Translate an OpenAI-style call into a native Ollama API call."""
        model = kwargs.get("model")
        messages = kwargs.get("messages", [])

        options = {}
        if Config.OLLAMA_NUM_CTX is not None:
            options["num_ctx"] = Config.OLLAMA_NUM_CTX
        if Config.OLLAMA_THINKING is not None:
            options["thinking"] = Config.OLLAMA_THINKING
        if Config.OLLAMA_THINK_BUDGET is not None:
            options["think_budget"] = Config.OLLAMA_THINK_BUDGET

        call_kwargs = {"model": model, "messages": messages}
        if options:
            call_kwargs["options"] = options
        if Config.OLLAMA_KEEP_ALIVE is not None:
            call_kwargs["keep_alive"] = Config.OLLAMA_KEEP_ALIVE

        response = await self._ollama_client.chat(**call_kwargs)
        return _OllamaResponseCompat(response.message.content)
