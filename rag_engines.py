"""RAG Lab core: six retrieval strategies over one small knowledge base.

Framework split
  LlamaIndex : indexing, dense retrieval, reranking, metadata filters,
               sentence-window parsing, response synthesis
  LangChain  : BM25 + vector store for hybrid search, ChatOllama for
               query transformation and for the routing agent
"""
import json
import re
import time
from pathlib import Path

from langchain_community.retrievers import BM25Retriever
from langchain_core.documents import Document as LCDocument
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_ollama import ChatOllama, OllamaEmbeddings
from llama_index.core import Document, Settings, VectorStoreIndex, get_response_synthesizer
from llama_index.core.node_parser import SentenceSplitter, SentenceWindowNodeParser
from llama_index.core.postprocessor import (
    MetadataReplacementPostProcessor,
    SentenceTransformerRerank,
)
from llama_index.core.response_synthesizers import ResponseMode
from llama_index.core.schema import NodeWithScore, TextNode
from llama_index.core.vector_stores import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.llms.ollama import Ollama

RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
META_KEYS = ["department", "doc_type", "year"]
STRATEGIES = ["normal", "rerank", "hybrid", "query_transform", "sentence_window"]

REWRITE_PROMPT = """You improve search queries for a company knowledge base.
Given the user's question, write 3 alternative search queries:
1. a clearer, more specific rewrite of the question
2. a version that uses formal terms likely found in policy or technical documents
3. a sub-question that covers a different aspect of the same need
Output ONLY the 3 queries, one per line, with no numbering or commentary.

Question: {question}"""

ROUTER_PROMPT = """You are a retrieval strategy router. Pick the single best strategy for the question.
- normal: a simple, clearly worded semantic question
- rerank: a broad question where many chunks look similar and precision matters
- hybrid: the question contains exact keywords such as error codes, IDs, commands or product names
- query_transform: the question is vague, very short, conversational or has several parts
- sentence_window: the question asks for one precise fact that needs surrounding context
Answer with ONLY the strategy name.

Question: {question}"""


def clean(text: str) -> str:
    """Remove <think> blocks that some Qwen variants emit."""
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()


def load_documents(data_dir: str = "data"):
    root = Path(data_dir)
    meta_file = root / "metadata.json"
    meta = json.loads(meta_file.read_text()) if meta_file.exists() else {}
    docs = []
    for path in sorted(root.glob("*.txt")):
        m = meta.get(path.name, {"department": "General", "doc_type": "misc", "year": 0})
        doc = Document(
            text=path.read_text(encoding="utf-8"),
            metadata={**m, "file_name": path.name},
            id_=path.name,
        )
        # keep metadata out of the embedding text so filtering shows a real effect
        doc.excluded_embed_metadata_keys = META_KEYS + ["file_name"]
        docs.append(doc)
    if not docs:
        raise RuntimeError("No .txt files in ./data. Run: python make_docs.py")
    return docs


def rrf(ranked_lists: dict, key, k: int = 60):
    """Reciprocal Rank Fusion. Returns [(item, fused_score, [lists it appeared in])]."""
    scores, items, via = {}, {}, {}
    for name, lst in ranked_lists.items():
        for rank, item in enumerate(lst):
            kk = key(item)
            scores[kk] = scores.get(kk, 0.0) + 1.0 / (k + rank + 1)
            items.setdefault(kk, item)
            via.setdefault(kk, []).append(name)
    order = sorted(scores, key=scores.get, reverse=True)
    return [(items[x], scores[x], via[x]) for x in order]


