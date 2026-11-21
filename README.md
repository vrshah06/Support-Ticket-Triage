# AI Support Ticket Triage System

An intelligent, production-ready AI triage application built in Python that automatically ingests customer support tickets, predicts categories and priorities with structured Pydantic schemas, and routes uncertain or high-risk cases to a human-in-the-loop review queue.

---

## 🎯 Deliverable 1: Scalability Design Note

### How to run this system for 50,000 tickets a day
1. **Asynchronous Ingestion via Message Queue**: Decouple ingestion from processing by streaming incoming tickets from webhooks, Zendesk, or email into a distributed message broker (e.g., Redis or RabbitMQ) managed by Celery or Temporal. This buffers spikes and absorbs traffic without dropping requests.
2. **Horizontal Parallel Worker Pools**: Deploy containerized stateless worker pools across Kubernetes nodes (EKS/GKE). Workers consume from the queue in parallel, enforcing concurrency limits per OpenAI API key tier (e.g., 50–100 concurrent requests) to maximize throughput without exceeding TPM/RPM quotas.
3. **Persistent Relational Database & Auditing**: Store all tickets, versioned AI inferences, token usage, confidence scores, and human review decisions in PostgreSQL. Use indexed JSONB columns for raw LLM inputs/outputs and structured relational columns for query optimization.
4. **Rate Limiting, Exponential Backoff & Dead-Letter Queues (DLQ)**: Implement token-bucket rate limiting matching OpenAI tier limits. Failed requests retry up to 3 times with exponential backoff and jitter. Permanently failed tickets route to a Dead-Letter Queue (DLQ) for engineering inspection, ensuring zero data loss.

### How to know it is still working well one month later
5. **Real-time Operational & Financial Observability**: Track operational metrics on Prometheus/Datadog dashboards:
   - **P95 / P99 Latency**: Model inference and triage pipeline latency.
   - **API Error & Timeout Rates**: Track 429 (rate limits) and 5xx failures.
   - **Human Escalation Rate**: Monitor the percentage of tickets routed to human review (healthy baseline: 15–30%). A sudden spike signals semantic shift, outages, or prompt drift.
   - **Cost per Ticket**: Monitor daily OpenAI token spend.
6. **Continuous Quality Monitoring & Active Learning from Human Review**:
   - Calculate agreement rates between initial AI predictions and human corrections in the review queue.
   - Log disagreement patterns (e.g., AI predicting *Low* on issues human reviewers mark *Urgent*).
   - Periodically sample and evaluate 200 random auto-approved tickets to catch silent false negatives.
   - Ingest confirmed human corrections into a regression evaluation test suite and few-shot prompt bank to continuously improve classification accuracy over time.

---

## 🏗️ System Architecture & Workflow

```
                        [ Customer Tickets CSV ]
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │    Ticket Processor Engine    │
                   │  - CSV Validation & Parsing   │
                   │  - Empty Body Detection       │
                   └───────────────┬───────────────┘
                                   │
                        (Non-empty tickets)
                                   ▼
                   ┌───────────────────────────────┐
                   │    OpenAI Classifier (LLM)    │
                   │  - Structured Output via      │
                   │    Pydantic Schema            │
                   │  - Category & Priority        │
                   │  - Confidence (0.0 to 1.0)    │
                   │  - Exponential Backoff Retry  │
                   └───────────────┬───────────────┘
                                   │
                                   ▼
                   ┌───────────────────────────────┐
                   │   Confidence & Safety Router  │
                   └───────┬───────────────┬───────┘
                           │               │
     [Confidence >= 0.80   │               │ [Confidence < 0.80 OR Urgent Priority
      & Non-Urgent Priority]               │  OR Critical Keywords OR Empty Body]
                           ▼               ▼
           ┌───────────────────────┐ ┌─────────────────────────┐
           │ Automatic Approval    │ │ Human Review Queue      │
           │ (needs_review = "no") │ │ (needs_review = "yes")   │
           └───────────┬───────────┘ └────────────┬────────────┘
                       │                          │
                       │             (Human review & correction)
                       │                          │
                       ▼                          ▼
                   ┌───────────────────────────────┐
                   │   Exports & Reporting Engine  │
                   │   - outputs/results.csv       │
                   │   - outputs/report.json       │
                   └───────────────────────────────┘
```

### Taxonomy Rules
- **Allowed Categories (Exact 5)**: `Billing`, `Technical`, `Account`, `Shipping`, `Other`
- **Allowed Priorities (Exact 4)**: `Low`, `Medium`, `High`, `Urgent`

