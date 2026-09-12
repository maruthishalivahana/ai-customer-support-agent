# AI Customer Support Agent

> **Evidence-grounded AI agent for first-line AppleSupport Twitter/X customer support.**

---

## 1. Overview

When a customer posts a support request on Twitter/X, this system acts as an evidence-grounded first-line triage assistant. The agent reconstructs the conversation context, predicts the customer's intent across a 12-class canonical taxonomy, and retrieves relevant historical AppleSupport interactions using dense FAISS vector search and lexical TF-IDF. A deterministic decision engine then routes the inquiry to `AUTO_HANDLE`, `CLARIFY`, or `ESCALATE` based on multi-turn dialogue context, customer frustration, repeated troubleshooting history, and retrieval confidence. If automated handling is safe, If automated handling is safe, the agent asks an OpenRouter LLM to synthesize a natural-language response from retrieved historical AppleSupport cases,
with explicit grounding constraints and deterministic fallback handling. using OpenRouter. Crucially, the system is designed to avoid unsupported answers and premature autonomous actions; it is an experimental decision-support prototype rather than an unattended, production-ready autonomous system.

---

## 2. Product Flow

```
                Customer Tweet
                      │
                      ▼
             Conversation Context
                      │
                      ▼
            Intent Classification
                      │
                      ▼
               Hybrid Retrieval
                      │
                      ▼
             Historical Evidence
                      │
                      ▼
               Decision Engine
         ┌────────────┼────────────┐
         ▼            ▼            ▼
    AUTO_HANDLE    CLARIFY      ESCALATE
         │            │            │
         ▼            ▼            ▼
   Grounded Reply  Targeted Q   Specialist Handoff
```

---

## 3. Key Features

- **Conversation-Aware Multi-Turn Support**: Extracts unified dialogue context across customer and assistant turns rather than treating utterances in isolation.
- **12-Class Intent Classification**: Predicts customer problem categories with confidence scores.
- **Hybrid Retrieval System**: Combines a fast lexical TF-IDF baseline with dense semantic vector search.
- **FAISS Vector Index**: Local vector search powered by `sentence-transformers/all-MiniLM-L6-v2` embeddings over 22,738 preprocessed support cases.
- **Historical Evidence Grounding**: Constrains response synthesis strictly to retrieved historical interactions to eliminate ungrounded advice.
- **Conservative Three-Way Decision Policy**: Deterministically assigns `AUTO_HANDLE`, `CLARIFY`, or `ESCALATE`.
- **Repeated Troubleshooting Detection**: Recognizes when customers report prior failed attempts (e.g., *"tried that"*, *"still having problems"*).
- **Frustration & Sentiment Signal Detection**: Identifies angry emoji (`😡`, `😤`), aggressive punctuation, and exasperated phrasing.
- **Resolved / Closing Conversation Detection**: Gracefully closes interactions when users express resolution or gratitude without over-escalating.
- **Grounded LLM Response Generation**: OpenRouter-compatible generation with prompt hardening and Twitter handle/URL sanitization.
- **Automated Golden Set Evaluation**: Rigorous evaluation harness over 200 human-reviewed conversations.
- **LLM-as-a-Judge Evaluation**: 5-dimension automated response auditing (Correctness, Groundedness, Helpfulness, Relevance, Action Appropriateness).
- **Human-vs-LLM Evidence Audit**: 50-example empirical audit uncovering LLM judge overestimation.
- **Before/After Safety Benchmarking**: Empirical before/after benchmark measuring false-positive escalations and unsafe auto-handles.

---

## 4. Architecture & Tech Stack

| Layer | Technology | Purpose |
| :--- | :--- | :--- |
| **Backend** | Python 3.12, FastAPI, Pydantic v2, PyMongo | High-performance REST API, strict request/response validation, MongoDB driver |
| **Database** | MongoDB Atlas / Local MongoDB | Storage and indexing for historical customer cases and conversation paths |
| **ML & Retrieval** | scikit-learn, SentenceTransformers, FAISS | TF-IDF vectorization, Logistic Regression, 384d dense embeddings, IndexFlatIP |
| **LLM Generation** | OpenRouter (OpenAI-compatible client) | Controlled grounded response synthesis with zero-temperature / low-temperature settings |
| **Testing** | pytest, pytest-asyncio, mongomock | Full unit and integration test suite (108 tests) |
| **Frontend** | React, Vite, Tailwind CSS, Axios | Interactive customer support dashboard and evaluation viewer |

