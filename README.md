# 🔎 RAG Lab: retrieval techniques side by side

A small Streamlit app that runs **the same question through six different retrieval strategies** so you can *see* how they differ. It uses **LlamaIndex** and **LangChain** together, with a local **Ollama + Qwen** model, so nothing leaves your machine.

![Guided demo](screenshots/guided-demo.png)

## What's inside

| # | Technique | What it does | Framework |
|---|---|---|---|
| 1 | **Normal retrieval** | Dense embedding similarity, top-k chunks (the baseline) | LlamaIndex |
| 2 | **Reranking** | Fetch many candidates, re-score them with a cross-encoder | LlamaIndex |
| 3 | **Hybrid search** | BM25 keywords + vector search, merged with Reciprocal Rank Fusion | LangChain |
| 4 | **Query transformation** | Qwen rewrites the question into several queries, results are fused | LangChain + LlamaIndex |
| 5 | **Metadata filtering** | Restrict search by department, doc type and year | LlamaIndex |
| 6 | **Sentence window** | Match single sentences, then expand to the surrounding window | LlamaIndex |
| 🤖 | **Auto agent** | Qwen chooses the best strategy for the question | LangChain |
| ⚖️ | **Compare all** | Shows what every strategy retrieves, side by side | Both |

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com) installed and running
- Roughly 8 GB of RAM for `qwen2.5:7b` (use `qwen2.5:3b` on smaller machines)
- Internet access once, to download the models (the reranker comes from Hugging Face)

## Quick start

```bash
# 1. Pull the models
ollama pull qwen2.5:7b
ollama pull nomic-embed-text

# 2. Set up the environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Generate the sample documents and run the app
python make_docs.py
streamlit run app.py
```

Open the URL Streamlit prints (usually http://localhost:8501). The first start embeds all documents, which takes a moment.

## How to use it

### 🎯 Guided demo
Pick a scenario and press **Run**. Normal retrieval runs next to one technique, and each side shows the rank of the correct document, the number of wrong-document chunks, and the context size. A "What changed" summary lists what the technique dropped and brought in.

| Scenario | Question | Trap for Normal retrieval |
|---|---|---|
| Hybrid search | `What does ERR-5003 mean?` | Old error catalogs full of similar codes |
| Metadata filtering | `How many days of annual leave do employees get?` | 2023 policy (20 days) vs 2024 policy (24 days) |
| Query transformation | `I want my money back for the plan I bought` | Vendor and expense documents that sound closer than the refund documents |
| Reranking | `Who has to approve my travel expenses?` | Procurement and 2023 expense policies full of "approve" |
| Sentence window | `How long does the canary phase last?` | Fixed-size chunk vs one matched sentence plus its neighbours |

### 🎮 Playground
Type any question and press one of the buttons. Use the sidebar to change top-k, the number of candidates fetched, and the metadata filters used by button 5.

![Playground](screenshots/playground.png)

## Project structure

```
rag-lab/
├── app.py            # Streamlit UI: guided demo + playground
├── rag_engines.py    # All retrieval strategies (LlamaIndex + LangChain)
├── make_docs.py      # Creates the sample knowledge base in ./data
├── requirements.txt
└── data/             # Generated .txt documents + metadata.json
```

## Using your own documents

1. Drop `.txt` files into `data/`.
2. Optionally add entries to `data/metadata.json` with `department`, `doc_type` and `year`. Files without an entry get `General / misc / 0`.
3. Click **Rebuild indexes** in the sidebar.

Note that `python make_docs.py` rewrites `data/`, so keep your own files in a separate folder or copy them back afterwards.

## How it works

- **Chunking:** documents are split into ~128-token chunks with `SentenceSplitter`. A second index stores individual sentences with a 3-sentence window for strategy 6.
- **Embeddings:** `nomic-embed-text` through Ollama, used by both frameworks.
- **Hybrid search:** LangChain's `BM25Retriever` and an in-memory vector store each return ranked lists, which are merged with Reciprocal Rank Fusion (`score = Σ 1 / (60 + rank)`).
- **Reranking:** `cross-encoder/ms-marco-MiniLM-L-6-v2` scores each (question, chunk) pair together, which is slower than embeddings but more precise.
- **Query transformation:** a LangChain chain asks Qwen for three alternative queries, LlamaIndex retrieves for each, and the lists are fused.
- **Auto agent:** a LangChain router prompt asks Qwen to pick one strategy, then runs it. If the answer can't be parsed it falls back to hybrid.
- **Answers:** every strategy uses the same LlamaIndex response synthesizer, so only the retrieval step differs.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not start the RAG system" | Make sure Ollama is running (`ollama serve`) and both models are pulled |
| Very slow answers | Try `qwen2.5:3b`, or lower top-k in the sidebar |
| First click on Reranking is slow | The cross-encoder is downloaded once from Hugging Face |
| A demo scenario shows no difference | Results depend on the models. Raise "Candidates fetched", or tweak the documents in `make_docs.py` |
| New documents don't show up | Click **Rebuild indexes** in the sidebar |
| Qwen3 prints reasoning text | `<think>` blocks are stripped, but `qwen2.5` gives the cleanest answers |

## Tech stack

Streamlit · LlamaIndex · LangChain · Ollama (Qwen 2.5, nomic-embed-text) · sentence-transformers · rank_bm25
