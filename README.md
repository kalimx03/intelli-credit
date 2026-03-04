# Intelli-Credit
### AI-Powered Corporate Credit Decisioning · IIT Hackathon · Indian Banking

---

## Technologies Used

| What | Technology | Why we picked it |
|------|-----------|-----------------|
| **LLM** | Claude `claude-sonnet-4-20250514` via Anthropic API | Extracts JSON from PDFs, writes CAM narratives, answers chat questions |
| **Embeddings** | `sentence-transformers` — `all-MiniLM-L6-v2` | 22MB, runs on CPU, no API key, ~5ms per query |
| **Vector DB** | ChromaDB (embedded mode) | No separate server — just a folder on disk |
| **RAG** | ChromaDB + sentence-transformers | Retrieves real RBI/GST/MCA regulations before every LLM call |
| **Backend** | FastAPI (Python) | Async REST, auto OpenAPI docs at `/docs` |
| **Frontend** | Next.js 14 + TypeScript | Type-safe, SSR, deploys free on Vercel |
| **PDF Extract** | pdfplumber | Table-aware extraction |
| **PDF Generate** | ReportLab | Professional CAM PDF |
| **Scoring** | Pure Python (no LLM) | 100% deterministic — same inputs always same output |
| **DB** | SQLite | Simple, file-based, no setup |

---

## How RAG Works (plain English)

**The problem it solves:** Claude doesn't reliably "know" current RBI circulars,
GST reconciliation norms, or MCA filing deadlines. Instead of trusting its memory,
we store those documents ourselves and retrieve the relevant ones before each call.

```
INGESTION (runs once at startup — ~30 seconds):
  regulations.txt (20 RBI/GST/MCA/sector docs)
      ↓
  Split into doc chunks
      ↓
  all-MiniLM-L6-v2 converts each chunk to a 384-number vector
      ↓
  ChromaDB stores (id, text, vector) to ./chroma_db/ folder

RETRIEVAL (runs on every CAM generation + chat message — ~50ms):
  User question or financial summary
      ↓
  all-MiniLM-L6-v2 converts question to a 384-number vector
      ↓
  ChromaDB: "find the 4 stored vectors closest to this one"
  (using cosine similarity — closer = more relevant topic)
      ↓
  Top-4 regulation chunks returned as text
      ↓
  Injected into Claude's prompt as context
      ↓
  Claude answers citing actual regulations, not memory
```

**Where RAG is applied in this project:**
1. **CAM Narratives** — RBI/GST/sector context injected → Claude cites real norms
2. **Chatbot** — Every question retrieves relevant regulations before Claude answers
3. **Governance Flags** — GST mismatch/RPT/litigation each trigger targeted retrieval
4. **Historical Comparison** — Similar past credit decisions retrieved for context

---

## Architecture

```
PDF Upload
    │
    ▼
pdf_extractor.py      (pdfplumber · 20MB limit · 60-page cap · per-page isolation)
    │
    ▼
llm_service.py        (Claude extracts JSON: value + confidence + evidence per field)
    │                  (4-strategy JSON recovery: direct → fence strip → regex → brace scan)
    ▼
validation.py         (type coercion · range bounds · cross-field consistency · confidence flags)
    │
    ▼
scoring.py            (DETERMINISTIC Five Cs engine · LLM never touches scoring)
    │
    ▼
database.py           (SQLite persistence)
    │
    ├──► /generate-cam  → rag_engine.py → llm_service.py(+context) → cam_generator.py → PDF
    │
    └──► /chat/{id}     → rag_engine.py → chat_service.py → Claude → answer + sources
```

**Core principle: LLM extracts data and writes text. Rules make credit decisions.**

---

## Five Cs Scoring (Fully Deterministic)

| Pillar     | Weight | Key Inputs |
|------------|--------|------------|
| Character  | 25%    | Auditor qualification, litigation, RPTs, years in operation, promoter flags |
| Capacity   | 30%    | DSCR, ICR, EBITDA margin, PAT sign |
| Capital    | 20%    | D/E ratio, current ratio, net worth sign, contingent liabilities |
| Collateral | 15%    | LTV ratio (loan ÷ collateral), collateral type bonus/penalty |
| Conditions | 10%    | GST mismatch, MCA default, RBI risk, sector headwinds |

Decisions: **≥ 75 = Approve · 50–74 = Conditional · < 50 = Reject**

---

# DEPLOYMENT — FROM SCRATCH

> Target architecture: **Frontend → Vercel | Backend → AWS EC2 | ChromaDB → EC2 (folder) | Storage → S3 (optional)**

---

## STEP 0: What you need before starting

