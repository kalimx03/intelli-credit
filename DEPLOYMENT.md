# Intelli-Credit — Complete Deployment Guide
## From Zero to Live in 4 Steps

---

## Technology Stack (What We Used and Why)

### LLM — Claude (Anthropic)
**Model:** `claude-sonnet-4-20250514`  
**Used for:** Extracting structured financial data from raw PDF text, generating CAM narrative sections, answering analyst questions in the chatbot.  
**Why Claude:** Function-grade JSON output reliability, 200K context window (handles large financial PDFs), strong Indian regulatory knowledge in training.

### RAG Stack — Sentence Transformers + ChromaDB
**Embedding model:** `all-MiniLM-L6-v2` (22 MB, runs on CPU, no GPU needed)  
**Vector database:** ChromaDB (embedded mode — just a folder on disk, no separate server)  
**Knowledge base:** 30 regulation chunks covering RBI norms, GST rules, MCA compliance, sector intelligence, and historical credit decisions  

**RAG is applied in 4 places:**
1. **CAM Narrative Generation** — regulatory context injected into each narrative section
2. **Chatbot Q&A** — every question retrieves top-4 relevant regulation chunks before Claude answers
3. **Governance Risk Context** — GST mismatch / RPT / litigation flags trigger targeted retrieval
4. **Historical Peer Comparison** — similar past credit decisions retrieved for benchmarking

**How RAG works in plain English:**
```
Analyst asks: "Why is the DSCR of 1.1x a problem?"
       ↓
We convert "DSCR 1.1x problem" → a 384-number vector
       ↓
ChromaDB finds the 4 most similar stored vectors:
  → "RBI DSCR Norms" (95% similar)
  → "RBI NPA Classification" (87% similar)
  → "Historical Rejected Cases" (82% similar)
  → "Tandon Committee Working Capital Norms" (76% similar)
       ↓
Claude receives: analysis data + those 4 regulation chunks + the question
       ↓
Claude answers: "As per RBI circular DBOD.BP.BC.No.110, DSCR below 1.25x..."
       ↓
Answer cites real regulations — not Claude's memory
```

### Backend — FastAPI (Python)
Deterministic Five Cs scoring engine. LLM only extracts data and writes narratives. All credit decisions are pure Python rule logic — reproducible, auditable, zero hallucination.

### Frontend — Next.js 14 (React + TypeScript)
Upload page, results dashboard with Five Cs visualisation, embedded RAG chatbot, CAM PDF generation.

### Database — SQLite (dev) / PostgreSQL (prod)
Stores analyses with full audit trail. In production, swap `database.py` to use PostgreSQL.

### PDF Generation — ReportLab
Generates professional bank-grade CAM PDFs entirely server-side. No external dependencies.

---

## Deployment Architecture

```
Internet
   │
   ├── Frontend ──────────────── Vercel (Free)
   │   next.js app               Auto-deploys from GitHub
   │   NEXT_PUBLIC_API_URL ─────────────────────────────┐
   │                                                     │
   └── Backend + RAG + DB ───── AWS EC2 (t3.medium)      │
       FastAPI on port 8000 ◄───────────────────────────┘
       ChromaDB on disk
       SQLite database
       sentence-transformers (CPU)
       
       ↕ S3 (optional)
       CAM PDFs stored in S3 bucket
       Presigned URLs for download
```

**Cost estimate:** ~$30/month (EC2 t3.medium $0.0416/hr)  
**Vercel:** Free forever for this traffic level  
**S3:** ~$0.02/GB/month — negligible for PDF storage  

---

## Step-by-Step Deployment

---

## STEP 1 — Get Your Anthropic API Key

1. Go to **https://console.anthropic.com**
2. Sign up / log in
3. Click **"API Keys"** in the left sidebar
4. Click **"Create Key"** → name it "intelli-credit"
5. Copy the key — it looks like `sk-ant-api03-XXXX...`
6. **Save it somewhere safe** — you'll need it in Step 3

---

## STEP 2 — Launch an EC2 Instance (Backend Server)

### 2a. Create AWS Account
Go to **https://aws.amazon.com** → Create account → Add credit card (you get 750 hours free for 12 months)

