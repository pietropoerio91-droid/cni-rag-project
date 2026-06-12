import asyncio
import logging
from typing import Any, AsyncGenerator

from langchain_core.language_models import BaseLLM

from src.inference.llm_client import LLMClient

logger = logging.getLogger(__name__)


class ResponseGenerator:
    def __init__(self, llm: BaseLLM):
        self.client = LLMClient(llm)

    def generate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return self.client.invoke(messages, **kwargs)

    async def agenerate(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return await self.client.ainvoke(messages, **kwargs)

    async def astream_generate(self, prompt: str, **kwargs: Any) -> AsyncGenerator[str, None]:
        messages = [{"role": "user", "content": prompt}]

        loop = asyncio.get_running_loop()
        sync_gen = self.client.stream(messages, **kwargs)

        while True:
            chunk = await loop.run_in_executor(None, lambda: next(sync_gen, _SENTINEL))
            if chunk is _SENTINEL:
                break
            yield chunk


_SENTINEL = object()
