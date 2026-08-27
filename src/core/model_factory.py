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
    def _generation_params(llm_config: dict[str, Any]) -> dict[str, Any]:
        """Parametri di generazione, letti da dove stanno davvero.

        Il codice precedente cercava `llm.parameters.temperature`, mentre
        config/rag_config.yaml li dichiara direttamente sotto `llm`:

            llm:
              model: qwen2.5:3b
              temperature: 0.2      <- qui, non sotto `parameters`

        `config.get("parameters", {})` restituiva quindi sempre un dizionario
        vuoto e valevano i default scritti nel codice. Il difetto era invisibile
        perche' quei default coincidevano con i valori nel YAML — ma qualunque
        modifica alla configurazione non aveva effetto, e il config_snapshot
        salvato in ogni run di valutazione documentava valori diversi da quelli
        realmente usati.

        Vengono accettate entrambe le forme: le chiavi al livello di `llm` e,
        se presenti, quelle annidate sotto `parameters`, che hanno la
        precedenza. Cosi' nessuna configurazione esistente si rompe.
        """
        DEFAULTS = {
            "temperature": 0.2,
            "max_tokens": 2048,
            "top_p": 0.95,
            "frequency_penalty": 0.0,
            "presence_penalty": 0.0,
        }
        annidati = llm_config.get("parameters") or {}
        return {
            chiave: annidati.get(chiave, llm_config.get(chiave, default))
            for chiave, default in DEFAULTS.items()
        }

    @staticmethod
    def _create_openai_compatible_llm(base_url: str, model: str, config: dict[str, Any]) -> BaseLLM:
        from langchain_openai import ChatOpenAI

        params = ModelFactory._generation_params(config)
        logger.info(
            f"Connecting to LLM at {base_url} with model {model} — "
            f"temperature={params['temperature']}, max_tokens={params['max_tokens']}, "
            f"top_p={params['top_p']}"
        )
        return ChatOpenAI(
            base_url=base_url,
            model=model,
            temperature=params["temperature"],
            max_tokens=params["max_tokens"],
            top_p=params["top_p"],
            frequency_penalty=params["frequency_penalty"],
            presence_penalty=params["presence_penalty"],
            api_key="not-needed",
        )

    @staticmethod
    def _create_llama_cpp_llm(model_path: str, config: dict[str, Any]) -> BaseLLM:
        params = ModelFactory._generation_params(config)
        logger.info(
            f"Loading local Llama model: {model_path} — "
            f"temperature={params['temperature']}, max_tokens={params['max_tokens']}"
        )
        return LlamaCpp(
            model_path=model_path,
            temperature=params["temperature"],
            max_tokens=params["max_tokens"],
            top_p=params["top_p"],
            n_ctx=config.get("context_length", 8192),
            verbose=False,
        )
