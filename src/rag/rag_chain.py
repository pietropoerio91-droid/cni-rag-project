import logging
from typing import Any

from langchain_core.embeddings import Embeddings
from langchain_core.language_models import BaseLLM
from langgraph.graph import END, StateGraph
from typing_extensions import TypedDict

from src.core.config_loader import ConfigLoader
from src.governance.monitoring import RAGMonitor
from src.governance.pii_filter import PIIFilter
from src.inference.citation_builder import CitationBuilder
from src.inference.response_generator import ResponseGenerator
from src.rag.grade_docs import GradeDocs
from src.rag.hybrid_retriever import HybridRetriever
from src.rag.prompt_builder import PromptBuilder
from src.rag.query_classifier import QueryClassifier
from src.rag.query_rewriter import QueryRewriter
from src.rag.reranker import Reranker
from src.rag.self_rag import SelfRAG

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
    fallback_triggered: bool
    grade_result: str
    retry_count: int
    self_check_result: str
    fix_attempted: bool


class RAGChain:
    def __init__(self, llm: BaseLLM, embeddings: Embeddings):
        self.llm = llm
        self.query_classifier = QueryClassifier()
        self.hybrid_retriever = HybridRetriever(embeddings)
        self.reranker = Reranker()
        self.grade_docs = GradeDocs(llm)
        self.query_rewriter = QueryRewriter(llm)
        self.prompt_builder = PromptBuilder()
        self.response_generator = ResponseGenerator(llm)
        self.self_rag = SelfRAG(llm)
        self.citation_builder = CitationBuilder()
        self.pii_filter = PIIFilter()
        self.monitor = RAGMonitor()

        config = ConfigLoader.get_rag_config()
        self.fallback_threshold = config.get("fallback", {}).get("score_threshold", 0.5)
        self.fallback_message = config.get("fallback", {}).get(
            "message",
            "Non ho trovato informazioni sufficienti nei documenti disponibili per rispondere a questa domanda.",
        )

        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        workflow = StateGraph(RAGState)

        workflow.add_node("classify", self._classify)
        workflow.add_node("retrieve", self._retrieve)
        workflow.add_node("rerank", self._rerank)
        workflow.add_node("grade_docs", self._grade_docs)
        workflow.add_node("rewrite_query", self._rewrite_query)
        workflow.add_node("build_prompt", self._build_prompt)
        workflow.add_node("generate", self._generate)
        workflow.add_node("self_check", self._self_check)
        workflow.add_node("build_citations", self._build_citations)
        workflow.add_node("fallback", self._fallback)

        workflow.set_entry_point("classify")
        workflow.add_edge("classify", "retrieve")
        workflow.add_edge("retrieve", "rerank")
        workflow.add_edge("rerank", "grade_docs")

        workflow.add_conditional_edges(
            "grade_docs",
            self._after_grade,
            {"pertinente": "build_prompt", "non pertinente": "rewrite_query"},
        )

        workflow.add_conditional_edges(
            "rewrite_query",
            self._after_rewrite,
            {"retry": "retrieve", "fallback": "fallback"},
        )

        workflow.add_edge("build_prompt", "generate")
        workflow.add_edge("generate", "self_check")

        workflow.add_conditional_edges(
            "self_check",
            self._after_self_check,
            {"accurata": "build_citations", "inaccurata": "generate"},
        )

        workflow.add_edge("build_citations", END)
        workflow.add_edge("fallback", END)

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

    def _grade_docs(self, state: RAGState) -> dict[str, Any]:
        docs = state["reranked_docs"]
        if not docs:
            return {"grade_result": "non pertinente"}

        result = self.grade_docs.grade(state["question"], docs)
        self.monitor.log_event(state["trace_id"], "grade_docs", {"result": result})
        return {"grade_result": result}

    def _after_grade(self, state: RAGState) -> str:
        return state.get("grade_result", "non pertinente")

    def _rewrite_query(self, state: RAGState) -> dict[str, Any]:
        retry = state.get("retry_count", 0)
        if retry >= 1:
            return {"retry_count": retry + 1}

        rewritten = self.query_rewriter.rewrite(state["question"])
        self.monitor.log_event(state["trace_id"], "rewrite_query", {"original": state["question"], "rewritten": rewritten})
        return {"question": rewritten, "retry_count": retry + 1}

    def _after_rewrite(self, state: RAGState) -> str:
        if state.get("retry_count", 0) <= 1:
            return "retry"
        return "fallback"

    def _build_prompt(self, state: RAGState) -> dict[str, Any]:
        docs = state["reranked_docs"]
        if not docs:
            return {"prompt": [], "response": self.fallback_message, "fallback_triggered": True}

        prompt = self.prompt_builder.build_prompt(state["question"], docs)
        return {"prompt": prompt, "fallback_triggered": False}

    def _generate(self, state: RAGState) -> dict[str, Any]:
        if state.get("fallback_triggered"):
            return {"response": state["response"]}

        filtered_prompt = []
        for msg in state["prompt"]:
            filtered_prompt.append({"role": msg["role"], "content": self.pii_filter.filter(msg["content"])})

        needs_fix = state.get("self_check_result") == "inaccurata"
        if needs_fix:
            for msg in filtered_prompt:
                if msg["role"] == "system":
                    msg["content"] += "\n\nLa risposta precedente conteneva imprecisioni o allucinazioni. Correggi basandoti ESCLUSIVAMENTE sui documenti forniti. Non inventare nulla."

        response = self.response_generator.generate(filtered_prompt)
        self.monitor.log_event(state["trace_id"], "generate", {"response_length": len(response), "regenerated": needs_fix})
        return {"response": response, "fix_attempted": needs_fix}

    def _self_check(self, state: RAGState) -> dict[str, Any]:
        result = self.self_rag.check(state["question"], state["response"], state["reranked_docs"])
        self.monitor.log_event(state["trace_id"], "self_check", {"result": result})
        return {"self_check_result": result}

    def _after_self_check(self, state: RAGState) -> str:
        result = state.get("self_check_result", "accurata")
        if result == "inaccurata" and not state.get("fix_attempted"):
            return "inaccurata"
        return "accurata"

    def _build_citations(self, state: RAGState) -> dict[str, Any]:
        citations = self.citation_builder.build(state["reranked_docs"], state["response"])
        return {"citations": citations}

    def _fallback(self, state: RAGState) -> dict[str, Any]:
        return {"response": self.fallback_message, "fallback_triggered": True}

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
            "fallback_triggered": False,
            "grade_result": "",
            "retry_count": 0,
            "self_check_result": "",
            "fix_attempted": False,
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

        yield {"type": "metadata", "category": category, "sources": reranked}

        grade = self.grade_docs.grade(question, reranked)

        if grade == "non pertinente":
            rewritten = self.query_rewriter.rewrite(question)
            retrieved = self.hybrid_retriever.retrieve(rewritten)
            reranked = self.reranker.rerank(rewritten, retrieved)
            yield {"type": "metadata", "category": category, "sources": reranked, "rewritten": rewritten}
            grade = self.grade_docs.grade(rewritten, reranked)

        if grade == "non pertinente" or not reranked:
            msg = self.fallback_message
            self.monitor.log_event(trace_id, "generate", {"response_length": len(msg), "fallback": True})
            yield {"type": "chunk", "content": msg}
            citations = self.citation_builder.build(reranked, msg)
            self.monitor.end_trace(trace_id, {"response_length": len(msg)})
            yield {"type": "done", "citations": citations, "trace_id": trace_id}
            return

        safe_question = self.pii_filter.filter(question)
        prompt = self.prompt_builder.build_stream_prompt(safe_question, reranked)

        full_response = ""
        async for chunk in self.response_generator.astream_generate(prompt):
            safe_chunk = self.pii_filter.filter(chunk)
            full_response += safe_chunk
            yield {"type": "chunk", "content": safe_chunk}

        self_check = self.self_rag.check(question, full_response, reranked)
        if self_check == "inaccurata":
            fix_prompt = prompt + "\n\nLa risposta precedente conteneva imprecisioni. Correggi basandoti ESCLUSIVAMENTE sui documenti forniti."
            full_response = ""
            async for chunk in self.response_generator.astream_generate(fix_prompt):
                safe_chunk = self.pii_filter.filter(chunk)
                full_response += safe_chunk
                yield {"type": "chunk", "content": safe_chunk}

        citations = self.citation_builder.build(reranked, full_response)
        self.monitor.end_trace(trace_id, {"response_length": len(full_response)})
        yield {"type": "done", "citations": citations, "trace_id": trace_id}