---

## 5. Project Structure

```
ai-customer-support-agent/
├── backend/
│   ├── main.py                  # FastAPI application entrypoint and route definitions
│   ├── requirements.txt         # Pinned Python backend dependencies
│   ├── .env.example             # Template for required environment variables
│   ├── src/
│   │   ├── agent.py             # SupportDecisionAgent orchestrator
│   │   ├── classifier.py        # TF-IDF + Logistic Regression 12-class classifier
│   │   ├── config.py            # Centralized Pydantic application settings
│   │   ├── conversation.py      # Multi-turn conversation state representation
│   │   ├── embeddings.py        # SentenceTransformer embedding wrapper with L2 norm
│   │   ├── escalation.py        # Interpretable multi-signal decision engine
│   │   ├── generator.py         # Grounded LLM response generator with OpenRouter
│   │   ├── intents.py           # 12 canonical intent definitions and label mappings
│   │   ├── preprocessing.py     # Text cleaning, case extraction, Golden Set filtering
│   │   ├── retriever.py         # TFIDFRetriever and SemanticFAISSRetriever
│   │   ├── schemas.py           # Pydantic schemas for requests, responses, and signals
│   │   └── database/
│   │       ├── mongodb.py       # MongoDB client lifecycle and index initialization
│   │       ├── models.py        # Database document models
│   │       └── repositories.py  # CRUD repositories for cases and predictions
│   ├── models/                  # Pre-built model and index artifacts
│   │   ├── intent_classifier.joblib       # Trained supervised intent classifier
│   │   ├── tfidf_retriever.joblib         # Fitted TF-IDF lexical index
│   │   ├── semantic_faiss.index           # Persisted FAISS vector index (22,738 cases)
│   │   ├── semantic_faiss_metadata.json   # 1:1 case metadata for FAISS index
│   │   └── baseline_tfidf.joblib          # Simple baseline model for evaluation
│   ├── evaluation/              # Benchmark harness and diagnostic analysis
│   │   ├── golden_set.py        # Golden Set loader and multi-turn dialogue rebuilder
│   │   ├── metrics.py           # Multi-class intent and safety metric calculators
│   │   ├── run_evaluation.py    # Main evaluation harness runner
│   │   ├── diagnose_decisions.py# Phase 8A failure analysis engine
│   │   ├── run_llm_judge.py     # Phase 9 LLM-as-a-judge orchestrator
│   │   ├── phase10_benchmark.py # Phase 10 before/after comparison runner
│   │   └── results/             # Benchmark JSONs, CSVs, and markdown reports
│   ├── scripts/                 # Data preparation and training CLI utilities
│   └── tests/                   # 108 unit and integration tests
├── data/
│   ├── apple_goldset.csv        # Canonical 200-conversation evaluation dataset (Read-Only)
│   ├── prepared_cases.jsonl     # 22,738 preprocessed historical support cases
│   └── apple_full_conversations.csv # Raw conversation paths from Twitter dataset
├── frontend/                    # React + Vite support agent dashboard
└── README.md                    # Project documentation
```

---


## 6. Dataset Selection & Preprocessing

The original Customer Support on Twitter dataset contains roughly 3M tweets.
I used an offline preprocessing pipeline to construct a focused AppleSupport
corpus from this large source dataset. The full 3M-tweet archive is not part of
the runtime workflow and is not required for a reviewer to reproduce the
included benchmark.

### 1. Raw Dataset Inspection

The raw dataset contains:

- `tweet_id`
- `author_id`
- `inbound`
- `created_at`
- `text`
- `response_tweet_id`
- `in_response_to_tweet_id`

These fields were used to identify customer messages, AppleSupport responses,
and relationships between messages.

### 2. Brand Selection

I selected `AppleSupport` as the target support brand.

The filtering process first identified tweets associated with the
AppleSupport account and then recovered customer messages directly connected
to those support interactions.

This produced:

- 106,860 AppleSupport support tweets
- 36,658 directly connected customer tweets
- 143,518 relevant tweets

### 3. Conversation Reconstruction