### 2b. Launch Instance
1. Go to **EC2 Dashboard** → **"Launch Instance"**
2. Settings:
   - **Name:** `intelli-credit-backend`
   - **OS:** Ubuntu 22.04 LTS (the orange one)
   - **Instance type:** `t3.medium` (2 CPU, 4 GB RAM — needed for sentence-transformers)
   - **Key pair:** Click "Create new key pair" → name it `intelli-credit-key` → Download the `.pem` file to your computer
   - **Network:** Allow SSH (port 22), HTTP (port 80), Custom TCP port 8000 (from anywhere 0.0.0.0/0)
3. Click **"Launch Instance"**
4. Wait 2 minutes for it to start
5. Copy the **Public IPv4 address** (looks like `54.xxx.xxx.xxx`)

### 2c. Connect to EC2
**On Mac/Linux:**
```bash
chmod 400 ~/Downloads/intelli-credit-key.pem
ssh -i ~/Downloads/intelli-credit-key.pem ubuntu@YOUR_EC2_IP
```

**On Windows:** Use PuTTY or Windows Terminal with WSL

You should now see `ubuntu@ip-xxx:~$` — you're inside the server.

### 2d. Install Everything on EC2
```bash
# Update the server
sudo apt update && sudo apt upgrade -y

# Install Python and pip
sudo apt install -y python3-pip python3-venv git

# Upload your project files to EC2
# (Do this from your LOCAL computer, not the EC2 terminal)
# Open a NEW terminal on your computer and run:
scp -i ~/Downloads/intelli-credit-key.pem -r ./intelli-credit ubuntu@YOUR_EC2_IP:~/
# Then go back to the EC2 terminal

# Go into the project
cd ~/intelli-credit/backend

# Create a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install all Python packages
# This will take 3-5 minutes (sentence-transformers downloads the embedding model)
pip install -r requirements.txt

# Set your environment variables
export CLAUDE_API_KEY="sk-ant-api03-PASTE-YOUR-KEY-HERE"
export DB_PATH="/home/ubuntu/intelli-credit/intelli_credit.db"

# Test the server starts (you should see "Uvicorn running on http://0.0.0.0:8000")
uvicorn main:app --host 0.0.0.0 --port 8000
# Press Ctrl+C to stop
```

### 2e. Run Backend Permanently (Systemd Service)
```bash
# Create the service file
sudo nano /etc/systemd/system/intelli-credit.service
```

Paste this into the file (replace YOUR_EC2_IP and YOUR_API_KEY):
```ini
[Unit]
Description=Intelli-Credit FastAPI Backend
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/intelli-credit/backend
Environment="CLAUDE_API_KEY=sk-ant-api03-YOUR-KEY-HERE"
Environment="DB_PATH=/home/ubuntu/intelli-credit/intelli_credit.db"
Environment="CHROMA_PERSIST_DIR=/home/ubuntu/intelli-credit/chroma_db"
ExecStart=/home/ubuntu/intelli-credit/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Save with `Ctrl+X`, then `Y`, then Enter.

```bash
# Enable and start the service
sudo systemctl daemon-reload
sudo systemctl enable intelli-credit
sudo systemctl start intelli-credit

# Check it's running
sudo systemctl status intelli-credit
# Should say "active (running)"

# Test it works
curl http://localhost:8000/health
# Should return {"status":"ok","claude_api_key_configured":true}
```

Your backend is now live at: `http://YOUR_EC2_IP:8000`

Test in browser: `http://YOUR_EC2_IP:8000/docs` (Swagger UI)

---

## STEP 3 — Deploy Frontend to Vercel

### 3a. Push to GitHub
On your LOCAL computer:
```bash
# If you don't have git set up:
git init
git add .
git commit -m "Initial commit"

# Create a new repo on github.com then:
git remote add origin https://github.com/YOURUSERNAME/intelli-credit.git
git push -u origin main
```

### 3b. Deploy on Vercel
1. Go to **https://vercel.com** → Sign up with GitHub
2. Click **"New Project"**
3. Click **"Import"** next to your `intelli-credit` repo
4. Settings:
   - **Framework Preset:** Next.js (auto-detected)
   - **Root Directory:** `frontend`
   - **Environment Variables:** Add this:
     - Key: `NEXT_PUBLIC_API_URL`
     - Value: `http://YOUR_EC2_IP:8000`
