import os
import re
import uuid
import json
import logging
from datetime import datetime
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from typing import Optional, List
from pydantic import BaseModel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger("intelli_credit")

app = FastAPI(
    title="Intelli-Credit API",
    version="2.0.0",
    description="AI-powered corporate credit decisioning — deterministic scoring + RAG.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Global error handler ────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled %s on %s %s", type(exc).__name__, request.method, request.url, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": "An unexpected error occurred."},
    )


# ── Helpers ─────────────────────────────────────────────────────────────────

def _validate_uuid(value: str, label: str = "ID") -> str:
    clean = value.strip()
    try:
        uuid.UUID(clean)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid {label}: {clean!r}")
    return clean


def _sanitise_company_name(name: str) -> str:
    return re.sub(r"[\x00-\x1f\x7f]", "", name).strip()[:200] or "Unknown Company"


# ── Models ───────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    question: str
    conversation_history: Optional[list] = None


# ── Startup ─────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    from database import init_db
    init_db()
    try:
        from rag_engine import ingest_knowledge_base
        count = ingest_knowledge_base()
        logger.info("RAG knowledge base ready: %d chunks.", count)
    except Exception as e:
        logger.warning("RAG ingestion skipped (install sentence-transformers + chromadb): %s", e)
    logger.info("Intelli-Credit API v2.0.0 started.")


# ── Health ───────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    return {"status": "Intelli-Credit API running", "version": "2.0.0"}


@app.get("/health", tags=["Health"])
def health():
    api_key_set = bool(os.environ.get("CLAUDE_API_KEY", ""))
    rag_ok = False
    try:
        from rag_engine import _get_chroma_collection
        rag_ok = _get_chroma_collection().count() > 0
    except Exception:
        pass
    return {
        "status": "ok",
        "claude_api_key_configured": api_key_set,
        "rag_ready": rag_ok,
    }


# ── Analysis list ────────────────────────────────────────────────────────────

@app.get("/analyses", tags=["Analysis"])
def get_analyses():
    from database import list_analyses
    try:
        return {"analyses": list_analyses()}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Could not retrieve analyses: {e}")


# ── Main analysis endpoint ───────────────────────────────────────────────────

