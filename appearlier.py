import streamlit as st

from rag_engines import RAGSystem

st.set_page_config(page_title="RAG Lab", page_icon="🔎", layout="wide")

METHODS = [
    ("normal", "1 · Normal retrieval"),
    ("rerank", "2 · Reranking"),
    ("hybrid", "3 · Hybrid search"),
    ("query_transform", "4 · Query transformation"),
    ("metadata", "5 · Metadata filtering"),
    ("sentence_window", "6 · Sentence window"),
    ("auto", "🤖 Auto agent"),
    ("compare", "⚖️ Compare all"),
]
LABELS = dict(METHODS)


@st.cache_resource(show_spinner="Building indexes (embedding all documents)...")
def get_rag(llm_model: str, embed_model: str):
    return RAGSystem(llm_model=llm_model, embed_model=embed_model)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Settings")
    llm_model = st.text_input("Ollama LLM", "qwen2.5:7b")
    embed_model = st.text_input("Ollama embedding model", "nomic-embed-text")
    top_k = st.slider("Chunks returned (top-k)", 1, 8, 3)
    fetch_k = st.slider("Candidates fetched (rerank / hybrid / transform)", 5, 30, 10)

try:
    rag = get_rag(llm_model, embed_model)
except Exception as e:  # Ollama not running, model not pulled, etc.
    st.error(f"Could not start the RAG system: {e}")
    st.info("Is `ollama serve` running, and did you `ollama pull` both models?")
    st.stop()

with st.sidebar:
    st.subheader("Metadata filters (button 5)")
    values = rag.meta_values()
    filters = {}
    for key in ["department", "doc_type", "year"]:
        choice = st.selectbox(key, ["Any"] + values[key])
        if choice != "Any":
            filters[key] = choice
    if st.button("Rebuild indexes"):
        st.cache_resource.clear()
        st.rerun()
    st.caption(" · ".join(f"{k}: {v}" for k, v in rag.stats().items()))

# --------------------------------------------------------------------- main
st.title("🔎 RAG Lab: retrieval techniques side by side")
st.caption("LlamaIndex + LangChain · Ollama Qwen · one question, many ways to retrieve")

query = st.text_input("Ask a question about the knowledge base",
                      placeholder="e.g. How many days of annual leave do employees get?")

clicked = None
for row in (METHODS[:4], METHODS[4:]):
    cols = st.columns(4)
    for col, (key, label) in zip(cols, row):
        if col.button(label, use_container_width=True, key=key):
            clicked = key

if clicked:
    if not query.strip():
        st.warning("Type a question first.")
    else:
        with st.spinner(f"Running {LABELS[clicked]}..."):
            try:
                st.session_state["result"] = rag.run(
                    clicked, query.strip(), top_k=top_k, fetch_k=fetch_k, filters=filters,
                    generate=True,
                )
                st.session_state["query"] = query.strip()
            except Exception as e:
                st.session_state["result"] = {"error": f"{type(e).__name__}: {e}"}


def render_sources(sources):
    for i, s in enumerate(sources, 1):
        score = f"{s['score']:.3f}" if s["score"] is not None else "n/a"
        with st.expander(f"#{i} · {s['file']} · score {score}", expanded=(i == 1)):
            if s.get("note"):
                st.caption(s["note"])
            if s.get("original"):
                st.markdown("**Matched sentence**")
                st.write(s["original"])
                st.markdown("**Window sent to the LLM**")
            st.write(s["text"])
            st.caption("  ·  ".join(f"{k}: {v}" for k, v in s["meta"].items()))


def render_single(res):
    st.caption(f"⏱ {res['seconds']:.1f}s · {res['info']}")
    for label, value in res.get("extra", {}).items():
        st.markdown(f"**{label}**")
        if isinstance(value, list):
            st.markdown("\n".join(f"- {v}" for v in value))
        else:
            st.write(value)
    if res.get("answer"):
        st.subheader("Answer")
        st.write(res["answer"])
    st.subheader("Retrieved chunks")
    render_sources(res["sources"])


res = st.session_state.get("result")
if res:
    st.divider()
    if res.get("error"):
        st.warning(res["error"])
    elif res["method"] == "compare":
        st.subheader(f"Retrieval only · {st.session_state['query']}")
        st.caption(f"⏱ {res['seconds']:.1f}s")
        items = list(res["results"].items())
        for start in range(0, len(items), 3):
            cols = st.columns(3)
            for col, (m, r) in zip(cols, items[start:start + 3]):
                with col:
                    st.markdown(f"**{LABELS[m]}**")
                    if r.get("error"):
                        st.caption(r["error"])
                        continue
                    for i, s in enumerate(r["sources"], 1):
                        score = f"{s['score']:.3f}" if s["score"] is not None else "n/a"
                        st.markdown(f"{i}. `{s['file']}` ({score})")
                        st.caption((s["original"] or s["text"])[:110] + "...")
    else:
        st.subheader(f"{LABELS[res['method']]} · {st.session_state['query']}")
        render_single(res)

with st.expander("Try these questions"):
    st.markdown(
        "- **Normal / metadata:** *How many days of annual leave do employees get?* "
        "(plain retrieval mixes the 2023 and 2024 policies; filter `year = 2024`)\n"
        "- **Hybrid:** *What does ERR-5003 mean and what should I do?* (exact code match)\n"
        "- **Query transformation:** *stuff about getting my money back* (vague wording)\n"
        "- **Reranking:** *Who has to approve my travel expenses?*\n"
        "- **Sentence window:** *How long does the canary phase last?*\n"
        "- **Auto agent:** any of the above, and watch which strategy it picks"
    )
