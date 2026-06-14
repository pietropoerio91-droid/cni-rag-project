import logging
from typing import Any

from langchain_core.language_models import BaseLLM

from src.core.model_factory import ModelFactory

logger = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, llm: BaseLLM | None = None):
        self.llm = llm or ModelFactory.create_llm()

    def invoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        langchain_messages = []
        for msg in messages:
            if msg["role"] == "system":
                langchain_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                langchain_messages.append(HumanMessage(content=msg["content"]))

        try:
            result = self.llm.invoke(langchain_messages, **kwargs)
            content = result.content if hasattr(result, "content") else str(result)
            logger.debug(f"LLM response: {content[:100]}...")
            return content
        except Exception as e:
            logger.error(f"LLM invocation failed: {e}")
            return f"Errore nella generazione della risposta: {e}"

    async def ainvoke(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        from langchain_core.messages import HumanMessage, SystemMessage

        langchain_messages = []
        for msg in messages:
            if msg["role"] == "system":
                langchain_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                langchain_messages.append(HumanMessage(content=msg["content"]))

        try:
            result = await self.llm.ainvoke(langchain_messages, **kwargs)
            content = result.content if hasattr(result, "content") else str(result)
            return content
        except Exception as e:
            logger.error(f"Async LLM invocation failed: {e}")
            return f"Errore nella generazione della risposta: {e}"

    def stream(self, messages: list[dict[str, str]], **kwargs: Any):
        from langchain_core.messages import HumanMessage, SystemMessage

        langchain_messages = []
        for msg in messages:
            if msg["role"] == "system":
                langchain_messages.append(SystemMessage(content=msg["content"]))
            elif msg["role"] == "user":
                langchain_messages.append(HumanMessage(content=msg["content"]))

        try:
            for chunk in self.llm.stream(langchain_messages, **kwargs):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    yield content
        except Exception as e:
            logger.error(f"LLM stream failed: {e}")
            yield f"Errore nella generazione della risposta: {e}"