### Routing Decision Logic
1. **Empty Body**: Immediately routed to human review (`needs_review="yes"`). No LLM call is wasted.
2. **Confidence Threshold (Default: 0.80)**: Predictions with confidence `< 0.80` are sent to human review.
3. **Conservative Escalation**: LLM self-reported confidence is not a calibrated guarantee. Tickets classified as `Urgent` or containing high-risk keywords (e.g. unauthorized charges, physical lockouts, security breaches) are automatically routed to human review (`needs_review="yes"`).
4. **API Failure**: Failed API requests retry 3 times with exponential backoff. If still failing, they are marked as `failed` and routed to human review (`needs_review="yes"`).

---

## 📁 Repository Structure

```
Support-Ticket-Triage/
│
├── app.py                     # Streamlit web application & interactive dashboard
├── classifier.py              # OpenAI API client, Pydantic schema, heuristic fallback
├── processor.py               # Batch execution, validation, routing, human review, exports
├── config.py                  # Environment config, thresholds, allowed labels
├── run_batch.py               # Headless CLI batch execution script
├── requirements.txt           # Python dependencies
├── .env.example               # Template environment configuration
├── .gitignore                 # Git ignore rules
├── README.md                  # System documentation & scaling design note
├── PRD.md                     # Product Requirements Document
│
├── candidate/
│   ├── README.txt             # Assessment instructions
│   ├── ml-1-support-ticket-triage.pdf  # Assessment specification PDF
│   └── tickets.csv            # Official 300-ticket dataset
│
├── outputs/
│   ├── results.csv            # Mandatory 4-column output file (300 rows)
│   └── report.json            # Processing summary report & metrics
│
└── tests/
    └── test_processor.py      # Automated pytest suite (13 passing tests)
```

---

## 🚀 Quickstart & Setup

### 1. Prerequisites
- Python 3.10+
- (Optional) OpenAI API Key. If no key is provided, the system seamlessly uses an intelligent offline heuristic classifier for offline evaluation and testing.

### 2. Installation
```bash
git clone https://github.com/vrshah06/Support-Ticket-Triage.git
cd Support-Ticket-Triage

# Create and activate virtual environment (optional)
python -m venv venv
venv\Scripts\activate  # On Windows
# source venv/bin/activate  # On macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 3. Environment Configuration
Create a `.env` file in the project root:
```bash
cp .env.example .env
```
Populate `.env` with your OpenAI API key:
```ini
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini
CONFIDENCE_THRESHOLD=0.80
```

### 4. Run the Streamlit Application
```bash
streamlit run app.py
```
Open your browser at `http://localhost:8501`.

### 5. Run Headless Batch Processing
To generate `results.csv` and `report.json` directly via CLI:
```bash
python run_batch.py
```

### 6. Run Automated Test Suite
```bash
pytest tests/test_processor.py -v
```

---

## 📊 Verification of Mandatory Outputs

### `outputs/results.csv`
Meets 100% of the assessment constraints:
- **Exact Columns**: `id, category, priority, needs_review`
- **Exact Row Count**: 300 rows matching the 300 input tickets in original order.
- **Valid values**: `needs_review` contains only `"yes"` or `"no"`.
- **Review rule**: For tickets requiring review that are pending human action, category and priority are left empty. For human-confirmed tickets, final reviewed labels are populated.

### `outputs/report.json`
- Includes processing totals, automated approval counts, human review counts, urgent ticket counts, duration, and API error counts.
- **Accuracy Notice**: Explicitly clarifies that because ground-truth labels are absent in the dataset, accuracy cannot be claimed without verified labels.

---

## 🧪 Automated Test Results

All 13 unit and integration tests pass:
```
tests/test_processor.py::test_load_and_validate_csv_success PASSED
tests/test_processor.py::test_load_and_validate_csv_missing_columns PASSED
tests/test_processor.py::test_all_five_categories_supported PASSED
tests/test_processor.py::test_all_four_priorities_supported PASSED
tests/test_processor.py::test_confidence_based_routing PASSED
tests/test_processor.py::test_empty_ticket_body_routes_to_human_review PASSED
tests/test_processor.py::test_conservative_escalation_for_urgent PASSED
tests/test_processor.py::test_long_ticket_message_handling PASSED
tests/test_processor.py::test_api_failure_handling_and_retries PASSED
tests/test_processor.py::test_human_review_correction_preserves_ai_prediction PASSED
tests/test_processor.py::test_export_results_csv_schema_and_rows PASSED
tests/test_processor.py::test_export_report_json_format PASSED
tests/test_processor.py::test_full_dataset_300_tickets PASSED
```
