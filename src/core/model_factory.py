import logging
import os
from typing import Any

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.llms import LlamaCpp
from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLLM

from src.core.config_loader import ConfigLoader

logger = logging.getLogger(__name__)


# Prefissi obbligatori per famiglia di modelli.
#
# Alcuni modelli di embedding non sono simmetrici: sono addestrati con due
# istruzioni testuali diverse a seconda che il testo sia una domanda o un
# passaggio da indicizzare. La famiglia `multilingual-e5` (e `e5` in generale)
# richiede letteralmente "query: " davanti alla domanda e "passage: " davanti
# al documento. Non e' una convenzione estetica: senza prefissi il modello
# lavora fuori dalla distribuzione vista in addestramento e la qualita' del
# recupero cala in modo misurabile.
#
# `paraphrase-multilingual-MiniLM-L12-v2`, il modello attuale, e' invece
# simmetrico e non vuole alcun prefisso: la tabella restituisce due stringhe
# vuote e il comportamento resta identico a prima.
#
# ATTENZIONE — la regola vale per l'indicizzazione tanto quanto per la ricerca.
# Un indice costruito con i prefissi e interrogato senza (o viceversa) e'
# silenziosamente degradato: nessun errore, solo risultati peggiori. Per questo
# i prefissi risolti vengono scritti nel log all'avvio.
PREFISSI_PER_FAMIGLIA: list[tuple[tuple[str, ...], tuple[str, str]]] = [
    (("multilingual-e5", "/e5-", "e5-small", "e5-base", "e5-large"), ("query: ", "passage: ")),
    (("bge-m3", "paraphrase-", "distiluse", "labse"), ("", "")),
]


def prefissi_per_modello(model_name: str) -> tuple[str, str]:
    """Restituisce (prefisso_query, prefisso_documento) per il modello dato."""
    nome = model_name.lower()
    for marcatori, prefissi in PREFISSI_PER_FAMIGLIA:
        if any(m in nome for m in marcatori):
            return prefissi
    return ("", "")


class PrefixedEmbeddings(Embeddings):
    """Adattatore che antepone i prefissi richiesti dal modello.

    Avvolge l'oggetto `Embeddings` vero e proprio invece di modificare i punti
    di chiamata. Il progetto ne ha tre — `EmbeddingGenerator`,
    `VectorRetriever` e il browser Qdrant dell'API — e tutti ricevono il
    modello da `ModelFactory.create_embeddings()`: incapsulando qui la regola
    non e' possibile che uno dei tre se ne dimentichi, che e' esattamente il
    modo in cui un indice e una query finiscono per divergere.
    """

    def __init__(self, inner: Embeddings, query_prefix: str = "", document_prefix: str = "") -> None:
        self.inner = inner
        self.query_prefix = query_prefix
        self.document_prefix = document_prefix

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(f"{self.query_prefix}{text}")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents([f"{self.document_prefix}{t}" for t in texts])


class ModelFactory:
    @staticmethod
    def create_embeddings() -> Embeddings:
        config = ConfigLoader.get_rag_config()
        emb_config = config.get("embedding", {})

        model_name = os.getenv("EMBEDDING_MODEL") or emb_config.get("model_name", "paraphrase-multilingual-MiniLM-L12-v2")
        device = os.getenv("EMBEDDING_DEVICE") or emb_config.get("device", "cpu")

        logger.info(f"Loading embedding model: {model_name} on {device}")
        modello = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": device},
            encode_kwargs={
                "normalize_embeddings": emb_config.get("normalize_embeddings", True),
                "batch_size": emb_config.get("batch_size", 32),
            },
        )

        # Il YAML puo' forzare i prefissi; altrimenti valgono quelli della famiglia.
        automatici = prefissi_per_modello(model_name)
        query_prefix = emb_config.get("query_prefix", automatici[0])
        document_prefix = emb_config.get("document_prefix", automatici[1])

        if not query_prefix and not document_prefix:
            logger.info("Embedding prefixes: none (symmetric model)")
            return modello

        logger.info(
            f"Embedding prefixes: query={query_prefix!r} document={document_prefix!r} "
            f"— l'indice va costruito con gli stessi prefissi"
        )
        return PrefixedEmbeddings(modello, query_prefix, document_prefix)

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
