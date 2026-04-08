# NewsContext AI  
**You read the headline. We tell you what it costs you.**

A multi-agent system built on **Google ADK** that translates any news headline into your exact **personal rupee impact** — based on your **home loan, investments, sector, and income**.

**Not summaries. Not generic advice. Your numbers.**

**Live demo:** https://actual-context-agent-922478641246.us-central1.run.app

---

## Demo

Paste any headline:

> RBI cuts repo rate by 25 bps

Get:

### 💰 YOUR PERSONAL IMPACT

**Harman, here's what this means for your wallet:**

- **🏠 Home Loan:**
  - Old EMI: ₹43,391 → New EMI: ₹42,603  
  - You save **₹788/month = ₹9,456/year**

- **📈 Investments (equity MF):**
  - Portfolio: ₹800,000 → Estimated change: **₹8,000 (positive)**

- **💼 Your Sector (IT):**
  - Lower rates boost tech hiring and client budgets.

- **🛢️ Daily Life:**
  - FD/savings account rates will drop slightly.

- **🧠 WHY:**
  - Repo rate cut reduces bank borrowing costs, transmitted to home loans in **1–3 months**.

- **⏳ WHEN:** 1 month  
- **💡 DO NOW:** Consider prepaying ₹50,000 of principal.

Works for any news — **RBI rates, Middle East war, India–UK FTA, oil prices, US recession**.

---

## Architecture

```text
User
  ↓
Orchestrator Agent  (Google ADK — state machine)
  ├── Profile Agent    →  collect / load user profile  →  Firestore
  ├── News Pipeline    →  validate (RBI/SEBI/PIB/Mint RSS) + causal chain
  └── Impact Agent     →  EMI math + MF impact + personalised output
                                    ↓
                          Google Firestore
                     profiles · events · impacts
```

---

## Tech stack

| Component | Technology |
|---|---|
| Agent orchestration | Google ADK 1.14 |
| LLM | Gemini 2.5 Flash |
| Database | Google Firestore |
| Deployment | Cloud Run |
| News validation | RSS — RBI, SEBI, PIB, The Hindu, Mint |
| Financial math | Python (deterministic, not LLM) |

---

## Setup

### Prerequisites
- Google Cloud account with billing enabled
- Python 3.12+
- `uv` installed
- Gemini API key from `aistudio.google.com`

### 1) Clone
```bash
git clone https://github.com/kaur-harman/actual-context.git
cd actual-context
```

### 2) Install dependencies
```bash
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 3) GCP setup
```bash
export PROJECT_ID=your_project_id
gcloud config set project $PROJECT_ID

# Enable APIs
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com

# Create Firestore database
gcloud firestore databases create \
  --location=asia-south1 \
  --type=firestore-native

# Create service account
export SA_NAME="news-agent-sa"
export SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts create $SA_NAME \
  --display-name="News Agent SA"

for ROLE in roles/aiplatform.user roles/run.invoker roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding $PROJECT_ID \
    --member="serviceAccount:$SA_EMAIL" \
    --role="$ROLE"
done
```

### 4) Configure environment
```bash
cp .env.example .env
```

Fill in `.env`:

```env
GOOGLE_API_KEY=your_key_from_aistudio
MODEL=gemini-2.5-flash
GOOGLE_GENAI_USE_VERTEXAI=0
PROJECT_ID=your_project_id
GOOGLE_CLOUD_PROJECT=your_project_id
```

### 5) Run locally
```bash
source .venv/bin/activate
adk web --allow_origins 'regex:https://.*\.cloudshell\.dev'
```

Open **Web Preview → port 8000**.

### 6) Deploy to Cloud Run
```bash
export GOOGLE_API_KEY=$(grep GOOGLE_API_KEY .env | cut -d= -f2 | tr -d ' ')
export MODEL=$(grep ^MODEL .env | cut -d= -f2 | tr -d ' ')
export SA_EMAIL="news-agent-sa@${PROJECT_ID}.iam.gserviceaccount.com"

uvx --from google-adk==1.14.0 adk deploy cloud_run \
  --project=$PROJECT_ID \
  --region=us-central1 \
  --service_name=actual-context-agent \
  --with_ui \
  . \
  -- \
  --service-account=$SA_EMAIL \
  --set-env-vars="GOOGLE_API_KEY=${GOOGLE_API_KEY},MODEL=${MODEL},GOOGLE_GENAI_USE_VERTEXAI=0,PROJECT_ID=${PROJECT_ID},GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" \
  --allow-unauthenticated
```

---

## Usage
1. Open the app
2. Type **new** → fill in your profile once (name, income, loan, MF, sector)
3. Save your **User ID** — paste it next time to skip setup
4. Paste any news headline
5. Get your personalised **₹ impact**

---

## Supported news types

| Category | Examples |
|---|---|
| Monetary policy | RBI repo rate, MPC decisions, inflation data |
| Geopolitical | Middle East war, Russia–Ukraine, border tensions |
| Commodity | Oil prices, gold, wheat, natural gas |
| Trade | FTA deals, tariffs, export/import bans |
| Budget | Union budget, tax slab changes, GST updates |
| Global macro | US recession fears, Fed rate changes, dollar index |