Individual tweets are not sufficient for evaluating a support agent because
the meaning of a customer message can depend on previous turns.

I therefore used the dataset's response relationship fields:

- `response_tweet_id`
- `in_response_to_tweet_id`

to reconstruct conversation paths.

This produced:

- 83,470 potential conversation roots
- 28,772 reconstructed conversation paths
- 91,316 messages across the reconstructed conversations

The reconstruction is treated as an approximation because the source dataset
does not guarantee that every conversation can be perfectly recovered.

### 4. Support-Case Preparation

The reconstructed conversations were then transformed into historical
support cases suitable for retrieval.

Preprocessing included:

- separating customer and AppleSupport messages
- identifying support-response relationships
- removing unusable/incomplete records
- normalizing text for retrieval
- retaining the customer issue together with its historical AppleSupport
  resolution
- preserving conversation context where available
- generating stable case/conversation identifiers

This produced `22,738` prepared historical support cases.

These cases form the runtime retrieval corpus used by the agent.

### 5. Data Validation

Before the processed corpus is used for retrieval or classification, the
pipeline performs structural and integrity checks:

- validates the expected input schema
- validates customer/AppleSupport message roles
- checks response relationships used for conversation reconstruction
- filters incomplete or unusable support cases
- validates prepared case identifiers and required fields
- checks for Golden Set overlap before retrieval index construction
- verifies zero Golden Set leakage into the runtime corpus

These checks are intended to catch malformed records and evaluation leakage;
they do not guarantee that every reconstructed conversation is semantically
perfect.

### 6. Retrieval Index

The prepared cases were indexed using semantic embeddings with
`all-MiniLM-L6-v2` and FAISS.

At runtime, an incoming customer message is embedded and matched against the
prepared AppleSupport historical cases to retrieve relevant evidence.

### 7. Golden Set Isolation

The 200-example Golden Set was kept completely separate from this pipeline.

It is used only for evaluation and was not used for:

- training
- retrieval
- prompting
- few-shot examples
- threshold tuning
- model development

This separation prevents evaluation leakage.

### 8.  Dataset Scope

The full ~3M-tweet Kaggle dataset is not required at runtime or for reproducing
the benchmark. The large raw dataset is used as the source from which the
focused AppleSupport corpus is constructed offline.

The repository contains the processed artifacts required for the documented
runtime and evaluation workflow.

### 9.  Data Flow Architecture

```
Original Kaggle Dataset (~3M tweets)
           │
           ▼
AppleSupport Selection (143,518 tweets)
           │
           ▼
Conversation Reconstruction (28,772 paths)
           │
           ▼
Prepared Support Cases (22,738 cases)
           │
           ▼
Retrieval Indexes (TF-IDF + FAISS)
           │
           ▼
Runtime Support Agent

────────────────────────────────────────────
Separately Isolated:

Human-Reviewed Golden Set (200 cases)
           │
           ▼
Deterministic Evaluation Harness (Phase 8 & 10)
```

### Strict Golden Set Isolation
The canonical evaluation file `data/apple_goldset.csv` contains 200 human-audited conversations. To ensure zero data leakage and preserve evaluation integrity:
- **NOT used for training** (the intent classifier was fitted only on historical prepared cases).
- **NOT used for retrieval** (asserted at index build time: zero overlap between indexed case IDs and Golden Set conversation IDs).
- **NOT used for prompt few-shot examples** or in-context demonstrations.
- **NOT used for threshold tuning** or hyperparameter optimization.
- **Strictly read-only evaluation benchmark**.

### What a Reviewer Needs
A reviewer **does NOT need to download or process the full 3M-tweet Kaggle dataset**:
1. **Pre-Built Runtime Artifacts**: The repository already includes all processed data and model artifacts:
   - `data/prepared_cases.jsonl` (22,738 processed cases)
   - `backend/models/intent_classifier.joblib` (trained 12-class classifier)
   - `backend/models/semantic_faiss.index` & `semantic_faiss_metadata.json` (dense vector index)
   - `backend/models/tfidf_retriever.joblib` (lexical retriever)
