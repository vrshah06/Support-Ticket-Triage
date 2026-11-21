# Product Requirements Document (PRD)
# AI Support Ticket Triage System

**Version:** 1.0  
**Project Type:** Technical Assessment  
**Development Timeline:** 60 Minutes (MVP)  
**Status:** Ready for Implementation

---

## 1. Product Overview & Vision

### 1.1 Product Overview

The AI Support Ticket Triage System is an intelligent ticket classification application that automates the initial processing of customer support tickets.

Support teams receive hundreds of customer tickets daily. Manually reading, categorizing, and assigning priorities to every ticket is time-consuming and can delay responses to urgent customer issues.

This application uses a Large Language Model (LLM) to automatically:

- Classify support tickets into appropriate categories.
- Assign priority levels.
- Generate confidence scores for predictions.
- Identify tickets requiring human intervention.
- Provide a dashboard to monitor ticket processing.
- Generate downloadable processing reports.

### 1.2 Product Vision

Build a reliable AI-powered ticket triage system that reduces manual classification effort while ensuring that uncertain or potentially critical tickets are reviewed by humans.

The system should prioritize reliability and human oversight over fully automated decision-making.

---

## 2. Problem Statement & Objectives

### 2.1 Problem Statement

Customer support teams receive hundreds of tickets every day. Each ticket must be read, categorized, and assigned a priority before the support team can take action.

Manual processing introduces:
- Delayed ticket classification.
- Inconsistent priority assignment.
- Increased operational workload.
- Risk of missing urgent customer issues.

AI can automate the initial classification process, but incorrect predictions can negatively affect customer experience.

### 2.2 Objectives

1. Automate classification of 300 support tickets.
2. Assign appropriate categories and priority levels.
3. Identify uncertain AI predictions.
4. Route uncertain and potentially critical tickets to human review.
5. Provide visibility into processing statistics.
6. Generate downloadable reports.
7. Design an architecture that can eventually support 50,000 tickets per day.

---

## 3. Target Users

### 3.1 Support Team Administrator

Responsible for:
- Uploading ticket datasets.
- Starting ticket processing.
- Monitoring processing statistics.
- Reviewing classification results.
- Downloading reports.

### 3.2 Support Agent / Human Reviewer

Responsible for:
- Reviewing uncertain tickets.
- Correcting incorrect categories.
- Updating incorrect priority assignments.
- Confirming final classifications.

---

## 4. Functional Requirements

### FR-01: CSV Upload

The application must allow administrators to upload a CSV file containing support tickets.

Requirements:
- Accept CSV files.
- Validate the uploaded file.
- Identify required ticket content columns.
- Handle missing or invalid records.
- Display the total number of valid tickets.

### FR-02: AI Ticket Classification

The system must use an LLM to analyze each ticket.

Each ticket must receive:

- Ticket ID.
- Predicted category.
- Predicted priority.
- Confidence score.
- Short classification explanation.
- Processing status.

Categories should be determined after inspecting the actual dataset.

### FR-03: Priority Assignment

The system must assign one of four priority levels:

| Priority | Description |
|---|---|
| Critical | Potentially severe or urgent customer issue |
| High | Significant issue requiring prompt attention |
| Medium | Normal support issue |
| Low | Minor request or general inquiry |

### FR-04: Confidence-Based Routing

The system must calculate or obtain a confidence score for each prediction.

Default confidence threshold: 0.80.

Routing logic:

- Confidence >= 0.80: Eligible for automatic classification.
- Confidence < 0.80: Send to human review.
- Potentially critical issues: Escalate to human review regardless of confidence.
- Failed AI requests: Mark as failed and route for review or retry.

Confidence scores must not be treated as guaranteed probabilities of correctness.

### FR-05: Human Review Queue

The application must provide a dedicated human review interface.

Reviewers should be able to:

- View the original ticket.
- View AI-generated classification.
- View the confidence score.
- Edit the predicted category.
- Edit the predicted priority.
- Confirm the final classification.

The system must preserve both original AI predictions and human corrections.

### FR-06: Dashboard & Analytics

The dashboard must display:

- Total tickets uploaded.
- Successfully processed tickets.
- Automatically classified tickets.
- Tickets requiring human review.
- Failed processing requests.
- Priority distribution.
- Category distribution.

Charts should provide an overview of ticket processing results.

### FR-07: Export & Reporting

The system must generate:

**Processed CSV**
- Original ticket details.
- Predicted category.
- Predicted priority.
- Confidence score.
- Processing status.
- Human-reviewed category and priority, where applicable.

**JSON Summary Report**
- Total tickets.
- Successfully processed tickets.
- Automatically classified tickets.
- Human review count.
- Failed tickets.
- Priority distribution.
- Category distribution.
- Processing duration.

The report must distinguish predictions from verified accuracy measurements.

### FR-08: Error Handling

The application must handle:

- OpenAI API failures.
- Request timeouts.
- Rate limits.
- Invalid model responses.
- Missing ticket content.
- Invalid CSV formats.

Failed requests must not silently be treated as successful classifications.

---

## 5. Non-Functional Requirements

### 5.1 Reliability
- Every uploaded ticket must have a traceable processing status.
- Failed requests must be identifiable.
- Critical issues must not be automatically dismissed based only on model confidence.

