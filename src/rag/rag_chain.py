import logging
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLLM
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.governance.monitoring import RAGMonitor
from src.governance.pii_filter import PIIFilter
from src.inference.citation_builder import CitationBuilder
from src.inference.response_generator import ResponseGenerator
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.prompt_builder import PromptBuilder
from src.rag.query_classifier import QueryClassifier
from src.rag.reranker import Reranker

logger = logging.getLogger(__name__)


class RAGState(TypedDict):
    question: str
    category: str
    retrieved_docs: list[dict[str, Any]]
    reranked_docs: list[dict[str, Any]]
    prompt: list[dict[str, str]]
    response: str
    citations: list[dict[str, Any]]
    trace_id: str


class RAGChain:
    def __init__(self, llm: BaseLLM, embeddings: Embeddings):
        self.llm = llm
        self.query_classifier = QueryClassifier()
        self.hybrid_retriever = HybridRetriever(embeddings)
        self.reranker = Reranker()
        self.prompt_builder = PromptBuilder()
        self.response_generator = ResponseGenerator(llm)
        self.citation_builder = CitationBuilder()
        self.pii_filter = PIIFilter()
        self.monitor = RAGMonitor()

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(RAGState)

        workflow.add_node("classify", self._classify)
        workflow.add_node("retrieve", self._retrieve)
        workflow.add_node("rerank", self._rerank)
        workflow.add_node("build_prompt", self._build_prompt)
        workflow.add_node("generate", self._generate)
        workflow.add_node("build_citations", self._build_citations)

        workflow.set_entry_point("classify")
        workflow.add_edge("classify", "retrieve")
        workflow.add_edge("retrieve", "rerank")
        workflow.add_edge("rerank", "build_prompt")
        workflow.add_edge("build_prompt", "generate")
        workflow.add_edge("generate", "build_citations")
        workflow.add_edge("build_citations", END)

        return workflow.compile()

    def _classify(self, state: RAGState) -> dict[str, Any]:
        category = self.query_classifier.classify(state["question"])
        self.monitor.log_event(state["trace_id"], "classify", {"category": category})
        return {"category": category}

    def _retrieve(self, state: RAGState) -> dict[str, Any]:
        docs = self.hybrid_retriever.retrieve(state["question"])
        self.monitor.log_event(state["trace_id"], "retrieve", {"count": len(docs)})
        return {"retrieved_docs": docs}

    def _rerank(self, state: RAGState) -> dict[str, Any]:
        docs = self.reranker.rerank(state["question"], state["retrieved_docs"])
        self.monitor.log_event(state["trace_id"], "rerank", {"count": len(docs)})
        return {"reranked_docs": docs}

    def _build_prompt(self, state: RAGState) -> dict[str, Any]:
        prompt = self.prompt_builder.build_prompt(state["question"], state["reranked_docs"])
        return {"prompt": prompt}

    def _generate(self, state: RAGState) -> dict[str, Any]:
        filtered_prompt = []
        for msg in state["prompt"]:
            filtered_prompt.append({"role": msg["role"], "content": self.pii_filter.filter(msg["content"])})
        response = self.response_generator.generate(filtered_prompt)
        self.monitor.log_event(state["trace_id"], "generate", {"response_length": len(response)})
        return {"response": response}

    def _build_citations(self, state: RAGState) -> dict[str, Any]:
        citations = self.citation_builder.build(state["reranked_docs"], state["response"])
        return {"citations": citations}

    def query(self, question: str) -> dict[str, Any]:
        trace_id = self.monitor.start_trace()
        initial_state: RAGState = {
            "question": question,
            "category": "",
            "retrieved_docs": [],
            "reranked_docs": [],
            "prompt": [],
            "response": "",
            "citations": [],
            "trace_id": trace_id,
        }

        final_state = self.graph.invoke(initial_state)
        self.monitor.end_trace(trace_id, {"response_length": len(final_state.get("response", ""))})

        return {
            "response": final_state.get("response", ""),
            "citations": final_state.get("citations", []),
            "category": final_state.get("category", ""),
            "trace_id": trace_id,
        }

    async def astream(self, question: str):
        trace_id = self.monitor.start_trace()

        category = self.query_classifier.classify(question)
        retrieved = self.hybrid_retriever.retrieve(question)
        reranked = self.reranker.rerank(question, retrieved)

        safe_question = self.pii_filter.filter(question)

        prompt = self.prompt_builder.build_stream_prompt(safe_question, reranked)

        yield {"type": "metadata", "category": category, "sources": reranked}

        full_response = ""
        async for chunk in self.response_generator.astream_generate(prompt):
            safe_chunk = self.pii_filter.filter(chunk)
            full_response += safe_chunk
            yield {"type": "chunk", "content": safe_chunk}

        citations = self.citation_builder.build(reranked, full_response)
        self.monitor.end_trace(trace_id, {"response_length": len(full_response)})
        yield {"type": "done", "citations": citations, "trace_id": trace_id}