2. **Pre-Packaged Benchmark Set**: The 200-conversation Golden Set (`data/apple_goldset.csv`) is already present for deterministic evaluation.
3. **Running the Project**: Reviewers only need Python 3.12 and the virtual environment dependencies (`requirements.txt`) to run the backend API or reproduce the complete evaluation benchmark in under 15 minutes.

---

## 7. Setup & Installation

### Prerequisites
- **Python 3.12+**
- **Node.js 18+ and npm** (for frontend)
- **MongoDB** (local instance or MongoDB Atlas URI)
- **OpenRouter API Key** (optional for offline testing; required for live LLM generation)

### Backend Setup (Windows PowerShell)

```powershell
# 1. Navigate to backend directory
cd backend

# 2. Create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment variables
Copy-Item .env.example .env
```

Open `backend/.env` and configure the following variables:

```env
# Application
ENVIRONMENT=development
LOG_LEVEL=INFO

# MongoDB Connection
MONGODB_URI=mongodb://localhost:27017
MONGODB_DATABASE=hiver_support

# OpenRouter LLM Configuration
OPENROUTER_API_KEY=your_openrouter_api_key_here
OPENROUTER_MODEL=openrouter/free
```

*(No secrets or live keys are committed in the repository.)*

---

## 8. Quick Start

### Terminal 1 — Start Backend Server

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

The API will be available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is hosted at `http://127.0.0.1:8000/docs`.

### Terminal 2 — Start Frontend Dashboard

```powershell
cd frontend
npm install
npm run dev
```

The frontend dashboard will run at `http://localhost:5173`.

---

## 9. Data & Model Artifacts

All runtime models and vector indexes are pre-built and packaged in the repository:

### A. Required Runtime Artifacts (Pre-Built)
- `data/prepared_cases.jsonl`: 22,738 preprocessed support cases (customer inquiry + support response).
- `backend/models/intent_classifier.joblib`: Trained TF-IDF + Logistic Regression classifier.
- `backend/models/semantic_faiss.index`: 384-dimensional FAISS `IndexFlatIP` vector index.
- `backend/models/semantic_faiss_metadata.json`: Metadata linking FAISS index positions to case IDs.
- `backend/models/tfidf_retriever.joblib`: Serialized TF-IDF lexical index.

### B. Reproducible Evaluation Artifacts
- `data/apple_goldset.csv`: Canonical 200-conversation human-reviewed benchmark dataset (**read-only**).
- `backend/models/baseline_tfidf.joblib`: Reference Simple TF-IDF baseline for benchmark comparison.
- `backend/evaluation/results/`: Evaluation summaries including `phase10_comparison.json`, `phase10_comparison.md`, and diagnostic tables.

---

## 10. API Reference

All routes accept and return strict JSON validated against Pydantic models.

### 1. Health Check
- **Method / Path**: `GET /health`
- **Purpose**: Verifies service status and MongoDB connectivity.
- **Sample Response**:
  ```json
  {
    "status": "healthy",
    "app_name": "Hiver AI Customer Support Agent",
    "version": "0.1.0",
    "environment": "development",
    "database": {
      "status": "connected",
      "details": "MongoDB ping successful."
    }
  }
  ```

### 2. Intent Classification
- **Method / Path**: `POST /api/v1/classify`
- **Purpose**: Classifies a message into one of 12 canonical intents with a confidence score.
- **Sample Request**:
  ```json
  {
    "message": "My iPhone battery is draining fast after updating to iOS 11."
  }
  ```
- **Sample Response**: Returns predicted `intent` (`"Battery / Charging"`), `confidence` (`0.9967`), and top candidate predictions.

### 3. Case Retrieval
- **Method / Path**: `POST /api/v1/retrieve`
- **Purpose**: Retrieves top-K grounding evidence cases using semantic FAISS or lexical TF-IDF.
- **Sample Request**:
  ```json
  {
    "message": "iPhone 7 video quality choppy",
    "top_k": 3,
    "retriever": "semantic"
  }
  ```
- **Sample Response**: Returns top retrieved items with cosine similarity scores, customer messages, and historical support answers.

### 4. Support Decision Agent (Main Endpoint)
- **Method / Path**: `POST /api/v1/agent`
- **Purpose**: Evaluates conversation dialogue, determines action (`auto_handle`, `clarify`, `escalate`), and generates grounded response.
- **Sample Request**:
  ```json
  {
    "conversation_id": "conv_123",
    "messages": [
      {
        "role": "customer",
        "text": "My iPhone battery is draining very quickly after the latest update."
      }
    ]
  }
  ```
