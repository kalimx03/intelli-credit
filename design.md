# Design

## Guiding Principles

**1. Determinism over magic.**
Credit decisions carry real financial consequences. The scoring engine is pure, rule-based Python — no stochasticity, no LLM-generated scores. The same PDF always produces the same result. This is a deliberate architectural choice, not a limitation.

**2. LLM for extraction, not judgment.**
The LLM's job is to read unstructured text and produce structured data. Once data is extracted, all judgment happens in deterministic code. This creates a clean separation: improve extraction accuracy without touching decision logic, and vice versa.

**3. Explainability as a first-class feature.**
Every score impact is logged with its rule name, numeric impact, plain English explanation, and the raw value that triggered it. The Rule Log is not an afterthought — it is the primary output.

**4. Fail gracefully, always.**
A PDF with missing financials should still produce a partial analysis, not a 500 error. Every field access in the scoring engine goes through `safe_value()` which returns None on missing data. Downstream logic handles None without crashing.

---

## System Components

### 1. PDF Extractor (`pdf_extractor.py`)

Uses `pdfplumber` to extract text and table data from each page. Tables are converted to structured text before being passed to the LLM, preserving column relationships that would be lost in raw text extraction.

Output is a single concatenated string passed to the extraction prompt.

**Limitation acknowledged:** Scanned (image-only) PDFs are not currently supported. OCR integration (Tesseract or AWS Textract) is the identified next step.

---

### 2. LLM Extraction (`llm_service.py`)

The extraction prompt instructs the LLM to return a strict JSON object. Three JSON parsing strategies are attempted in sequence:
1. Direct `json.loads()`
2. Strip markdown code fences, retry parse
3. Regex extract first `{...}` block, retry parse

If all three fail, a null skeleton is returned and the analysis proceeds with low-confidence defaults.

Each call retries up to 5 times. Rate limit errors (HTTP 429) trigger a 30-second wait before retry.

**Why Groq/Llama over GPT-4?**
Groq provides ~10x lower latency on Llama-3.3-70b compared to GPT-4o at similar quality for structured extraction tasks. For a hackathon demo with real-time uploads, latency matters more than marginal quality improvements.

---

### 3. Validation Layer (`validation.py`)

Runs after extraction, before scoring. Checks:
- Confidence < 0.5 on critical fields (DSCR, revenue, net worth) → warning
- Non-null value with empty evidence → hallucination flag
- Numeric fields outside plausible ranges for Indian mid-market corporates

Warnings are surfaced in the dashboard and included in the CAM PDF. They do not block analysis — the credit officer makes the final call.

---

### 4. Five Cs Scoring Engine (`scoring.py`)

```
ExtractedFinancials + ManagementInsightFlags
            │
            ▼
    ┌───────────────┐
    │  score_character()  → 0–100, rule_log[]
    │  score_capacity()   → 0–100, rule_log[]
    │  score_capital()    → 0–100, rule_log[]
    │  score_collateral() → 0–100, rule_log[]
    │  score_conditions() → 0–100, rule_log[]
    └───────────────┘
            │
            ▼
    weighted_total = Σ(score × weight)
            │
            ▼
    decision + loan_limit + interest_rate
```

All five functions follow the same pattern:
- Start at 100
- Apply penalty rules (impact < 0) or bonus rules (impact > 0)
- Clamp result to [0, 100]
- Return score + full rule log

The loan limit formula: `revenue × multiplier(score_band)`. The multiplier is 0.40 / 0.25 / 0.10 for Low / Moderate / High risk respectively. This is a conservative Indian banking convention — not a global benchmark.

---

### 5. RAG Engine (`rag_engine.py`)

**Ingestion (once at startup):**
```
regulations.txt → split into ~500 char chunks with 50 char overlap
               → embed each chunk with all-MiniLM-L6-v2 (384-dim vector)
               → store in ChromaDB with metadata (title, category, source)
```

**Retrieval (per request):**
```
user query → embed with same model
          → cosine similarity search in ChromaDB
          → return top-4 chunks with relevance scores
          → format as numbered context block for LLM
```

**Why all-MiniLM-L6-v2?**
22MB model, runs on CPU in under 100ms, semantic quality sufficient for regulatory text retrieval. No API cost, no latency variance, no dependency on external embedding services.

