from fastapi import FastAPI, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.responses import FileResponse
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer, CrossEncoder
from rank_bm25 import BM25Okapi
from fastapi.staticfiles import StaticFiles
from groq import Groq

import numpy as np
import re
import os
import pickle
from sklearn.preprocessing import normalize

# =========================
# 🚀 APP INIT
# =========================
app = FastAPI()
app.mount("/", StaticFiles(directory=".", html=True), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key = os.environ.get("GROQ_API_KEY")

if not api_key:
    raise ValueError("❌ GROQ_API_KEY not set")

client = Groq(api_key=api_key)

# =========================
# 🌍 GLOBALS
# =========================
chunks = []
chunk_texts = []
embeddings = None
bm25 = None

# 🔥 LAZY LOADED MODELS
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

def detect_keywords(q):
    keywords = []
    if "revenue" in q:
        keywords += ["revenue", "sales", "income"]
    if "ebitda" in q:
        keywords += ["ebitda"]
    if "profit" in q:
        keywords += ["profit", "net profit"]
    return keywords

# =========================
# 🤖 GROQ ANSWER
# =========================
def generate_answer(question, context):
    prompt = f"""
You are a financial analyst.

Rules:
- Find the value relevant to the question
- Focus on correct label (like revenue, income, etc.)
- If multiple values exist, choose the correct row
- DO NOT guess
- Return ONLY final answer with unit

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
# 📤 UPLOAD
# =========================
@app.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    global chunks, chunk_texts, embeddings, bm25

    try:
        load_models()  # 🔥 IMPORTANT

        file_path = "temp.pdf"
        cache_path = f"cache_{file.filename}.pkl"

        with open(file_path, "wb") as f:
            f.write(await file.read())

        if os.path.exists(cache_path):
            with open(cache_path, "rb") as f:
                data = pickle.load(f)

            chunks = data["chunks"]
            chunk_texts = data["chunk_texts"]
            embeddings = data["embeddings"]
            bm25 = data["bm25"]

            return {"message": "Loaded from cache ⚡", "chunks": len(chunks)}

        loader = PyPDFLoader(file_path)
        documents = loader.load()
        documents = documents[:50]

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=800,
            chunk_overlap=100
        )

        chunks = splitter.split_documents(documents)
        chunk_texts = [clean_text(c.page_content) for c in chunks]

        embeddings = normalize(np.array(embedder.encode(chunk_texts)))

        tokenized = [tokenize(t) for t in chunk_texts]
        bm25 = BM25Okapi(tokenized)

        with open(cache_path, "wb") as f:
            pickle.dump({
                "chunks": chunks,
                "chunk_texts": chunk_texts,
                "embeddings": embeddings,
                "bm25": bm25
            }, f)

        return {"message": "Processed & cached ✅", "chunks": len(chunks)}

    except Exception as e:
        return {"error": str(e)}

# =========================
# ❓ QUERY MODEL
# =========================
class Query(BaseModel):
    question: str

# =========================
# ❓ ASK
# =========================
@app.post("/ask")
def ask_question(query: Query):
    global chunks, chunk_texts, embeddings, bm25

    try:
        load_models()  # 🔥 IMPORTANT

        if embeddings is None:
            return {"error": "Upload PDF first"}

        q = normalize_question(query.question)
        keywords = detect_keywords(q)

        q_emb = normalize(np.array(embedder.encode([q])))
        scores = np.dot(embeddings, q_emb.T).squeeze()
        top_vec = np.argsort(scores)[-10:][::-1]

        bm25_scores = bm25.get_scores(tokenize(q))
        top_bm25 = np.argsort(bm25_scores)[-10:][::-1]

        combined = list(set(top_vec) | set(top_bm25))

        pairs = [(q, chunk_texts[i]) for i in combined]
        rerank_scores = reranker.predict(pairs)

        scored = list(zip(combined, rerank_scores))
        scored.sort(key=lambda x: x[1], reverse=True)

        filtered = []
        for idx, _ in scored:
            text = chunk_texts[idx].lower()

            if any(k in text for k in keywords):
                filtered.append(idx)

            if len(filtered) == 3:
                break

        if not filtered:
            filtered = [idx for idx, _ in scored[:3]]

        context = "\n\n".join([chunk_texts[i] for i in filtered])
        answer = generate_answer(q, context)

        if answer == "NOT FOUND" or len(answer) > 50:
            answer = context[:100]

        sources = [
            {
                "page": chunks[i].metadata.get("page", "unknown"),
                "text": chunk_texts[i][:200]
            }
            for i in filtered
        ]

        return {"answer": answer, "sources": sources}

    except Exception as e:
        return {"error": str(e)}