- **Sample Response**:
  ```json
  {
    "conversation_id": "conv_123",
    "action": "auto_handle",
    "intent": "Battery / Charging",
    "intent_confidence": 0.9967,
    "reason": "The issue is clear and relevant historical evidence is available.",
    "response": "Grounded response generated from the retrieved historical AppleSupport evidence.",
    "clarification_question": null,
    "retrieval": {
      "top_similarity": 0.8825,
      "top_k": 3
    },
    "signals": {
      "ambiguous": false,
      "evidence_sufficient": true,
      "repeated_troubleshooting": false,
      "frustrated": false,
      "resolved_closing": false
    },
    "evidence": [...]
  }
  ```

---

## 11. Decision Engine Policy

Routing is governed by an interpretable, deterministic priority policy rather than delegating control unconditionally to an LLM:

1. **ESCALATE (Sensitive / Safety)**: Physical hardware hazards (cracked screen, water damage, swollen battery), explicit human transfer requests (*"talk to a person"*), or legal mentions.
2. **AUTO_HANDLE (Resolved / Closing)**: Customer acknowledges that the issue is fixed (*"works now"*, *"all sorted"*) or sends closing thanks (*"thank you"*).
3. **ESCALATE (Repeated Troubleshooting)**: Customer reports multiple unsuccessful troubleshooting attempts or states that recommended actions failed (*"already tried that"*, *"still having problems"*).
4. **ESCALATE (Frustration + Unresolved)**: Angry emojis (`😡`, `😤`, `😣`), aggressive punctuation, or persistent complaint language co-occurring with an active issue.
5. **CLARIFY (Ambiguous Inquiry)**: Missing product, device model, or feature referents (*"It stopped working after I updated it"*). Generates targeted clarifying question.
6. **CLARIFY (Low Intent Confidence)**: Classifier probability < 0.60 indicates ambiguity; seeks details rather than risking an ungrounded answer or premature escalation.
7. **CLARIFY (Insufficient Retrieval Similarity)**: Top retrieval similarity < 0.65 indicates unfamiliar wording; requests additional information to retrieve grounded guidance.
8. **AUTO_HANDLE (Clear & Grounded)**: Unambiguous inquiry with confident intent and high historical evidence similarity.

---

## 12. Evidence Grounding & Safety Principles

- **Strict Evidence Boundary**: The generator prompt explicitly forbids introducing troubleshooting steps (e.g. restarting, resetting network settings, restoring) unless directly supported by the retrieved historical AppleSupport evidence.
- **Evidence Quality Principle**: *"High retrieval similarity is treated as evidence strength, not as proof that the response is safe or correct."*
- **Social Media Sanitization**: All raw `@AppleSupport` handles and t.co shortlinks are automatically filtered from evidence and completions.

---

## 13. Golden Set Benchmark & Evaluation

Evaluation was conducted against the canonical **200-conversation Golden Set** (`data/apple_goldset.csv`), reviewed and labeled by human annotators across 12 canonical intents and binary escalation flags (`YES` / `NO`).

### Intent Classification Benchmark (Preserved Across Phases)
- **Accuracy**: **52.00%** (outperforming Simple TF-IDF baseline at 46.5% and Majority Class baseline at 20.5%)
- **Macro F1**: **0.4317**
- **Weighted F1**: **0.5344**
- *(Model weights remained untouched during Phase 10; classification performance is strictly preserved.)*

### Phase 8 vs Phase 10 Decision Policy Comparison

