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

# Each scenario is built so that Normal retrieval is tempted by a wrong document.
SCENARIOS = [
    {
        "title": "Hybrid search · exact error code",
        "query": "What does ERR-5003 mean?",
        "method": "hybrid",
        "filters": {},
        "expected": ["eng_incident_runbook_2024.txt"],
        "bad": ["eng_error_catalog_2023.txt", "eng_incident_runbook_2023.txt",
                "support_error_codes_customer_2024.txt"],
        "why": "Embeddings treat 'ERR-5003' as just another error code, so the old error "
               "catalog (full of similar codes) competes with the right runbook. BM25 matches "
               "the exact token '5003', and fusion pulls the runbook to the top.",
    },
    {
        "title": "Metadata filtering · outdated policy",
        "query": "How many days of annual leave do employees get?",
        "method": "metadata",
        "filters": {"department": "HR", "year": 2024},
        "expected": ["hr_leave_policy_2024.txt"],
        "bad": ["hr_leave_policy_2023.txt", "hr_leave_faq_2025.txt"],
        "why": "The 2023 and 2024 leave policies say almost the same thing with different "
               "numbers (20 vs 24 days). Similarity can't tell which year you mean, so a plain "
               "search may return the outdated one. The filter department=HR, year=2024 removes it.",
    },
    {
        "title": "Query transformation · vague wording",
        "query": "I want my money back for the plan I bought",
        "method": "query_transform",
        "filters": {},
        "expected": ["support_faq_2025.txt", "finance_refund_policy_2024.txt"],
        "bad": ["finance_vendor_payments_2024.txt", "finance_expense_policy_2025.txt",
                "finance_expense_policy_2023.txt"],
        "why": "'Money back' is casual wording. Finance documents about getting money back from "
               "vendors or reimbursing expenses sound closer than the customer refund FAQ. Qwen "
               "rewrites the question into 'refund policy for annual plans' style queries.",
    },
    {
        "title": "Reranking · look-alike documents",
        "query": "Who has to approve my travel expenses?",
        "method": "rerank",
        "filters": {},
        "expected": ["finance_expense_policy_2025.txt"],
        "bad": ["finance_procurement_policy_2024.txt", "finance_expense_policy_2023.txt",
                "legal_vendor_contract_guidelines_2024.txt"],
        "why": "The procurement policy is full of 'approve' and 'approval' words, so embeddings "
               "rank it highly. A cross-encoder reads the question and each chunk together and "
               "pushes the travel-expense chunk up. Watch the 'dense rank -> rerank' notes.",
    },
    {
        "title": "Sentence window · precise fact with context",
        "query": "How long does the canary phase last?",
        "method": "sentence_window",
        "filters": {},
        "expected": ["eng_deployment_guide_2025.txt"],
        "bad": [],
        "why": "Normal chunks are fixed-size slices that can start or end mid-thought. Here a "
               "single sentence is matched precisely and only its neighbouring sentences are "
               "added. Look at 'Matched sentence' vs the window, and at the context size.",
    },
]


@st.cache_resource(show_spinner="Building indexes (embedding all documents)...")
def get_rag(llm_model: str, embed_model: str):
    return RAGSystem(llm_model=llm_model, embed_model=embed_model)


def fmt_score(s):
    return f"{s:.3f}" if s is not None else "n/a"


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

st.title("🔎 RAG Lab: retrieval techniques side by side")
st.caption("LlamaIndex + LangChain · Ollama Qwen · same question, different ways to retrieve")

tab_demo, tab_play = st.tabs(["🎯 Guided demo (see the difference)", "🎮 Playground"])


# ============================================================ GUIDED DEMO
def scenario_stats(res, sc):
    files = [s["file"] for s in res["sources"]]
    hits = [i for i, f in enumerate(files, 1) if f in sc["expected"]]
    rank = hits[0] if hits else None
    wrong = sum(f in sc["bad"] for f in files)
    ctx = sum(len(s["text"]) for s in res["sources"]) // max(len(files), 1)
    return files, rank, wrong, ctx


def render_side(title, res, sc, other_files):
    st.markdown(f"### {title}")
    if res.get("error"):
        st.warning(res["error"])
        return
    files, rank, wrong, ctx = scenario_stats(res, sc)
    m1, m2, m3 = st.columns(3)
    m1.metric("Correct doc rank", f"#{rank}" if rank else "❌ missing")
    m2.metric("Wrong-doc chunks", wrong)
    m3.metric("Avg context (chars)", ctx)
    for label, value in res.get("extra", {}).items():
        st.markdown(f"**{label}**")
        st.markdown("\n".join(f"- {v}" for v in value) if isinstance(value, list) else str(value))
    st.markdown("**Answer**")
    st.success(res["answer"]) if rank == 1 else st.write(res["answer"])
    st.markdown("**Retrieved chunks**")
    for i, s in enumerate(res["sources"], 1):
        mark = "✅" if s["file"] in sc["expected"] else ("⚠️" if s["file"] in sc["bad"] else "▫️")
        new = " 🆕" if other_files is not None and s["file"] not in other_files else ""
        st.markdown(f"{i}. {mark} `{s['file']}` ({fmt_score(s['score'])}){new}")
        if s.get("note"):
            st.caption(s["note"])
        snippet = s["original"] or s["text"]
        st.caption(snippet[:170] + ("..." if len(snippet) > 170 else ""))