5. Click **"Deploy"**
6. Wait ~2 minutes
7. Vercel gives you a URL like `https://intelli-credit-xyz.vercel.app`

**Your app is live!** Open the Vercel URL in your browser.

---

## STEP 4 — (Optional) Set Up S3 for PDF Storage

By default, CAM PDFs are stored on EC2 disk. For production, store them on S3:

### 4a. Create S3 Bucket
1. Go to **AWS S3** → **Create bucket**
2. Name: `intelli-credit-cams-YOURNAME` (must be globally unique)
3. Region: same as your EC2 (e.g. `ap-south-1` for India)
4. Uncheck "Block all public access" → acknowledge warning
5. Click Create

### 4b. Create IAM User for S3 Access
1. Go to **IAM** → **Users** → **Create User**
2. Name: `intelli-credit-s3`
3. Attach policy: `AmazonS3FullAccess`
4. Create user → **Security credentials** → **Create access key**
5. Copy **Access Key ID** and **Secret Access Key**

### 4c. Add to EC2 Environment
```bash
sudo nano /etc/systemd/system/intelli-credit.service
# Add these lines in [Service] section:
Environment="AWS_ACCESS_KEY_ID=YOUR_ACCESS_KEY"
Environment="AWS_SECRET_ACCESS_KEY=YOUR_SECRET_KEY"
Environment="S3_BUCKET=intelli-credit-cams-YOURNAME"
Environment="AWS_REGION=ap-south-1"

sudo systemctl daemon-reload && sudo systemctl restart intelli-credit
```

---

## Verify Everything Works

### Checklist
- [ ] `http://YOUR_EC2_IP:8000/health` returns `{"status":"ok"}`
- [ ] `http://YOUR_EC2_IP:8000/rag/status` shows chunks > 0
- [ ] Vercel frontend loads without errors
- [ ] Upload a test PDF → analysis runs → scores appear
- [ ] Click "AI Analyst Chat" → ask a question → get answer with regulation sources
- [ ] Click "Generate CAM PDF" → PDF downloads

### If Something Breaks

**Backend not starting:**
```bash
sudo journalctl -u intelli-credit -n 50
# Shows last 50 lines of error logs
```

**CLAUDE_API_KEY error:**
```bash
sudo systemctl edit intelli-credit --force
# Re-enter the Environment line with the correct key
sudo systemctl restart intelli-credit
```

**RAG not working:**
```bash
curl http://YOUR_EC2_IP:8000/rag/status
# If chunks=0, run:
curl -X POST http://YOUR_EC2_IP:8000/rag/reingest
```

**Frontend can't reach backend:**
- Check EC2 Security Group allows port 8000 from 0.0.0.0/0
- Check `NEXT_PUBLIC_API_URL` in Vercel settings has no trailing slash
- Redeploy Vercel after changing env vars

---

## Estimated Costs

| Service | Plan | Cost |
|---------|------|------|
| EC2 t3.medium | ~730 hrs/month | ~$30/month |
| Vercel | Hobby (free) | $0 |
| S3 storage | Pay per use | ~$0.50/month |
| Claude API | Pay per use | ~$0.005 per analysis |
| **Total** | | **~$31/month** |

---

## How to Add More Regulations to the Knowledge Base

1. Open `backend/knowledge_base/regulations.txt`
2. Add a new doc block:
```
---
DOC_ID: YOUR_DOC_ID_001
CATEGORY: rbi_guidelines
TITLE: Your Regulation Title
---
Full regulation text here. Be specific and include circular numbers,
thresholds, and exact requirements. Each chunk should be self-contained.
```
3. Re-ingest: `curl -X POST http://YOUR_EC2_IP:8000/rag/reingest`
4. Done — ChromaDB now includes your new regulation

Categories: `rbi_guidelines`, `gst_regulations`, `mca_regulations`, `credit_norms`, `governance`, `fraud_prevention`, `sector_intelligence`, `historical_decisions`