| Metric | Phase 8 Baseline | Phase 10 Improved | Delta | Business Impact |
| :--- | :---: | :---: | :---: | :--- |
| **False-Positive Escalations** | 87 | **15** | **-72 (-82.8%)** | Massive reduction in unnecessary human handoffs |
| **True-Positive Escalations** | 12 | **15** | **+3 (+25.0%)** | Better capture of genuine escalation cases |
| **Escalation Precision** | 12.12% | **50.00%** | **+37.88%** | Over 4x higher specialist handoff accuracy |
| **Escalation Recall** | 46.15% | **57.69%** | **+11.54%** | Captures 15 of 26 human escalation cases |
| **Escalation F1** | 0.1920 | **0.5357** | **+0.3437** | Strong overall decision quality balance |
| **Unsafe Auto-Handles (YES as Auto)** | 12 | **3** | **-9 (-75.0%)** | **75% reduction in unsafe autonomous responses** |
| **Unsafe Auto-Handle Rate** | 15.79% | **3.41%** | **-12.38%** | Lower unsafe-auto-handle rate on the evaluated benchmark. |
| **Auto-Handle Precision (wrt NO)** | 84.21% | **96.59%** | **+12.38%** | 96.6% of auto-handle decisions matched the human NO-escalation label on this 200-example benchmark. |
| **Auto-Handle Count** | 76 (38.0%) | 88 (44.0%) | +12 | Resolved/closing cases handled cleanly |
| **Clarify Count** | 25 (12.5%) | 82 (41.0%) | +57 | Safe fallback for ambiguous or low-similarity inputs |
| **Escalate Count** | 99 (49.5%) | 30 (15.0%) | -69 | Eliminates hyper-escalation behavior |

---


## 14. What Is Misleading About My Headline Number?

The strongest headline result from the final benchmark is an **82.8% reduction in false-positive escalations**, from **87 to 15** on the same 200-example Golden Set.

This result is meaningful: the initial decision policy was overly conservative and escalated **49.5%** of evaluated conversations, while the improved policy reduced this to **15.0%**. At the same time, true-positive escalations increased from **12 to 15**, escalation precision improved from **12.12% to 50.00%**, and unsafe auto-handles decreased from **12 to 3**.

However, this headline number can be misleading if interpreted as overall agent accuracy or production readiness.

- It measures **one dimension of the decision policy**, not the complete support-agent performance.
- The benchmark contains only **200 human-reviewed conversations**, so the result should not be generalized to all customer-support traffic.
- **Intent classification accuracy remained 52.0%**, showing that intent prediction is still a significant quality bottleneck.
- The **90.5% evidence-supported response rate** came from an automated LLM judge and was not treated as ground truth.
- A 50-example human audit of the LLM judge showed only **58.0% binary agreement** and **Cohen's κ = -0.0780**, with the LLM judge systematically scoring evidence support higher than human reviewers.
- The **3.41% unsafe auto-handle rate** is a benchmark measurement, not a universal production safety guarantee.

Therefore, the most defensible interpretation is:

> **The Phase 10 changes substantially improved routing behavior on the fixed 200-example benchmark, especially by reducing unnecessary escalations and unsafe auto-handles. They do not demonstrate that the complete agent is 82.8% better, nor that it is production-ready.**

This distinction is important because the project's goal is not simply to maximize a single headline metric, but to understand where the system is reliable, where it fails, and what evidence is still needed before deployment.

## 15. LLM-as-a-Judge Evaluation & Human Audit

### Automated LLM Evaluation (200 Golden Set Examples)
- **Overall Score**: **4.74 / 5.0** (Median: 4.80)
- **Correctness**: 4.91 / 5.0
- **Groundedness**: 4.81 / 5.0
- **Helpfulness**: 4.00 / 5.0
- **Evidence-Supported Response Rate**: **90.5%** (181 / 200 responses)

### Empirical Human vs LLM Audit (50 Diverse Examples)
- **Exact Binary Agreement**: **58.0%** (29/50)
- **Binary Cohen's Kappa**: **-0.0780** (*poor agreement; below-chance agreement in this audit*)
- **Human Mean Support Score**: **3.46 / 5.0**
- **LLM Mean Support Score**: **4.92 / 5.0**
- **Score Mean Absolute Error (MAE)**: **1.62**
- **Total Disagreements**: 21 cases (19 cases where LLM judged supported but human judged unsupported)

> **Key Evaluation Insight**: *The LLM judge was treated as a diagnostic evaluator rather than ground truth because the 50-example human audit revealed weak agreement and systematic overestimation of evidence support by automated LLM judges.*

---

## 16. Key Failure Modes Discovered

