import logging
import os
from typing import Any

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import LlamaCpp
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLLM

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


class ModelFactory:
    @staticmethod
    def create_embeddings() -> Embeddings:
        config = ConfigLoader.get_rag_config()
        emb_config = config.get("embedding", {})

        model_name = os.getenv("EMBEDDING_MODEL") or emb_config.get("model_name", "paraphrase-multilingual-MiniLM-L12-v2")
        device = os.getenv("EMBEDDING_DEVICE") or emb_config.get("device", "cpu")

        logger.info(f"Loading embedding model: {model_name} on {device}")
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={
                "normalize_embeddings": emb_config.get("normalize_embeddings", True),
                "batch_size": emb_config.get("batch_size", 32),
            },
        )

    @staticmethod
    def create_llm() -> BaseLLM:
        config = ConfigLoader.get_rag_config()
        llm_config = config.get("llm", {})

        provider = os.getenv("LLM_PROVIDER") or llm_config.get("provider", "ollama")
        base_url = os.getenv("LLM_BASE_URL") or llm_config.get("base_url", "http://localhost:11434/v1")
        model = os.getenv("LLM_MODEL") or llm_config.get("model", "qwen2.5:3b")

        if provider in ("ollama", "lm_studio"):
            return ModelFactory._create_openai_compatible_llm(base_url, model, llm_config)
        elif provider == "llama_cpp":
            return ModelFactory._create_llama_cpp_llm(model, llm_config)
        else:
            raise ValueError(f"Unsupported LLM provider: {provider}")

    @staticmethod
    def _create_openai_compatible_llm(base_url: str, model: str, config: dict[str, Any]) -> BaseLLM:
        from langchain_openai import ChatOpenAI

        logger.info(f"Connecting to LLM at {base_url} with model {model}")
        params = config.get("parameters", {})
        return ChatOpenAI(
            base_url=base_url,
            model=model,
            temperature=params.get("temperature", 0.2),
            max_tokens=params.get("max_tokens", 2048),
            top_p=params.get("top_p", 0.95),
            frequency_penalty=params.get("frequency_penalty", 0.0),
            presence_penalty=params.get("presence_penalty", 0.0),
            api_key="not-needed",
        )

    @staticmethod
    def _create_llama_cpp_llm(model_path: str, config: dict[str, Any]) -> BaseLLM:
        logger.info(f"Loading local Llama model: {model_path}")
        params = config.get("parameters", {})
        return LlamaCpp(
            model_path=model_path,
            temperature=params.get("temperature", 0.2),
            max_tokens=params.get("max_tokens", 2048),
            top_p=params.get("top_p", 0.95),
            n_ctx=config.get("context_length", 8192),
            verbose=False,
        )