class RAGSystem:
    def __init__(self, llm_model="qwen2.5:7b", embed_model="nomic-embed-text",
                 data_dir="data", window_size=3):
        Settings.llm = Ollama(model=llm_model, request_timeout=300.0,
                              temperature=0.1, context_window=8192)
        Settings.embed_model = OllamaEmbedding(model_name=embed_model)

        self.docs = load_documents(data_dir)

        # ---- LlamaIndex: standard chunk index ------------------------------
        splitter = SentenceSplitter(chunk_size=128, chunk_overlap=16)
        self.nodes = splitter.get_nodes_from_documents(self.docs)
        self.index = VectorStoreIndex(self.nodes)

        # ---- LlamaIndex: sentence-window index -----------------------------
        wparser = SentenceWindowNodeParser.from_defaults(
            window_size=window_size,
            window_metadata_key="window",
            original_text_metadata_key="original_text",
        )
        self.window_nodes = wparser.get_nodes_from_documents(self.docs)
        self.window_index = VectorStoreIndex(self.window_nodes)
        self.window_post = MetadataReplacementPostProcessor(target_metadata_key="window")

        # ---- LangChain: BM25 + vector store (hybrid) -----------------------
        self.lc_docs = [
            LCDocument(page_content=n.get_content(), metadata=dict(n.metadata))
            for n in self.nodes
        ]
        self.bm25 = BM25Retriever.from_documents(
            self.lc_docs, k=20,
            preprocess_func=lambda t: re.findall(r"\w+", t.lower()),
        )
        self.lc_store = InMemoryVectorStore.from_documents(
            self.lc_docs, OllamaEmbeddings(model=embed_model)
        )

        # ---- LangChain: LLM chains (query transform + router) --------------
        lc_llm = ChatOllama(model=llm_model, temperature=0)
        self.rewrite_chain = ChatPromptTemplate.from_template(REWRITE_PROMPT) | lc_llm | StrOutputParser()
        self.router_chain = ChatPromptTemplate.from_template(ROUTER_PROMPT) | lc_llm | StrOutputParser()

        self.synth = get_response_synthesizer(response_mode=ResponseMode.COMPACT)
        self._reranker = None

    # ------------------------------------------------------------------ utils
    def meta_values(self):
        return {k: sorted({d.metadata[k] for d in self.docs}, key=str) for k in META_KEYS}

    def stats(self):
        return {"documents": len(self.docs), "chunks": len(self.nodes),
                "sentence nodes": len(self.window_nodes)}

    def _get_reranker(self):
        if self._reranker is None:
            self._reranker = SentenceTransformerRerank(model=RERANK_MODEL, top_n=20)
        return self._reranker

    @staticmethod
    def _src(n: NodeWithScore, note=None):
        m = dict(n.node.metadata)
        return {
            "file": m.get("file_name", "?"),
            "text": n.node.get_content(),
            "original": m.get("original_text"),
            "score": n.score,
            "note": note,
            "meta": {k: m[k] for k in META_KEYS if k in m},
        }

    def _finish(self, q, nodes, generate, info, notes=None, extra=None):
        notes = notes or [None] * len(nodes)
        answer = None
        if generate:
            if nodes:
                answer = clean(str(self.synth.synthesize(q, nodes=nodes)))
            else:
                answer = "No chunks matched, so there is nothing to answer from."
        return {
            "answer": answer,
            "info": info,
            "extra": extra or {},
            "sources": [self._src(n, note) for n, note in zip(nodes, notes)],
        }

    # ------------------------------------------------------------- strategies
    def normal(self, q, top_k, fetch_k, filters, generate):
        nodes = self.index.as_retriever(similarity_top_k=top_k).retrieve(q)
        return self._finish(q, nodes, generate,
                            "Baseline: dense embedding similarity, top-k chunks (LlamaIndex).")

    def rerank(self, q, top_k, fetch_k, filters, generate):
        cands = self.index.as_retriever(similarity_top_k=fetch_k).retrieve(q)
        before = {n.node.node_id: i + 1 for i, n in enumerate(cands)}
        best = self._get_reranker().postprocess_nodes(cands, query_str=q)[:top_k]
        notes = [f"dense rank #{before[n.node.node_id]} -> rerank #{i + 1}"
                 for i, n in enumerate(best)]
        return self._finish(
            q, best, generate,
            f"Fetched {fetch_k} candidates by embeddings, then a cross-encoder "
            f"({RERANK_MODEL}) re-scored them against the query.",
            notes)

    def hybrid(self, q, top_k, fetch_k, filters, generate):
        vec = self.lc_store.similarity_search(q, k=fetch_k)
        kw = self.bm25.invoke(q)[:fetch_k]
        fused = rrf({"vector": vec, "bm25": kw}, key=lambda d: d.page_content)[:top_k]
        nodes = [NodeWithScore(node=TextNode(text=d.page_content, metadata=d.metadata), score=s)
                 for d, s, _ in fused]
        notes = ["found by: " + " + ".join(v) for _, _, v in fused]
        return self._finish(
            q, nodes, generate,
            "LangChain BM25 (keywords) + vector search, merged with Reciprocal Rank Fusion.",
            notes)

    def query_transform(self, q, top_k, fetch_k, filters, generate):
        raw = clean(self.rewrite_chain.invoke({"question": q}))
        rewrites = [re.sub(r"^[\d\.\-\*\)\s]+", "", ln).strip() for ln in raw.splitlines()]
        rewrites = [r for r in rewrites if r and r.lower() != q.lower()][:3]
        queries = [q] + rewrites
        retriever = self.index.as_retriever(similarity_top_k=fetch_k)
        lists = {f"q{i}": retriever.retrieve(x) for i, x in enumerate(queries)}
        fused = rrf(lists, key=lambda n: n.node.node_id)[:top_k]
        nodes = [NodeWithScore(node=n.node, score=s) for n, s, _ in fused]
        notes = ["matched queries: " + ", ".join(v) for _, _, v in fused]
        return self._finish(
            q, nodes, generate,
            "LangChain + Qwen rewrote the question into several queries; LlamaIndex "
            "retrieved for each and results were fused.",
            notes, extra={"Transformed queries": queries})

    def metadata(self, q, top_k, fetch_k, filters, generate):
        if not filters:
            return {"error": "Pick at least one metadata filter in the sidebar first."}
        mf = MetadataFilters(
            filters=[MetadataFilter(key=k, value=v, operator=FilterOperator.EQ)
                     for k, v in filters.items()],
            condition=FilterCondition.AND,
        )
        nodes = self.index.as_retriever(similarity_top_k=top_k, filters=mf).retrieve(q)
        return self._finish(
            q, nodes, generate,
            "Dense retrieval restricted by metadata filters (LlamaIndex MetadataFilters).",
            extra={"Active filters": [f"{k} = {v}" for k, v in filters.items()]})

    def sentence_window(self, q, top_k, fetch_k, filters, generate):
        hits = self.window_index.as_retriever(similarity_top_k=top_k).retrieve(q)
        nodes = self.window_post.postprocess_nodes(hits)
        return self._finish(
            q, nodes, generate,
            "Single sentences are embedded for precise matching; each hit is then "
            "expanded to its surrounding window of sentences before generation.")

    # ------------------------------------------------------------------ agent
    def auto(self, q, top_k, fetch_k, filters, generate):
        raw = clean(self.router_chain.invoke({"question": q})).lower()
        choice = next((s for s in STRATEGIES if s in raw), "hybrid")
        res = self.run(choice, q, top_k, fetch_k, filters, generate)
        res["extra"] = {"Agent chose": choice, **res.get("extra", {})}
        return res

    # --------------------------------------------------------------- dispatch
    def run(self, method, q, top_k=3, fetch_k=10, filters=None, generate=True):
        filters = filters or {}
        t0 = time.time()
        if method == "compare":
            results = {m: getattr(self, m)(q, top_k, fetch_k, filters, False) for m in STRATEGIES}
            if filters:
                results["metadata"] = self.metadata(q, top_k, fetch_k, filters, False)
            return {"method": "compare", "results": results, "seconds": time.time() - t0}
        res = getattr(self, method)(q, top_k, fetch_k, filters, generate)
        res["method"] = method
        res["seconds"] = time.time() - t0
        return res