**Knowledge base coverage:**
- RBI IRACP norms (income recognition, asset classification, provisioning)
- DSCR and ICR benchmarks for Indian corporate lending
- GST 2A vs 3B reconciliation and ITC fraud signals
- MCA ROC filing obligations and default consequences
- CIBIL commercial score interpretation
- Related party transaction risk signals
- Sector-specific credit benchmarks (manufacturing, services, NBFC)

---

### 6. CAM Generator (`cam_generator.py`)

Produces a structured PDF using ReportLab. The LLM writes narrative sections (executive summary, financial analysis, justification) with the regulatory context injected via RAG. All numeric tables (Five Cs scores, extracted metrics, rule log) are generated deterministically from the scoring output — the LLM does not touch numbers in the CAM.

**Section structure:**
1. Header — company name, date, decision badge
2. Executive Summary — LLM narrative
3. Five Cs Score Card — table with scores and weights
4. Financial Metrics — extracted values with confidence indicators
5. Rule Trigger Log — all triggered rules with impact values
6. Compliance Review — GST, MCA, RBI flags
7. Litigation & Legal Risk — LLM narrative
8. Sector Conditions — LLM narrative with RAG context
9. Justification — LLM decision rationale
10. Data Quality Warnings — hallucination flags and low-confidence fields

---

### 7. Chat Service (`chat_service.py`)

```
question
    │
    ├─ embed → ChromaDB → top-3 regulation chunks
    ├─ retrieve historical peer decisions for same sector/score band
    │
    ├─ build analysis summary (company metrics, Five Cs, triggered rules)
    │
    └─ Groq LLM call with:
          system: CHAT_SYSTEM_PROMPT (role + rules)
          context: analysis summary + regulation chunks
          history: last 6 conversation turns
          question: current user input
```

The chat does not have access to the raw PDF text — only the structured analysis output. This prevents hallucination from ambiguous source material and forces answers to be grounded in verified extracted data.

---

## Frontend Architecture

```
app/
├── page.tsx          Upload form — PDF + company details + management notes
│                     Submits multipart/form-data to /api/proxy/analyze
│
├── dashboard/
│   └── page.tsx      Fetches analysis by UUID from URL params
│                     Four tabs: Overview · Metrics · Rules · Warnings
│                     Download CAM button → /api/proxy/cam/{id}
│
├── chat/
│   └── page.tsx      Maintains local conversation history state
│                     Posts to /api/proxy/chat/{analysis_id}
│                     Renders RAG source chips below each response
│
└── api/proxy/
    └── route.ts      Next.js edge route — proxies all requests to EC2
                      Preserves Content-Type header for JSON vs multipart
                      Handles binary response (PDF download) separately
```

**Why the proxy?**
The EC2 backend runs HTTP. Browsers block mixed-content (HTTPS page → HTTP API). The Next.js proxy runs server-side on Vercel (HTTPS) and forwards to EC2 over HTTP — no browser restriction applies.

---

## Data Flow: End-to-End

```
1. User uploads sharma_financial.pdf
   POST /api/proxy/analyze (multipart)

2. Proxy forwards to EC2:8000/analyze

3. Backend:
   a. pdfplumber extracts 1,625 chars of text
   b. Groq Llama-3.3 extracts 22 financial fields (JSON)
   c. Validation layer checks confidence and evidence
   d. Management insights parsed into 7 boolean flags
   e. Five Cs engine runs 28 rules, produces scores
   f. Loan limit and interest rate computed
   g. RAG retrieves 4 regulation chunks for CAM
   h. LLM writes 7 narrative sections
   i. ReportLab generates CAM PDF
   j. Result stored in SQLite with UUID

4. Response: AnalysisResponse JSON → frontend

5. Frontend redirects to /dashboard?id={uuid}
   Renders: score card, metrics table, rule log, warnings

6. User clicks AI Chat:
   POST /chat/{uuid} {"question": "...", "history": [...]}
   → RAG retrieval + Groq → answer with regulation citations
```

---

## Known Limitations and Next Steps

| Limitation | Identified Solution |
|-----------|-------------------|
| No OCR for scanned PDFs | Integrate AWS Textract or Tesseract |
| Web search not reliable in current setup | Implement Serper API or Tavily for news retrieval |
| GST cross-verification is flag-based, not quantitative | Ingest actual GSTR-2A/3B data via GST API |
| Single-file PDF only | Add multi-document upload (bank statements + ITR + annual report) |
| SQLite not production-grade | Migrate to PostgreSQL for concurrent access |
| No authentication | Add JWT-based auth for production deployment |
