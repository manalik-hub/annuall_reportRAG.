from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse

from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from groq import Groq

import numpy as np
import re
import os
from sklearn.preprocessing import normalize

# =========================
# 🚀 APP INIT
# =========================
app = FastAPI()

@app.get("/")
def serve_ui():
    return FileResponse("index.html")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# 🔐 GROQ
# =========================
api_key = os.environ.get("GROQ_API_KEY")
if not api_key:
    raise ValueError("GROQ_API_KEY not set")

client = Groq(api_key=api_key)

# =========================
# 🌍 GLOBALS
# =========================
chunks = []
chunk_texts = []
embeddings = None
bm25 = None

embedder = None
reranker = None

# =========================
# 🧠 LOAD MODELS (LAZY)
# =========================
def load_models():
    global embedder, reranker

    if embedder is None:
        print("Loading embedder...")
        embedder = SentenceTransformer("all-MiniLM-L6-v2")

    if reranker is None:
        print("Loading reranker...")
        reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

# =========================
# 🔧 HELPERS
# =========================
def clean_text(text):
    text = text.replace("\n", " ")
    return re.sub(r"\s+", " ", text)

def tokenize(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9.%₹$]", " ", text)
    return text.split()

def normalize_question(q):
    return q.lower().replace("₹", "rupees")

# =========================
# 🤖 GROQ ANSWER
# =========================
def generate_answer(question, context):
    prompt = f"""
You are a financial analyst.

Rules:
- Find the exact value asked
- Do NOT guess
- Return only final answer with unit

Question:
{question}

Context:
{context}
"""

    response = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "system", "content": "Extract correct financial value."},
            {"role": "user", "content": prompt}
        ],
        temperature=0,
        max_tokens=100
    )

    return response.choices[0].message.content.strip()

# =========================
# 📤 UPLOAD (LIGHTWEIGHT)
# =========================
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    global chunks, chunk_texts, embeddings, bm25

    try:
        contents = await file.read()

        # 🚨 LIMIT FILE SIZE (IMPORTANT)
        if len(contents) > 3 * 1024 * 1024:
            return {"error": "File too large (max 3MB)"}

        with open("temp.pdf", "wb") as f:
            f.write(contents)

        loader = PyPDFLoader("temp.pdf")
        documents = loader.load()

        # 🚨 LIMIT PAGES
        documents = documents[:10]

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        chunks = splitter.split_documents(documents)
        chunk_texts = [clean_text(c.page_content) for c in chunks]

        # 🔥 RESET embeddings so they regenerate fresh
        embeddings = None
        bm25 = None

        return {
            "message": "PDF processed ✅",
            "chunks": len(chunks)
        }

    except Exception as e:
        print("UPLOAD ERROR:", str(e))
        return {"error": str(e)}

# =========================
# ❓ QUERY MODEL
# =========================
class Query(BaseModel):
    question: str

# =========================
# ❓ ASK (HEAVY WORK HERE)
# =========================
@app.post("/ask")
def ask_question(query: Query):
    global embeddings, bm25

    try:
        if not chunk_texts:
            return {"error": "Upload PDF first"}

        # 🔥 LOAD MODELS HERE ONLY
        load_models()

        # 🔥 CREATE EMBEDDINGS ONLY ONCE
        if embeddings is None:
            print("Creating embeddings...")
            embeddings = normalize(np.array(embedder.encode(chunk_texts)))

            tokenized = [tokenize(t) for t in chunk_texts]
            bm25 = BM25Okapi(tokenized)

        q = normalize_question(query.question)

        # 🔍 VECTOR SEARCH
        q_emb = normalize(np.array(embedder.encode([q])))
        scores = np.dot(embeddings, q_emb.T).squeeze()
        top_vec = np.argsort(scores)[-5:][::-1]

        # 🔍 BM25
        bm25_scores = bm25.get_scores(tokenize(q))
        top_bm25 = np.argsort(bm25_scores)[-5:][::-1]

        combined = list(set(top_vec) | set(top_bm25))

        # 🔁 RERANK
        pairs = [(q, chunk_texts[i]) for i in combined]
        rerank_scores = reranker.predict(pairs)

        scored = list(zip(combined, rerank_scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        top_chunks = [idx for idx, _ in scored[:3]]

        context = "\n\n".join([chunk_texts[i] for i in top_chunks])

        answer = generate_answer(q, context)

        sources = [
            {
                "page": chunks[i].metadata.get("page", "unknown"),
                "text": chunk_texts[i][:200]
            }
            for i in top_chunks
        ]

        return {"answer": answer, "sources": sources}

    except Exception as e:
        print("ASK ERROR:", str(e))
        return {"error": str(e)}
