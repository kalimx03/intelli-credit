"""
RAG ENGINE — Intelli-Credit
============================

WHAT IS RAG?
  RAG = Retrieval-Augmented Generation.
  Instead of asking Claude to "know" all RBI/GST/MCA rules from training,
  we store those rules ourselves in a vector database and RETRIEVE the
  relevant ones before each Claude call. Claude then answers using real
  regulatory text — not its memory.

TECHNOLOGY STACK:
  ┌─────────────────────────────────────────────────────────────────┐
  │  sentence-transformers (all-MiniLM-L6-v2)                       │
  │  • Converts text → 384-number vector (embedding)                │
  │  • 22 MB model, runs on CPU, no API key needed                  │
  │  • Same model used for both ingestion and queries               │
  ├─────────────────────────────────────────────────────────────────┤
  │  ChromaDB (embedded mode)                                        │
  │  • Stores vectors on disk in ./chroma_db/                        │
  │  • No separate server — just a folder                           │
  │  • Finds "nearest neighbours" using cosine similarity           │
  ├─────────────────────────────────────────────────────────────────┤
  │  Claude (claude-sonnet-4-20250514)                               │
  │  • Receives retrieved chunks as context in system prompt        │
  │  • Generates grounded answers citing actual regulations         │
  └─────────────────────────────────────────────────────────────────┘

WHERE RAG IS APPLIED IN THIS PROJECT:
  1. CAM Narrative Generation  → relevant RBI/GST norms injected
  2. Credit Q&A Chatbot        → analyst questions answered with regulation context
  3. Governance Risk Context   → GST/RPT/litigation flags trigger targeted retrieval
  4. Sector Intelligence       → sector-specific risk docs retrieved per company

FLOW:
  INGESTION (once at startup):
    regulations.txt → parse into 20 doc chunks → embed each →
    store (id, text, vector, metadata) in ChromaDB

  RETRIEVAL (every CAM / chat request):
    user query → embed query → cosine similarity search →
    top-4 matching chunks → format as context → inject into Claude prompt
"""

import os
import re
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

# Lazy globals — only initialised on first use
_chroma_client = None
_embedding_model = None
_collection = None

CHROMA_PERSIST_DIR  = os.environ.get("CHROMA_PERSIST_DIR", "./chroma_db")
COLLECTION_NAME     = "intelli_credit_knowledge"
KNOWLEDGE_BASE_DIR  = Path(__file__).parent / "knowledge_base"
EMBEDDING_MODEL     = "all-MiniLM-L6-v2"


# ── Model + collection loaders ───────────────────────────────────────────────

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading embedding model '%s' (first run downloads ~22MB)...", EMBEDDING_MODEL)
            _embedding_model = SentenceTransformer(EMBEDDING_MODEL)
            logger.info("Embedding model loaded.")
        except ImportError:
            raise RuntimeError("Run: pip install sentence-transformers")
    return _embedding_model


def _get_chroma_collection():
    global _chroma_client, _collection
    if _collection is None:
        try:
            import chromadb
            from chromadb.config import Settings
        except ImportError:
            raise RuntimeError("Run: pip install chromadb")

        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR,
            settings=Settings(anonymized_telemetry=False),
        )
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info("ChromaDB ready at '%s' — %d chunks.", CHROMA_PERSIST_DIR, _collection.count())
    return _collection


# ── Document parsing ─────────────────────────────────────────────────────────

def _parse_knowledge_base(filepath: Path) -> List[Dict[str, Any]]:
    """
    Parse regulations.txt into structured chunks.
    Each chunk = one DOC_ID block.
    """
    text = filepath.read_text(encoding="utf-8")
    raw_docs = re.split(r"---\s*\nDOC_ID:", text)
    chunks = []
    for raw in raw_docs:
        raw = raw.strip()
        if not raw:
            continue
        lines = raw.split("\n")
        doc_id = lines[0].strip()
        category, title, body_lines = "", "", []
        in_body = False
        for line in lines[1:]:
            if line.startswith("CATEGORY:"):
                category = line.replace("CATEGORY:", "").strip()
            elif line.startswith("TITLE:"):
                title = line.replace("TITLE:", "").strip()
            elif line.startswith("---"):
                in_body = True
            elif in_body:
                body_lines.append(line)
        content = "\n".join(body_lines).strip()
        if content:
            chunks.append({
                "doc_id":    doc_id,
                "category":  category,
                "title":     title,
                "content":   content,
                "full_text": f"[{title}]\n{content}",
            })
    return chunks


# ── Ingestion ────────────────────────────────────────────────────────────────

