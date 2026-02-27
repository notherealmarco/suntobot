"""Centralized LLM client with Ollama support via extra_body."""

import openai
import logging

from config import Config

logger = logging.getLogger(__name__)


class LLMClient:
    """Wrapper around openai.AsyncOpenAI that injects Ollama-specific options."""

    def __init__(self):
        self.client = openai.AsyncOpenAI(
            api_key=Config.OPENAI_API_KEY,
            base_url=Config.OPENAI_BASE_URL,
        )
        self._extra_body = Config.get_ollama_extra_body()
        if self._extra_body:
            logger.info(f"Ollama extra_body configured: {self._extra_body}")

    async def create_chat_completion(
        self, **kwargs
    ) -> openai.types.chat.ChatCompletion:
        """Proxy for client.chat.completions.create with Ollama options merged in.

        Any caller-supplied extra_body keys take precedence over the global config.
        """
        if self._extra_body:
            caller_extra = kwargs.pop("extra_body", None) or {}
            merged = {**self._extra_body, **caller_extra}
            kwargs["extra_body"] = merged

        return await self.client.chat.completions.create(**kwargs)