@app.post("/analyze", tags=["Analysis"])
async def analyze(
    file: UploadFile = File(...),
    company_name: str = Form(default="Unknown Company"),
    primary_insights: Optional[str] = Form(default=None),
    loan_amount_requested: Optional[float] = Form(default=None),
):
    from pdf_extractor import extract_text_from_pdf
    from llm_service import extract_financials_from_text, analyze_management_insights, _build_null_extraction_skeleton
    from validation import validate_and_flag
    from scoring import run_scoring
    from database import save_analysis
    from models import ManagementInsightFlags

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=f"Only PDF files accepted. Got: '{file.filename}'")
    if loan_amount_requested is not None and loan_amount_requested < 0:
        raise HTTPException(status_code=400, detail="loan_amount_requested must be non-negative.")

    company_name = _sanitise_company_name(company_name)
    analysis_id = str(uuid.uuid4())

    try:
        file_bytes = await file.read()
        document_text = extract_text_from_pdf(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=f"PDF error: {e}")
    except Exception as e:
        logger.error("PDF extraction crash: %s", e)
        raise HTTPException(status_code=422, detail="Failed to read PDF.")

    extraction_warnings: List[str] = []
    try:
        raw_extracted = extract_financials_from_text(document_text)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM service unavailable: {e}")
    except Exception as e:
        logger.warning("LLM unusable output, using null skeleton: %s", e)
        raw_extracted = _build_null_extraction_skeleton()
        extraction_warnings.append("[LLM] Extraction failed — all fields null. Check PDF quality.")

    if loan_amount_requested is not None:
        existing = raw_extracted.get("loan_amount_requested", {})
        if not (isinstance(existing, dict) and existing.get("value") is not None):
            raw_extracted["loan_amount_requested"] = {
                "value": loan_amount_requested,
                "confidence": 1.0,
                "evidence": "Provided by user in submission form.",
            }

    financials, val_warnings = validate_and_flag(raw_extracted)
    all_warnings = extraction_warnings + val_warnings

    try:
        mgmt_flags = analyze_management_insights(primary_insights or "")
    except Exception as e:
        logger.warning("Management analysis failed: %s", e)
        mgmt_flags = ManagementInsightFlags()
        all_warnings.append("[MGMT] Management analysis unavailable — defaults used.")

    try:
        scoring_result = run_scoring(financials, mgmt_flags)
    except Exception as e:
        logger.error("Scoring engine error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Scoring engine error: {e}")

    financials_dict = financials.model_dump()
    scoring_dict = scoring_result.model_dump()

    try:
        save_analysis(analysis_id, company_name, financials_dict, scoring_dict, all_warnings)
    except Exception as e:
        logger.error("DB save failed: %s", e)
        all_warnings.append("[DB] Analysis not persisted — results in-memory only.")

    return {
        "analysis_id": analysis_id,
        "company_name": company_name,
        "extracted_financials": financials_dict,
        "scoring_result": scoring_dict,
        "validation_warnings": all_warnings,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ── CAM generation ───────────────────────────────────────────────────────────

@app.post("/generate-cam/{analysis_id}", tags=["CAM"])
def generate_cam_endpoint(analysis_id: str):
    analysis_id = _validate_uuid(analysis_id, "analysis_id")

    from database import get_analysis, update_cam_path
    from llm_service import generate_cam_narratives
    from cam_generator import generate_cam_pdf

    row = get_analysis(analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    company_name = _sanitise_company_name(row.get("company_name") or "Unknown")

    try:
        financials = json.loads(row["extracted_financials"])
        scoring    = json.loads(row["scoring_result"])
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"Stored data corrupt: {e}")

    fin_summary = json.dumps(
        {k: v.get("value") for k, v in financials.items()
         if isinstance(v, dict) and v.get("value") is not None},
        indent=2,
    )
    scoring_summary = json.dumps(
        {k: v for k, v in scoring.items()
         if k in {"final_score", "risk_band", "decision", "five_cs",
                  "suggested_loan_limit", "suggested_interest_rate"}},
        indent=2,
    )

    rag_context = ""
    try:
        from rag_engine import (
            get_regulatory_context, get_sector_context,
            get_governance_context, format_context_for_prompt,
        )
        sector_val = None
        sf = financials.get("industry_sector", {})
        if isinstance(sf, dict):
            sector_val = sf.get("value")

        def _flag(field):
            f = financials.get(field, {})
            return bool(isinstance(f, dict) and f.get("value"))

        reg_chunks  = get_regulatory_context(fin_summary)
        sec_chunks  = get_sector_context(sector_val)
        gov_chunks  = get_governance_context(
            has_litigation=_flag("litigation_pending"),
            has_rpt=_flag("related_party_transactions"),
            has_gst_mismatch=_flag("gst_mismatch"),
        )
        all_rag = (reg_chunks + sec_chunks + gov_chunks)[:5]
        rag_context = format_context_for_prompt(all_rag)
        logger.info("RAG: injected %d chunks into CAM narratives.", len(all_rag))
    except Exception as e:
        logger.warning("RAG retrieval for CAM skipped: %s", e)

    narratives = generate_cam_narratives(company_name, fin_summary, scoring_summary, rag_context)

    try:
        pdf_path = generate_cam_pdf(analysis_id, company_name, financials, scoring, narratives)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    try:
        update_cam_path(analysis_id, pdf_path)
    except Exception as e:
        logger.warning("Could not update CAM path: %s", e)

    return {
        "analysis_id": analysis_id,
        "download_url": f"/download-cam/{analysis_id}",
        "status": "ready",
    }


@app.get("/download-cam/{analysis_id}", tags=["CAM"])
def download_cam(analysis_id: str):
    analysis_id = _validate_uuid(analysis_id, "analysis_id")

    from database import get_analysis
    row = get_analysis(analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail="Analysis not found.")

    pdf_path = row.get("cam_pdf_path")
    if not pdf_path:
        raise HTTPException(status_code=404, detail="CAM not yet generated. POST /generate-cam/{id} first.")
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=410, detail="PDF no longer on disk.")

    company = _sanitise_company_name(row.get("company_name") or "report").replace(" ", "_")
    return FileResponse(pdf_path, media_type="application/pdf",
                        filename=f"CAM_{company}_{analysis_id[:8]}.pdf")


