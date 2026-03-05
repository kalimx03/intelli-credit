# Requirements

## Functional Requirements

### FR-1: Document Ingestion
- Accept PDF uploads up to 50MB
- Extract text from both digital and text-layer PDFs using pdfplumber
- Parse tables, financial statements, and free-form text in a single pass
- Support annual reports, ITR summaries, GST statements, and sanction letters

### FR-2: Financial Data Extraction
The system must extract and return structured data with confidence scores for:

**Financial Metrics**
- Revenue, EBITDA, PAT (Profit After Tax)
- Net worth, Total debt
- Current ratio, Debt/Equity ratio
- Interest Coverage Ratio (ICR), DSCR

**Compliance Signals**
- Auditor qualifications or adverse opinions
- GST 2A vs 3B mismatch flag
- MCA filing status (default or compliant)
- RBI regulatory risk or NPA classification
- Litigation pending flag
- Related party transaction flag
- Contingent liabilities

**Business Profile**
- Years in operation, Promoter experience
- Industry sector, Collateral value and type
- Loan amount requested

Every extracted field must carry: `value`, `confidence (0–1)`, `evidence (text snippet)`.

### FR-3: Anti-Hallucination Validation
- Fields with non-null values but empty evidence strings must be auto-flagged
- Confidence below 0.5 must trigger a validation warning visible to the user
- Scoring engine must never use LLM-generated numeric scores — only extracted field values

### FR-4: Five Cs Scoring Engine
- Must be fully deterministic — identical inputs always produce identical outputs
- Each rule trigger must log: rule name, category, impact value, explanation, raw value
- Weighted scoring: Character 25%, Capacity 30%, Capital 20%, Collateral 15%, Conditions 10%
- Output: final score, risk band, decision, suggested loan limit, suggested interest rate

### FR-5: Primary Insight Integration
- Credit officer must be able to input qualitative notes (max 2000 chars)
- System must parse notes into structured boolean flags:
  `promoter_concern`, `succession_risk`, `sector_headwind`, `regulatory_concern`, `concentration_risk`, `expansion_risk`, `positive_management`
- Flags must directly adjust the Five Cs Character and Conditions scores

### FR-6: CAM PDF Generation
The Credit Appraisal Memo must contain:
- Executive Summary with decision and score
- Company profile section
- Financial analysis with extracted metrics table
- Five Cs score breakdown with rule trigger log
- Compliance and GST review section
- Litigation and legal risk section
- Sector and macro conditions
- Justification narrative
- Validation warnings (data quality flags)

### FR-7: RAG Credit Chat
- Users must be able to ask natural language questions about any analysis
- System must retrieve relevant regulation chunks from the knowledge base
- Answers must cite specific financial figures from the analysis AND regulatory sources
- Conversation history (last 6 turns) must be maintained within a session

### FR-8: Analysis Persistence
- Each analysis must be stored with a unique UUID
- Results must be retrievable via analysis ID
- Dashboard must be shareable via URL

---

## Non-Functional Requirements

### NFR-1: Performance
- PDF extraction + LLM extraction: complete within 30 seconds for documents up to 10 pages
- Scoring engine: complete within 100ms (pure Python, no I/O)
- CAM PDF generation: complete within 10 seconds
- RAG retrieval: complete within 2 seconds

### NFR-2: Reliability
- LLM calls must retry up to 3 times with exponential backoff on transient failures
- If LLM extraction fails entirely, scoring must still run with null-safe defaults
- If RAG retrieval fails, CAM generation must fall back to template narratives
- System must never return a 500 error due to missing or malformed financial data

### NFR-3: Explainability
- Every credit decision must be accompanied by a human-readable rule trigger log
- Score impacts must be signed (positive/negative) with plain English explanations
- No decision field may be populated without a traceable computation path

### NFR-4: Indian Regulatory Context
- Knowledge base must cover: RBI IRACP norms, DSCR benchmarks, GST 2A/3B reconciliation, MCA ROC filing requirements, CIBIL commercial risk signals
- GST mismatch detection must reference GSTR-2A vs GSTR-3B reconciliation specifically
- Interest rate bands must align with Indian banking risk premium conventions

### NFR-5: Security
- API keys must never be committed to version control
- All keys must be injected via environment variables
- No sensitive financial data logged in application logs

### NFR-6: Deployment
- Frontend must be deployable to Vercel with zero configuration
- Backend must run as a systemd service on Ubuntu 22.04+
- Backend must be accessible over HTTP on port 8000
- All cross-origin requests must be proxied through the frontend (no direct EC2 exposure to browser)

---

## Data Requirements

### Input Schema (POST /analyze)
```
multipart/form-data:
  file              PDF file (required)
  company_name      string (required)
  loan_amount       float in INR (required)
  primary_insights  string (optional, max 2000 chars)
```

### Extracted Fields Schema
```json
{
  "field_name": {
    "value": <number | boolean | string | null>,
    "confidence": <float 0.0–1.0>,
    "evidence": "<source text from document>"
  }
}
```

### Scoring Output Schema
```json
{
  "five_cs": {
    "character": 85.0,
    "capacity": 72.5,
    "capital": 90.0,
    "collateral": 80.0,
    "conditions": 65.0,
    "weighted_total": 79.25
  },
  "final_score": 79.25,
  "risk_band": "Low Risk",
  "decision": "Approve",
  "suggested_loan_limit": 72000000,
  "suggested_interest_rate": 9.5,
  "rule_log": [
    {
      "rule_name": "DSCR Adequate (>=1.5)",
      "category": "capacity",
      "triggered": false,
      "impact": 0.0,
      "explanation": "DSCR of 1.8x is adequate.",
      "raw_value": 1.8
    }
  ]
}
```

---

## Constraints

- Must run on a single EC2 t3.medium instance (2 vCPU, 4GB RAM)
- Embedding model (all-MiniLM-L6-v2) must run on CPU — no GPU dependency
- ChromaDB must operate in embedded mode — no separate vector DB server
- Total backend cold-start time must be under 30 seconds
- LLM provider must support free-tier usage sufficient for hackathon demonstration