### 5.2 Performance
- Process the provided dataset of 300 tickets within the assessment time constraints.
- Use controlled batches to avoid unnecessary API calls and rate-limit failures.
- Display processing progress.

### 5.3 Maintainability
- Use modular Python files.
- Separate AI classification from data processing and UI logic.
- Keep configuration outside application code.

### 5.4 Security
- Store API keys in environment variables.
- Never expose API keys in the frontend.
- Avoid committing `.env` files to GitHub.
- Treat uploaded ticket content as potentially sensitive.

---

## 6. Technology Stack

| Layer | Technology |
|---|---|
| Programming Language | Python |
| Frontend | Streamlit |
| AI Integration | OpenAI API |
| Data Processing | Pandas |
| Data Validation | Pydantic |
| Configuration | Python Dotenv |
| Visualization | Plotly |
| Storage | CSV / JSON |
| Version Control | Git & GitHub |

No separate database is required for the initial MVP.

---

## 7. System Architecture

### 7.1 High-Level Workflow

1. Administrator uploads a CSV file.
2. Application validates and reads the dataset.
3. Ticket processor sends ticket content to the classification engine.
4. OpenAI generates structured classification results.
5. Pydantic validates the model response.
6. Confidence and priority routing rules are applied.
7. Tickets are separated into automatic classification and human review queues.
8. Human reviewers correct uncertain predictions.
9. Dashboard displays processing statistics.
10. Application generates downloadable CSV and JSON reports.

### 7.2 Architecture Components

**Streamlit Application**
- User interface.
- CSV upload.
- Dashboard.
- Human review interface.
- Export functionality.

**Classification Engine**
- OpenAI API integration.
- Classification prompt.
- Structured response generation.
- Category and priority prediction.

**Ticket Processor**
- CSV processing.
- Batch execution.
- Confidence-based routing.
- Retry and failure handling.

**Configuration Module**
- API key management.
- Model configuration.
- Confidence threshold configuration.

---

## 8. Proposed Project Structure

```text
support-ticket-triage/
│
├── app.py
├── classifier.py
├── processor.py
├── config.py
│
├── data/
│   └── tickets.csv
│
├── outputs/
│
├── requirements.txt
├── .env
├── .env.example
├── .gitignore
└── README.md
```

### Module Responsibilities

- `app.py`: Streamlit dashboard and user interactions.
- `classifier.py`: LLM integration and structured classification.
- `processor.py`: Ticket processing, routing and error handling.
- `config.py`: Environment configuration and application settings.

---

## 9. Business Rules

1. Every valid ticket must be processed or explicitly marked as failed.
2. Every successful classification must contain a category, priority, confidence score, and explanation.
3. Tickets below the configured confidence threshold must enter the human review queue.
4. Potentially critical tickets must be escalated for human review.
5. Failed classifications must never be counted as successful.
6. Human corrections must preserve the original AI predictions.
7. Accuracy must only be calculated when reliable ground-truth labels are available.

---

## 10. Scalability & Future Architecture

### 10.1 Scaling to 50,000 Tickets Per Day

The initial application will process 300 tickets using a lightweight architecture.

For production-scale deployment, the following improvements are proposed:

- Introduce a message queue such as Celery with Redis.
- Process tickets asynchronously using multiple workers.
- Store tickets and classification history in PostgreSQL.
- Introduce controlled LLM batching and concurrency.
- Implement retry policies and dead-letter queues.
- Monitor API costs, latency, failure rates, and classification quality.
- Use configurable model and routing policies.

### 10.2 Monitoring After One Month

Monitor the following metrics:

- Classification accuracy against reviewed ground truth.
- Percentage of tickets routed to human review.
- Incorrect critical-ticket classifications.
- API failure rate.
- Average processing time.
- Model cost per ticket.
- Changes in ticket category distribution.

Human-reviewed corrections should be used to identify classification errors and improve prompts and routing policies.

---

## 11. Scope & Constraints

### 11.1 MVP Scope

The first version will include:

- CSV upload.
- AI classification.
- Priority assignment.
- Confidence-based routing.
- Human review interface.
- Dashboard analytics.
- CSV export.
- JSON report generation.
- Basic error handling.

### 11.2 Out of Scope

To meet the 60-minute implementation deadline, the following are excluded:

- User authentication and authorization.
- Multi-tenant support.
- Live integration with external customer support platforms.
- Email notifications.
- Production database.
- Advanced workflow automation.
- Full production-scale distributed infrastructure.

---

## 12. Acceptance Criteria

The project will be considered complete when:

1. The application successfully accepts the provided 300-ticket CSV dataset.
2. Valid tickets are processed through the classification engine.
3. Each successful result includes category, priority, confidence, and explanation.
4. Low-confidence tickets are routed to human review.
5. Potentially critical tickets are escalated.
6. Human reviewers can correct predictions.
7. Dashboard statistics reflect actual processing results.
8. Processed tickets can be downloaded as CSV.
9. A JSON summary report can be generated.
10. API failures and invalid responses are handled appropriately.
11. The application runs successfully locally.
12. A README documents setup, architecture, scaling, and monitoring.

---

## 13. Implementation Milestones

| Phase | Task | Time |
|---|---|---:|
| 1 | Repository and dataset inspection | 5 min |
| 2 | CSV processing and validation | 10 min |
| 3 | OpenAI classification