- [ ] A credit card (AWS requires it, won't charge in free tier)
- [ ] Your Anthropic API key — get it at https://console.anthropic.com → API Keys
- [ ] Git installed on your laptop — https://git-scm.com
- [ ] A GitHub account — https://github.com

---

## STEP 1: Get your Anthropic API Key

1. Go to **https://console.anthropic.com**
2. Sign up or log in
3. Left sidebar → **"API Keys"**
4. Click **"Create Key"** → name it `intelli-credit` → click Create
5. Copy the key — starts with `sk-ant-api03-...`
6. Paste it in Notepad immediately. **You only see it once.**

---

## STEP 2: Create AWS Account + Launch EC2

**Create account:**
1. Go to **https://aws.amazon.com** → "Create an AWS Account"
2. Fill in your details, add a credit card
3. Choose **"Basic support - Free"**

**Launch your server:**
1. Log into AWS → search **"EC2"** in the top bar → click it
2. Click the orange **"Launch Instance"** button
3. Fill in:
   - **Name:** `intelli-credit-backend`
   - **OS Image:** Ubuntu Server 22.04 LTS *(look for "Free tier eligible")*
   - **Instance type:** `t2.medium` *(2 vCPU, 4GB RAM — needed for sentence-transformers)*
   - **Key pair:** Click "Create new key pair"
     - Name: `intelli-credit-key`  
     - Type: RSA · Format: .pem  
     - Click "Create key pair" → your browser downloads the `.pem` file
     - **Do not lose this file. It's your password.**
4. **Network settings** (click "Edit"):
   - ✅ Allow SSH traffic from → "My IP"
   - ✅ Allow HTTP traffic from the internet
   - ✅ Allow HTTPS traffic from the internet
5. **Storage:** Change to **20 GB** (torch is large)
6. Click **"Launch Instance"**

**Open port 8000 for the API:**
1. Click your instance name → **Security** tab
2. Click the Security Group link (looks like `sg-0abc123...`)
3. Click **"Edit inbound rules"** → **"Add rule"**:
   - Type: Custom TCP · Port range: 8000 · Source: Anywhere-IPv4
4. Click **"Save rules"**

**Get your server's IP:**  
Click your instance → copy the **Public IPv4 address** (e.g. `54.234.12.34`)

---

## STEP 3: Connect to Your Server

Open Terminal (Mac/Linux) or Git Bash (Windows):

```bash
# First, protect the key file
chmod 400 ~/Downloads/intelli-credit-key.pem

# Connect (replace with YOUR IP)
ssh -i ~/Downloads/intelli-credit-key.pem ubuntu@54.234.12.34
```

You'll see a prompt like `ubuntu@ip-172-31-xx:~$` — you're inside the server.

---

## STEP 4: Install Python + Dependencies on Server

Run these commands on the server (copy-paste each block):

```bash
# Update package list
sudo apt update && sudo apt upgrade -y

# Install Python 3.11
sudo apt install -y python3.11 python3-pip python3.11-venv python3-dev

# Verify
python3 --version   # should print 3.11.x
pip3 --version
```

---

## STEP 5: Upload Your Backend Code

**On your laptop** — open a NEW terminal (keep the server one open):

```bash
# Navigate to your intelli-credit folder
cd path/to/intelli-credit

# Upload just the backend
scp -i ~/Downloads/intelli-credit-key.pem -r backend ubuntu@54.234.12.34:~/
```

**Back on the server terminal:**

```bash
# Go into backend folder
cd ~/backend

# Create isolated Python environment
python3 -m venv venv

# Activate it (you'll see "(venv)" in your prompt)
source venv/bin/activate

# Install packages
# IMPORTANT: torch (~500MB) takes 5-10 minutes to download
pip install -r requirements.txt
```

---

## STEP 6: Configure Your API Key

```bash
# Still inside ~/backend on the server
# Create the environment file
nano .env
```

Type this exactly (replace with your actual key):
```
CLAUDE_API_KEY=sk-ant-api03-YOUR-ACTUAL-KEY-HERE
DB_PATH=/home/ubuntu/backend/intelli_credit.db
CHROMA_PERSIST_DIR=/home/ubuntu/backend/chroma_db
```

Press **Ctrl+X** → **Y** → **Enter** to save.

---

## STEP 7: Test the Backend

```bash
# Inside ~/backend with (venv) active
uvicorn main:app --host 0.0.0.0 --port 8000
```

**First run output (this is normal):**
```
Loading embedding model 'all-MiniLM-L6-v2' (first run downloads ~22MB)...
Embedding model loaded.
Parsing: regulations.txt → 20 chunks
Ingestion complete — 20 chunks stored.
RAG knowledge base ready: 20 chunks.
Intelli-Credit API v2.0.0 started.
```

**Test in your browser:**
```
http://54.234.12.34:8000/health
```
You should see:
```json
{"status":"ok","claude_api_key_configured":true,"rag_ready":true}
```

Press **Ctrl+C** to stop.

---

## STEP 8: Run Backend Forever (Auto-restart on reboot)

```bash
# Create a system service
sudo nano /etc/systemd/system/intelli-credit.service
```

Paste this:
```ini
[Unit]
Description=Intelli-Credit FastAPI
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/backend
EnvironmentFile=/home/ubuntu/backend/.env
ExecStart=/home/ubuntu/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

**Ctrl+X → Y → Enter** to save.

```bash
# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable intelli-credit
sudo systemctl start intelli-credit

# Verify it's running
sudo systemctl status intelli-credit

# Watch live logs
sudo journalctl -u intelli-credit -f
# Press Ctrl+C to stop watching
```

---

## STEP 9: Deploy Frontend to Vercel

**Push code to GitHub:**

```bash
# On your laptop, inside the intelli-credit folder
git init
git add .
git commit -m "Intelli-Credit v2.0 with RAG"

# Create a repo at github.com, then:
git remote add origin https://github.com/YOUR_USERNAME/intelli-credit.git
git push -u origin main
```

**Deploy on Vercel:**

1. Go to **https://vercel.com** → Sign up with GitHub → click **"Continue with GitHub"**
2. Click **"Add New Project"**
3. Click **"Import"** next to your `intelli-credit` repo
4. **Configure:**
   - Framework Preset: **Next.js** (auto-detected)
   - Root Directory: click **Edit** → type `frontend`
5. **Environment Variables** → click **"Add"**:
   - Name: `NEXT_PUBLIC_API_URL`
   - Value: `http://54.234.12.34:8000` *(your EC2 IP)*
6. Click **"Deploy"**
7. Wait ~2 minutes → Vercel gives you: `https://intelli-credit-abc123.vercel.app`

**Done. Open the link and upload a PDF.**

---

## STEP 10: (Optional) S3 for PDF Storage

Right now, generated CAM PDFs are stored on the EC2 disk.
If the instance restarts, they're gone. S3 solves this.

```bash
pip install boto3
```

In AWS Console → **S3** → **Create bucket** → name it `intelli-credit-cams` → region `ap-south-1` → all other settings default → Create.

In AWS Console → **IAM** → Create user `intelli-credit-s3` → Attach policy `AmazonS3FullAccess` → Create access key → copy both keys.

Add to your `.env`:
```
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
S3_BUCKET=intelli-credit-cams
AWS_REGION=ap-south-1
```

Then in `cam_generator.py`, after `doc.build(story)`:
```python
import boto3, os
if os.environ.get("S3_BUCKET"):
    s3 = boto3.client("s3")
    s3.upload_file(filename, os.environ["S3_BUCKET"], f"cams/{os.path.basename(filename)}")
```

---

## Common Commands (Quick Reference)

```bash
# Check if backend is running
sudo systemctl status intelli-credit

# Restart after code changes
sudo systemctl restart intelli-credit

# See live logs
sudo journalctl -u intelli-credit -f

# Check RAG status
curl http://localhost:8000/rag/status

# Re-ingest after updating regulations.txt
curl -X POST http://localhost:8000/rag/reingest

# Test semantic search (shows what RAG retrieves)
curl "http://localhost:8000/rag/search?q=DSCR+norms+RBI"

# Health check
curl http://localhost:8000/health

# API docs (auto-generated by FastAPI)
# Open in browser: http://54.234.12.34:8000/docs
```

---

## Cost Estimate

| Service | Spec | Monthly Cost |
|---------|------|-------------|
| EC2 t2.medium | 2 vCPU, 4GB RAM | $0 (free tier 12 months) → ~$33/mo after |
| Vercel | Hobby plan | Free forever |
| Anthropic Claude | ~100 analyses | ~$5–15 |
| S3 | 1 GB PDFs | ~$0.02 |
| **Total** | | **~Free year 1, ~$40/mo after** |

---

## Demo Checklist

### Before presenting:
- [ ] `GET /health` → `"rag_ready": true, "claude_api_key_configured": true`
- [ ] `GET /rag/status` → `"chunks_ingested": 20`
- [ ] Upload a test PDF → analysis completes successfully
- [ ] Generate CAM → PDF downloads correctly
- [ ] Chat tab → ask "What does RBI say about DSCR?" → sources appear below answer

### Key things to explain to judges:
1. **LLM never scores** — scoring.py is pure deterministic Python
2. **RAG makes Claude cite real laws** — not hallucinated norms
3. **Evidence required** — Pydantic flags any non-null value without a document quote
4. **Every decision is auditable** — full rule log with triggered/not-triggered + impact
5. **Indian-specific** — GST 2A/3B mismatch, MCA filings, RBI NPA classification are all modelled