# ── RAG Chat ─────────────────────────────────────────────────────────────────

@app.post("/chat/{analysis_id}", tags=["RAG Chat"])
async def chat_endpoint(
    analysis_id: str,
    body: ChatRequest,
):
    analysis_id = _validate_uuid(analysis_id, "analysis_id")

    if not body.question or not body.question.strip():
        raise HTTPException(status_code=400, detail="'question' field is required.")
    if len(body.question) > 2000:
        raise HTTPException(status_code=400, detail="Question too long (max 2000 chars).")

    from database import get_analysis
    row = get_analysis(analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    try:
        analysis_data = {
            "company_name":          row["company_name"],
            "extracted_financials":  json.loads(row["extracted_financials"]),
            "scoring_result":        json.loads(row["scoring_result"]),
            "validation_warnings":   json.loads(row["validation_warnings"]),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis data corrupt: {e}")

    try:
        from chat_service import answer_question
        result = answer_question(
            question=body.question.strip(),
            analysis_data=analysis_data,
            conversation_history=body.conversation_history or [],
        )
        return {
            "analysis_id":     analysis_id,
            "question":        body.question,
            "answer":          result["answer"],
            "sources":         result["sources"],
            "rag_chunks_used": result["rag_chunks_used"],
        }
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=f"LLM unavailable: {e}")
    except Exception as e:
        logger.error("Chat endpoint error: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Chat error: {e}")


# ── RAG management endpoints ─────────────────────────────────────────────────

@app.get("/rag/status", tags=["RAG"])
def rag_status():
    try:
        from rag_engine import _get_chroma_collection
        col = _get_chroma_collection()
        count = col.count()
        return {
            "status": "ready" if count > 0 else "empty",
            "chunks_ingested": count,
            "embedding_model": "all-MiniLM-L6-v2",
            "vector_db": "ChromaDB (embedded)",
        }
    except Exception as e:
        return {"status": "unavailable", "error": str(e)}


@app.post("/rag/reingest", tags=["RAG"])
def rag_reingest():
    try:
        from rag_engine import ingest_knowledge_base
        count = ingest_knowledge_base(force_reingest=True)
        return {"status": "ok", "chunks_ingested": count}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/rag/search", tags=["RAG"])
def rag_search(q: str, n: int = 4, category: Optional[str] = None):
    if not q or len(q.strip()) < 3:
        raise HTTPException(status_code=400, detail="Query 'q' must be at least 3 chars.")
    try:
        from rag_engine import retrieve_context
        results = retrieve_context(q.strip(), n_results=min(n, 10), category_filter=category)
        return {"query": q, "results": results, "count": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Get single analysis ───────────────────────────────────────────────────────

@app.get("/analysis/{analysis_id}", tags=["Analysis"])
def get_analysis_endpoint(analysis_id: str):
    analysis_id = _validate_uuid(analysis_id, "analysis_id")

    from database import get_analysis
    row = get_analysis(analysis_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"Analysis '{analysis_id}' not found.")

    try:
        return {
            "analysis_id":          analysis_id,
            "company_name":         row["company_name"],
            "created_at":           row["created_at"],
            "extracted_financials": json.loads(row["extracted_financials"]),
            "scoring_result":       json.loads(row["scoring_result"]),
            "validation_warnings":  json.loads(row["validation_warnings"]),
            "has_cam":              bool(row.get("cam_pdf_path")),
            "timestamp":            row.get("created_at", datetime.utcnow().isoformat()) + "Z",
        }
    except (json.JSONDecodeError, KeyError) as e:
        raise HTTPException(status_code=500, detail=f"Stored data corrupt: {e}")