1. **Intent Confusion on Brief Messages**: Conversational snippets (e.g., *"iOS 11.0.2."*, *"DM sent"*) suffer from high classification entropy.
2. **Over-Escalation on Out-of-Distribution Vocabulary**: Previously, slight phrasing differences dropped retrieval similarity below 0.65, triggering 87 false escalations.
3. **Single-Turn Troubleshooting Failure**: Customers describing prior attempts in the same turn (e.g., *"I reset settings. Still having problems."*) bypassed multi-turn tracking.
4. **Subtle Customer Frustration**: Sarcasm and emoji anger (`😡`) were previously unflagged if intent confidence was high.
5. **Misreading Closing Turns**: Benign closing acknowledgments (*"Thank you, it works now"*) previously failed similarity checks and escalated.
6. **Automated LLM Judge Over-Optimism**: LLM judges routinely scored generic reassurance as fully grounded evidence when human annotators scored it unsupported.

---

## 17. Safety & Governance Principles

- **Golden Set Isolation**: `data/apple_goldset.csv` is strictly read-only and is never used for training, feature extraction, retrieval indexing, prompt few-shotting, or threshold optimization.
- **No Threshold Gaming**: Decision gates were not tuned to fit specific Golden Set rows; routing logic was improved structurally.
- **Safety Gate Enforcement**: Any policy change that increases unsafe auto-handles is automatically rejected.

---

## 18. Test Suite

The test suite contains **108 automated tests** passing with zero failures:

```powershell
cd backend
.\.venv\Scripts\pytest -q
# Result: 108 passed in ~30s
```

Test coverage includes:
- Data preprocessing, handle stripping, and case extraction (`test_preprocessing.py`)
- MongoDB schema and repository CRUD operations (`test_database.py`)
- Lexical TF-IDF retrieval scoring and ranking (`test_retriever.py`)
- Dense semantic FAISS vector retrieval and cosine metrics (`test_semantic_retriever.py`)
- Intent classifier training, confidence scoring, and taxonomy validation (`test_classifier.py`)
- Decision engine signals, ambiguity, and Phase 10 regressions (`test_agent.py`)
- Grounded response generation, prompt hardening, and mock safety (`test_generator.py`)
- Golden Set validation, zero-leakage assertions, and metric math (`test_evaluation.py`)
- LLM judge schemas, agreement metrics, and cache handling (`test_llm_judge.py`)
- API endpoints, routing, and HTTP validation error handling (`test_api.py`, `test_schemas.py`)

---

## 19. Reproducibility Guide

All steps can be reproduced directly from the `backend/` directory using the included dataset files (`data/prepared_cases.jsonl` and `data/apple_goldset.csv`). No download or processing of the raw 3M-tweet Kaggle archive is required.

```powershell
# 1. (Optional) Re-extract cases from included Apple subset (data/apple_full_conversations.csv)
python scripts/prepare_cases.py --no-mongo

# 2. (Optional) Rebuild TF-IDF lexical index from prepared cases
python scripts/build_retrieval_index.py

# 3. (Optional) Rebuild dense FAISS semantic vector index
python scripts/build_semantic_index.py

# 4. (Optional) Retrain supervised 12-class intent classifier
python scripts/train_classifier.py

# 5. Execute Golden Set evaluation harness (runs out-of-the-box on apple_goldset.csv)
python evaluation/run_evaluation.py

# 6. Run Phase 8A diagnostic error breakdown
python evaluation/diagnose_decisions.py

# 7. Run Phase 10 before/after comparison benchmark
python evaluation/phase10_benchmark.py
```

*(Note: Pre-built models are already packaged in `backend/models/`, so steps 5–7 can be executed immediately without retraining or re-indexing.)*

---

## 20. Known Limitations

- **Dataset Scope**: Kaggle Twitter data from 2017 may not reflect modern iOS releases or current Apple support procedures.
- **Evaluation Set Size**: The 200-conversation Golden Set is relatively small; the `App Store / Purchases` class has zero support examples.
- **Classification Headroom**: At 52.0% accuracy on multi-class Twitter text, intent classification remains a primary quality bottleneck.
- **Graph Reconstruction Noise**: Conversation threading heuristics can occasionally link tangential replies.
- **Retrieval Evaluation**: Retrieval quality is assessed via top-case similarity and end-to-end task grounding, as corpus-level Recall@K / MRR query labels are unavailable.
- **No Live Twitter/X Posting**: The agent does not execute automated live posts to Twitter/X.