def render_demo(demo):
    sc, a, b = demo["sc"], demo["normal"], demo["tech"]
    st.caption(f"✅ correct document · ⚠️ distractor · 🆕 not found by the other side · "
               f"⏱ {a['seconds']:.1f}s vs {b['seconds']:.1f}s")
    left, right = st.columns(2)
    files_a = [s["file"] for s in a["sources"]]
    files_b = [s["file"] for s in b["sources"]] if not b.get("error") else []
    with left:
        render_side("Normal retrieval", a, sc, None)
    with right:
        render_side(LABELS[sc["method"]], b, sc, files_a)
    if not b.get("error"):
        dropped = [f for f in dict.fromkeys(files_a) if f not in files_b]
        gained = [f for f in dict.fromkeys(files_b) if f not in files_a]
        st.markdown("#### What changed")
        st.markdown(f"- Dropped by the technique: {', '.join(f'`{f}`' for f in dropped) or 'nothing'}")
        st.markdown(f"- Brought in by the technique: {', '.join(f'`{f}`' for f in gained) or 'nothing'}")
        top_a = files_a[0] if files_a else None
        top_b = files_b[0] if files_b else None
        st.markdown("- Top result: " + ("same document" if top_a == top_b
                                        else f"`{top_a}` became `{top_b}`"))


with tab_demo:
    st.markdown("Pick a scenario. Each one is designed so **Normal retrieval is tempted by a "
                "wrong document**, then the matching technique is run next to it.")
    pick = st.selectbox("Scenario", [s["title"] for s in SCENARIOS])
    sc = next(s for s in SCENARIOS if s["title"] == pick)
    st.markdown(f"**Question:** `{sc['query']}`")
    if sc["filters"]:
        st.markdown("**Filters used:** " + ", ".join(f"{k} = {v}" for k, v in sc["filters"].items()))
    st.info(sc["why"])
    st.caption("Correct source: " + " or ".join(f"`{f}`" for f in sc["expected"]))
    if st.button(f"▶ Run: Normal vs {LABELS[sc['method']]}", type="primary"):
        with st.spinner("Running both pipelines..."):
            try:
                st.session_state["demo"] = {
                    "sc": sc,
                    "normal": rag.run("normal", sc["query"], top_k, fetch_k, {}, True),
                    "tech": rag.run(sc["method"], sc["query"], top_k, fetch_k, sc["filters"], True),
                }
            except Exception as e:
                st.error(f"{type(e).__name__}: {e}")
    demo = st.session_state.get("demo")
    if demo and demo["sc"]["title"] == sc["title"]:
        st.divider()
        render_demo(demo)


# ============================================================== PLAYGROUND
def render_sources(sources):
    for i, s in enumerate(sources, 1):
        with st.expander(f"#{i} · {s['file']} · score {fmt_score(s['score'])}", expanded=(i == 1)):
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
        st.markdown("\n".join(f"- {v}" for v in value) if isinstance(value, list) else str(value))
    if res.get("answer"):
        st.subheader("Answer")
        st.write(res["answer"])
    st.subheader("Retrieved chunks")
    render_sources(res["sources"])


def render_compare(res):
    st.caption(f"⏱ {res['seconds']:.1f}s · retrieval only · 🆕 = document that Normal retrieval "
               "did not return · ⬆️⬇️ = position change vs Normal")
    base = [s["file"] for s in res["results"]["normal"]["sources"]]
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
                    tag = ""
                    if m != "normal":
                        if s["file"] not in base:
                            tag = " 🆕"
                        else:
                            old = base.index(s["file"]) + 1
                            tag = " ⬆️" if i < old else (" ⬇️" if i > old else "")
                    st.markdown(f"{i}. `{s['file']}` ({fmt_score(s['score'])}){tag}")
                    snippet = s["original"] or s["text"]
                    st.caption(snippet[:140] + "...")


with tab_play:
    query = st.text_input("Ask your own question about the knowledge base",
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
                        clicked, query.strip(), top_k=top_k, fetch_k=fetch_k,
                        filters=filters, generate=True)
                    st.session_state["query"] = query.strip()
                except Exception as e:
                    st.session_state["result"] = {"error": f"{type(e).__name__}: {e}"}

    res = st.session_state.get("result")
    if res:
        st.divider()
        if res.get("error"):
            st.warning(res["error"])
        elif res["method"] == "compare":
            st.subheader(f"Compare all · {st.session_state['query']}")
            render_compare(res)
        else:
            st.subheader(f"{LABELS[res['method']]} · {st.session_state['query']}")
            render_single(res)