def ingest_knowledge_base(force_reingest: bool = False) -> int:
    """
    Embed and store all knowledge base documents into ChromaDB.
    Skips if already done (idempotent). Pass force_reingest=True to rebuild.
    """
    collection = _get_chroma_collection()
    existing = collection.count()

    if existing > 0 and not force_reingest:
        logger.info("KB already ingested (%d chunks). Skipping.", existing)
        return existing

    model = _get_embedding_model()
    all_chunks: List[Dict[str, Any]] = []

    if not KNOWLEDGE_BASE_DIR.exists():
        logger.warning("Knowledge base dir not found: %s", KNOWLEDGE_BASE_DIR)
        return 0

    for kb_file in sorted(KNOWLEDGE_BASE_DIR.glob("*.txt")):
        logger.info("Parsing: %s", kb_file.name)
        chunks = _parse_knowledge_base(kb_file)
        all_chunks.extend(chunks)
        logger.info("  → %d chunks", len(chunks))

    if not all_chunks:
        logger.warning("No chunks found in knowledge base.")
        return 0

    # Rebuild collection if force
    if force_reingest and existing > 0:
        global _collection
        _chroma_client.delete_collection(COLLECTION_NAME)
        _collection = _chroma_client.get_or_create_collection(
            name=COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        collection = _collection

    # Embed in batches
    BATCH = 50
    total = 0
    for i in range(0, len(all_chunks), BATCH):
        batch = all_chunks[i: i + BATCH]
        texts     = [c["full_text"] for c in batch]
        ids       = [f"{c['doc_id']}_{i+j}" for j, c in enumerate(batch)]
        metadatas = [{"doc_id": c["doc_id"], "category": c["category"], "title": c["title"]}
                     for c in batch]
        embeddings = model.encode(texts, show_progress_bar=False).tolist()
        collection.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)
        total += len(batch)

    logger.info("Ingestion complete — %d chunks stored.", total)
    return total


# ── Retrieval ────────────────────────────────────────────────────────────────

def retrieve_context(
    query: str,
    n_results: int = 4,
    category_filter: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    THE CORE RAG OPERATION.

    1. Embed the query using the same model used during ingestion
    2. Ask ChromaDB: "which stored vectors are most similar to this?"
    3. Return the top-N matching document chunks

    Args:
        query:           Natural language question or topic string
        n_results:       How many chunks to return (default 4)
        category_filter: Restrict to one category, e.g. 'rbi_guidelines'
                         Categories: rbi_guidelines, gst_regulations,
                         mca_regulations, credit_norms, sector_intelligence,
                         governance, historical_decisions, fraud_prevention

    Returns:
        List of {"text", "title", "category", "score"} dicts
        score = cosine similarity 0.0–1.0 (higher = more relevant)
    """
    collection = _get_chroma_collection()
    model = _get_embedding_model()

    if collection.count() == 0:
        logger.warning("Empty knowledge base — triggering ingestion.")
        ingest_knowledge_base()

    # Embed the query
    query_vec = model.encode([query], show_progress_bar=False).tolist()[0]

    # ChromaDB similarity search
    where = {"category": {"$eq": category_filter}} if category_filter else None
    try:
        results = collection.query(
            query_embeddings=[query_vec],
            n_results=min(n_results, max(1, collection.count())),
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except Exception as e:
        logger.error("ChromaDB query failed: %s", e)
        return []

    docs   = results.get("documents", [[]])[0]
    metas  = results.get("metadatas", [[]])[0]
    dists  = results.get("distances",  [[]])[0]

    retrieved = []
    for doc, meta, dist in zip(docs, metas, dists):
        retrieved.append({
            "text":     doc,
            "title":    meta.get("title", ""),
            "category": meta.get("category", ""),
            "score":    round(1 - dist, 3),   # cosine distance → similarity
        })

    if retrieved:
        logger.info("RAG: '%s...' → %d chunks (top: %.2f)", query[:40], len(retrieved), retrieved[0]["score"])
    return retrieved


def format_context_for_prompt(chunks: List[Dict[str, Any]]) -> str:
    """Format retrieved chunks as a readable context block for Claude."""
    if not chunks:
        return "No relevant regulatory context retrieved."
    parts = []
    for i, c in enumerate(chunks, 1):
        parts.append(
            f"[Regulation {i}: {c['title']} | Relevance {c['score']:.0%}]\n{c['text']}"
        )
    return "\n\n".join(parts)


# ── Convenience retrievers used by CAM + chat ────────────────────────────────

def get_regulatory_context(financials_summary: str) -> List[Dict[str, Any]]:
    """Retrieve general regulatory context relevant to this financial profile."""
    return retrieve_context(
        f"Indian banking credit appraisal norms DSCR ICR leverage: {financials_summary[:200]}",
        n_results=3,
    )


def get_sector_context(sector: Optional[str]) -> List[Dict[str, Any]]:
    """Retrieve sector-specific risk intelligence."""
    if not sector:
        return []
    results = retrieve_context(f"sector credit risk {sector}", n_results=2,
                               category_filter="sector_intelligence")
    if not results:
        results = retrieve_context(f"sector risk {sector}", n_results=2)
    return results


def get_governance_context(has_litigation: bool, has_rpt: bool,
                            has_gst_mismatch: bool) -> List[Dict[str, Any]]:
    """Retrieve governance/fraud regulation context based on active flags."""
    topics = []
    if has_gst_mismatch:
        topics.append("GST mismatch fraud credit risk 2A 3B reconciliation")
    if has_rpt:
        topics.append("related party transactions fund diversion fraud")
    if has_litigation:
        topics.append("litigation legal risk credit appraisal")
    if not topics:
        return []
    return retrieve_context(" | ".join(topics), n_results=3)


def get_historical_context(score: float, sector: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve similar historical credit decisions for peer comparison."""
    band = "approve" if score >= 75 else ("conditional" if score >= 50 else "reject")
    return retrieve_context(
        f"historical credit decision {band} {sector or ''} outcome result",
        n_results=2, category_filter="historical_decisions",
    )