---

## 21. Future Improvements

1. **Model Upgrades**: Transition from linear TF-IDF classification to a fine-tuned domain cross-encoder or modern small language model.
2. **Corpus-Level Retrieval Benchmarks**: Annotate explicit query-document relevance pairs to compute formal Recall@K and MRR.
3. **Dynamic Few-Shot Grounding**: Retrieve both historical cases and verified policy documentation into prompt context.
4. **Expanded Human Auditing**: Scale human-in-the-loop evidence validation from 50 to 500 examples to better calibrate automated judges.
5. **Real-Time Webhook Integration**: Support live Twitter/X API v2 webhook listeners for real-time agent triage.

---

## 22. 60-Second Reviewer Demo Scenario

1. **Start Backend**: Run `python -m uvicorn main:app --reload` from `backend/`.
2. **Open Swagger UI**: Visit `http://127.0.0.1:8000/docs` in your browser.
3. **Test Clear Issue (`auto_handle`)**:
   - Send `POST /api/v1/agent` with text: `"My iPhone battery is draining very quickly after the latest update."`
   - Observe predicted intent `Battery / Charging` (confidence > 0.95), action `auto_handle`, and grounded advice.
4. **Test Ambiguous Query (`clarify`)**:
   - Send `POST /api/v1/agent` with text: `"It stopped working after I updated it."`
   - Observe action `clarify` with targeted question asking what stopped working.
5. **Test Failed Troubleshooting (`escalate`)**:
   - Send `POST /api/v1/agent` with text: `"Last night my keyboard disappeared so I reset the phone settings. Still having problems."`
   - Observe action `escalate` with signal `repeated_troubleshooting: true`.
6. **Inspect Benchmark Comparison**:
   - Open `backend/evaluation/results/phase10_comparison.md` to review the empirical -82.8% reduction in false-positive escalations.

---
## What I Would Do With One More Week

If I had one more week, I would prioritize improvements based on the failure
analysis rather than adding more features.

1. **Improve intent classification (P0)**  
   The 52% intent accuracy on the 200-example Golden Set is the largest
   quality bottleneck. I would add more human-reviewed training examples,
   especially for low-performing intents such as App Issue, Settings /
   Features, Messages / Calling, and Apple ID / Account, and use the observed
   confusion matrix to guide the additional labeling.

2. **Improve multi-turn context handling (P0)**  
   I would make frustration, resolution, and repeated-troubleshooting
   detection more context-aware instead of relying primarily on deterministic
   phrase patterns. This should reduce both missed escalations and unnecessary
   escalations caused by short conversational messages.

3. **Build a labeled retrieval benchmark (P1)**  
   The current retrieval comparison is diagnostic because the corpus does not
   have formal relevance labels. I would label a small retrieval evaluation
   set and measure Recall@K and MRR, allowing retrieval improvements to be
   measured independently from downstream response quality.

4. **Improve evidence selection for generation (P1)**  
   When several historical cases are similarly relevant, I would rank evidence
   by both semantic similarity and resolution specificity, so the generator
   is more likely to use the most directly applicable historical resolution.

5. **Calibrate the evaluation judge (P1)**  
   The human-vs-LLM evidence audit showed only 58% exact binary agreement and
   Cohen's κ of -0.078. I would expand the human audit set, refine the judging
   rubric with disagreement examples, and calibrate the judge before relying
   on it for broader regression testing.

6. **Add production-oriented observability (P2)**  
   I would add latency, retrieval confidence, fallback frequency, decision
   distributions, and escalation reasons to structured monitoring so that
   failures can be detected and investigated after deployment.

The goal would not be to maximize a single benchmark number. I would first
improve the weakest measurable components—intent classification, retrieval
quality, and evaluator reliability—while preserving the conservative safety
behavior of the decision engine.

## 23. Dataset & License Attribution

- **Dataset**: Kaggle *Customer Support on Twitter* dataset (`twcs.csv`).
- The full 3M-tweet Kaggle archive is excluded from Git per assignment guidelines encouraging subsampling; all code, pre-built model artifacts, and reproducible AppleSupport datasets needed to run and benchmark the system are included in the repository.
- All code and evaluation harnesses are developed as part of the Hiver SDE Intern technical assessment.
