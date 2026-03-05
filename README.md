![WhatsApp Image 2026-03-06 at 12 51 41 AM](https://github.com/user-attachments/assets/eafcf8aa-4a5f-485d-8316-2f51e383e0a7)
# Intelli-Credit

**AI-powered corporate credit decisioning engine for Indian banking.**

Upload a financial PDF. Get a structured, explainable credit decision in under 60 seconds — grounded in RBI, GST, and MCA regulations.

🔗 **Live Demo:** [intelli-credit.vercel.app](https://intelli-credit.vercel.app)

---

## The Problem

A mid-sized Indian corporate loan application requires stitching together GST filings, ITRs, annual reports, MCA filings, legal records, and management assessments. The current process takes 2–3 weeks, is prone to human bias, and routinely misses early warning signals buried in unstructured documents.

## The Solution

Intelli-Credit automates the end-to-end Credit Appraisal Memo (CAM) pipeline:

```
PDF Upload  →  LLM Extraction  →  Deterministic Five Cs Scoring  →  CAM PDF  →  RAG Chat
```

Every decision is **fully traceable** — not a black box. Each score impact is logged with the exact rule that triggered it.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND (Next.js 14)                        │
│   Upload Portal  ·  Results Dashboard  ·  AI Chat Interface          │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS (Vercel Proxy)
┌───────────────────────────────▼─────────────────────────────────────┐
│                       BACKEND (FastAPI / EC2)                        │
│                                                                       │
│  ┌─────────────┐    ┌──────────────────┐    ┌────────────────────┐  │
│  │ PDF Extract │    │  LLM Extraction  │    │  Scoring Engine    │  │
│  │ pdfplumber  │───▶│  Groq Llama-3.3  │───▶│  Five Cs Rules     │  │
│  └─────────────┘    └──────────────────┘    └─────────┬──────────┘  │
│                                                        │              │
│  ┌─────────────────────────────────────────┐          │              │
│  │           RAG Engine                    │          │              │
│  │  ChromaDB  ·  all-MiniLM-L6-v2          │◀─────────┘              │
│  │  30 regulation chunks: RBI/GST/MCA      │                         │
│  └──────────────────┬──────────────────────┘                         │
│                     │                                                 │
│  ┌──────────────────▼──────────────────────┐                         │
│  │         CAM Generator (ReportLab)        │                         │
│  │  Narrative + Metrics + Rule Log → PDF    │                         │
│  └─────────────────────────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Five Cs Scoring Engine

The scoring model is fully deterministic — no LLM randomness in the decision logic.

| Pillar | Weight | Key Signals |
|--------|--------|-------------|
| **Character** | 25% | Auditor qualifications · Litigation · Related party transactions · Years in operation · Promoter flags |
| **Capacity** | 30% | DSCR · Interest Coverage Ratio · EBITDA margin · PAT |
| **Capital** | 20% | Debt/Equity ratio · Current ratio · Net worth · Contingent liabilities |
| **Collateral** | 15% | LTV ratio · Collateral type (immovable vs current assets) |
| **Conditions** | 10% | GST 2A/3B mismatch · RBI regulatory risk · MCA filing default · Sector headwinds |

**Decision bands:**
- Score ≥ 75 → **Approve** · Loan limit = 40% of revenue · Rate from 8.5% p.a.
- Score 50–74 → **Conditional Approval** · Loan limit = 25% of revenue · Rate from 10.5% p.a.
- Score < 50 → **Reject** · Loan limit = 10% of revenue · Rate from 13.5% p.a.

---

## Key Design Decisions

**Anti-hallucination:** Every extracted field carries a confidence score and evidence string. Fields with non-null values but no evidence are automatically flagged for human review. The scoring engine runs on extracted data — never on LLM-generated scores.

**Deterministic scoring:** The Five Cs engine is pure Python with no LLM calls. The same inputs always produce the same output. Judges can audit every rule trigger in the Rule Log tab.

**Indian regulatory context:** The RAG knowledge base contains RBI IRACP norms, GST 2A vs 3B reconciliation guidelines, MCA ROC filing requirements, CIBIL commercial risk signals, and sector-specific credit benchmarks — retrieved semantically for each analysis.

**Primary insight integration:** Credit officers can enter qualitative observations (e.g., "Factory operating at 40% capacity"). These are parsed by the LLM into structured flags (sector_headwind, promoter_concern, etc.) that directly adjust the Five Cs scores.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14, TypeScript |
| Backend | FastAPI, Python 3.12 |
| LLM | Groq API — Llama-3.3-70b-versatile |
| Embeddings | sentence-transformers/all-MiniLM-L6-v2 |
| Vector DB | ChromaDB (embedded, no server) |
| PDF Parsing | pdfplumber |
| CAM Generation | ReportLab |
| Database | SQLite + SQLAlchemy |
| Deployment | Vercel (frontend) · AWS EC2 t3.medium (backend) |

---

## Local Setup

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY=your_key_here
uvicorn main:app --reload --port 8000

# Frontend
cd frontend
npm install
echo 'NEXT_PUBLIC_API_URL=/api/proxy' > .env.local
npm run dev
```

The backend initialises ChromaDB and ingests the regulation knowledge base on first startup. No separate vector DB server needed.

---

## Project Structure

```
intelli-credit/
├── backend/
│   ├── main.py              # FastAPI routes and orchestration
│   ├── llm_service.py       # Groq LLM calls with retry logic
│   ├── chat_service.py      # RAG-powered Q&A pipeline
│   ├── scoring.py           # Deterministic Five Cs engine
│   ├── rag_engine.py        # ChromaDB ingestion and retrieval
│   ├── cam_generator.py     # CAM PDF generation (ReportLab)
│   ├── pdf_extractor.py     # PDF text and table extraction
│   ├── validation.py        # Anti-hallucination validation layer
│   ├── models.py            # Pydantic data models
│   ├── prompts.py           # LLM prompt templates
│   └── knowledge_base/
│       └── regulations.txt  # RBI/GST/MCA regulation corpus
└── frontend/
    ├── app/
    │   ├── page.tsx          # Upload and submission portal
    │   ├── dashboard/        # Results: Overview, Metrics, Rules, Warnings
    │   ├── chat/             # AI credit analyst chat
    │   └── api/proxy/        # Next.js → EC2 proxy (HTTPS→HTTP)
    └── lib/
        └── api.ts            # Axios API client
```

---

## Built for

**IIT Hyderabad — Intelli-Credit Hackathon**
*Next-Gen Corporate Credit Appraisal: Bridging the Intelligence Gap*
