import os
import time
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd

from config import (
    ALLOWED_CATEGORIES,
    ALLOWED_PRIORITIES,
    DEFAULT_CONFIDENCE_THRESHOLD,
    MAX_RETRIES,
    RETRY_BASE_DELAY,
    MAX_CONCURRENT_WORKERS,
    ESCALATE_PRIORITIES,
    CRITICAL_KEYWORDS,
)
from classifier import TicketClassifier, ClassificationResult

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

REQUIRED_COLUMNS = ["id", "received_at", "customer", "subject", "body"]


class TicketProcessor:
    """Orchestrates CSV ticket ingestion, AI classification, routing, and reporting."""

    def __init__(self, classifier: Optional[TicketClassifier] = None):
        self.classifier = classifier or TicketClassifier()
        self.tickets: List[Dict[str, Any]] = []
        self.results: Dict[str, Dict[str, Any]] = {}  # keyed by ticket_id
        self.processing_start_time: float = 0.0
        self.processing_end_time: float = 0.0
        self.api_error_count: int = 0

    def load_and_validate_csv(self, file_path_or_buffer: Any) -> Tuple[bool, List[str]]:
        """
        Validate CSV structure and required columns.
        Preserves original ticket IDs and data order.
        """
        errors = []
        try:
            df = pd.read_csv(file_path_or_buffer, dtype=str)
        except Exception as e:
            return False, [f"CSV parsing error: {str(e)}"]

        # Check required columns
        missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
        if missing_cols:
            errors.append(f"Missing required columns: {', '.join(missing_cols)}")
            return False, errors

        # Ensure ID column is not empty
        if df["id"].isnull().any() or (df["id"].str.strip() == "").any():
            errors.append("Dataset contains tickets with missing or empty 'id' values.")
            return False, errors

        # Convert to list of dicts while preserving None/empty strings
        self.tickets = []
        for _, row in df.iterrows():
            self.tickets.append({
                "id": str(row.get("id", "")).strip(),
                "received_at": str(row.get("received_at", "")).strip(),
                "customer": str(row.get("customer", "")).strip(),
                "subject": str(row.get("subject", "")).strip(),
                "body": "" if pd.isna(row.get("body")) else str(row.get("body", "")),
            })

        logger.info(f"Loaded {len(self.tickets)} tickets successfully.")
        return True, []

    def _process_single_ticket(
        self, ticket: Dict[str, Any], confidence_threshold: float
    ) -> Dict[str, Any]:
        """
        Process a single ticket with retry logic, confidence routing, and conservative escalation.
        """
        ticket_id = ticket["id"]
        subject = ticket.get("subject", "")
        body = ticket.get("body", "")

        # 1. Check for empty ticket body
        if not body.strip():
            logger.warning(f"Ticket {ticket_id} has empty body. Routing directly to human review.")
            return {
                "id": ticket_id,
                "customer": ticket.get("customer", ""),
                "subject": subject,
                "body": body,
                "ai_category": None,
                "ai_priority": None,
                "ai_confidence": 0.0,
                "ai_explanation": "Ticket body is empty. Insufficient information for automated triage.",
                "status": "human_review",
                "needs_review": "yes",
                "review_reason": "Empty ticket body",
                "is_human_reviewed": False,
                "final_category": None,
                "final_priority": None,
                "retries": 0,
            }

        # 2. Call classifier with exponential backoff retries
        result: Optional[ClassificationResult] = None
        attempts = 0
        last_error = ""

        for attempt in range(1, MAX_RETRIES + 1):
            attempts = attempt
            try:
                result = self.classifier.classify(ticket_id, subject, body)
                break
            except Exception as e:
                self.api_error_count += 1
                last_error = str(e)
                logger.warning(f"Ticket {ticket_id} attempt {attempt} failed: {last_error}")
                if attempt < MAX_RETRIES:
                    time.sleep(RETRY_BASE_DELAY * (2 ** (attempt - 1)))

        # 3. Handle persistent API failure
        if result is None:
            logger.error(f"Ticket {ticket_id} failed after {MAX_RETRIES} attempts. Routing to human review.")
            return {
                "id": ticket_id,
                "customer": ticket.get("customer", ""),
                "subject": subject,
                "body": body,
                "ai_category": None,
                "ai_priority": None,
                "ai_confidence": 0.0,
                "ai_explanation": f"API failure after {MAX_RETRIES} retries: {last_error}",
                "status": "failed",
                "needs_review": "yes",
                "review_reason": f"API failure after {MAX_RETRIES} retries",
                "is_human_reviewed": False,
                "final_category": None,
                "final_priority": None,
                "retries": attempts,
            }

        # 4. Confidence-based and Conservative Escalation Routing Rules
        ai_cat = result.category
        ai_pri = result.priority
        conf = result.confidence
        explanation = result.explanation

        # Check for conservative escalation triggers (Urgent priority or critical keywords)
        text_lower = f"{subject} {body}".lower()
        has_critical_keyword = any(kw in text_lower for kw in CRITICAL_KEYWORDS)
        is_urgent_priority = ai_pri in ESCALATE_PRIORITIES

        needs_review = "no"
        status = "automatically_classified"
        review_reason = "Eligible for automatic classification"

        if is_urgent_priority or has_critical_keyword:
            # Conservative escalation rule: High-risk/urgent tickets require human oversight
            needs_review = "yes"
            status = "human_review"
            review_reason = "Conservative escalation: Potentially urgent or high-risk ticket requires human verification"
        elif conf < confidence_threshold:
            # Low confidence threshold routing rule
            needs_review = "yes"
            status = "human_review"
            review_reason = f"Low confidence score ({conf:.2f} < {confidence_threshold:.2f})"
        else:
            # High confidence, non-urgent -> eligible for automated classification
            needs_review = "no"
            status = "automatically_classified"
            review_reason = "High confidence automatic classification"

        return {
            "id": ticket_id,
            "customer": ticket.get("customer", ""),
            "subject": subject,
            "body": body,
            "ai_category": ai_cat,
            "ai_priority": ai_pri,
            "ai_confidence": round(conf, 4),
            "ai_explanation": explanation,
            "status": status,
            "needs_review": needs_review,
            "review_reason": review_reason,
            "is_human_reviewed": False,
            "final_category": ai_cat if needs_review == "no" else None,
            "final_priority": ai_pri if needs_review == "no" else None,
            "retries": attempts,
        }

    def process_all_tickets(
        self,
        confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
        max_workers: int = MAX_CONCURRENT_WORKERS,
    ) -> Dict[str, Any]:
        """
        Process all loaded tickets concurrently or sequentially.
        """
        if not self.tickets:
            raise ValueError("No tickets loaded to process.")

        self.processing_start_time = time.time()
        self.api_error_count = 0
        total = len(self.tickets)
        completed = 0

        # Execute using thread pool for optimal throughput
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_ticket = {
                executor.submit(self._process_single_ticket, ticket, confidence_threshold): ticket["id"]
                for ticket in self.tickets
            }

            for future in as_completed(future_to_ticket):
                ticket_id = future_to_ticket[future]
                try:
                    res = future.result()
                    self.results[ticket_id] = res
                except Exception as e:
                    logger.error(f"Unexpected error processing ticket {ticket_id}: {e}")
                    self.results[ticket_id] = {
                        "id": ticket_id,
                        "customer": "",
                        "subject": "",
                        "body": "",
                        "ai_category": None,
                        "ai_priority": None,
                        "ai_confidence": 0.0,
                        "ai_explanation": f"Unexpected execution error: {str(e)}",
                        "status": "failed",
                        "needs_review": "yes",
                        "review_reason": "Unexpected execution error",
                        "is_human_reviewed": False,
                        "final_category": None,
                        "final_priority": None,
                        "retries": 1,
                    }

                completed += 1
                if progress_callback:
                    progress_callback(completed, total, f"Processed {completed}/{total} tickets (ID: {ticket_id})")

        self.processing_end_time = time.time()
        duration = self.processing_end_time - self.processing_start_time
        logger.info(f"Processed {total} tickets in {duration:.2f} seconds.")
        return self.get_summary_stats()

    def apply_human_review(
        self, ticket_id: str, human_category: str, human_priority: str
    ) -> bool:
        """
        Apply human correction or confirmation to a ticket.
        Preserves original AI predictions separately from human corrections.
        """
        if ticket_id not in self.results:
            return False

        if human_category not in ALLOWED_CATEGORIES:
            raise ValueError(f"Category '{human_category}' is not in allowed categories: {ALLOWED_CATEGORIES}")
        if human_priority not in ALLOWED_PRIORITIES:
            raise ValueError(f"Priority '{human_priority}' is not in allowed priorities: {ALLOWED_PRIORITIES}")

        record = self.results[ticket_id]
        record["human_category"] = human_category
        record["human_priority"] = human_priority
        record["is_human_reviewed"] = True
        record["final_category"] = human_category
        record["final_priority"] = human_priority
        record["status"] = "human_reviewed"
        # Once human reviewed, the ticket is resolved, but we maintain the audit trail
        logger.info(f"Ticket {ticket_id} reviewed by human: Category={human_category}, Priority={human_priority}")
        return True

    def get_summary_stats(self) -> Dict[str, Any]:
        """Generate comprehensive summary statistics."""
        total = len(self.tickets)
        if total == 0:
            return {"total_tickets": 0}

        successful = sum(1 for r in self.results.values() if r["status"] != "failed")
        auto_classified = sum(1 for r in self.results.values() if r["status"] == "automatically_classified")
        human_review = sum(1 for r in self.results.values() if r["needs_review"] == "yes")
        human_reviewed = sum(1 for r in self.results.values() if r.get("is_human_reviewed", False))
        failed = sum(1 for r in self.results.values() if r["status"] == "failed")

        # Distributions (based on final or predicted priority/category)
        priority_dist = {p: 0 for p in ALLOWED_PRIORITIES}
        category_dist = {c: 0 for c in ALLOWED_CATEGORIES}
        category_dist["Unassigned"] = 0

        urgent_count = 0
        for r in self.results.values():
            pri = r.get("final_priority") or r.get("ai_priority")
            cat = r.get("final_category") or r.get("ai_category")

            if pri in priority_dist:
                priority_dist[pri] += 1
            if pri == "Urgent":
                urgent_count += 1

            if cat in category_dist:
                category_dist[cat] += 1
            else:
                category_dist["Unassigned"] += 1

        duration = (
            self.processing_end_time - self.processing_start_time
            if self.processing_end_time > 0
            else 0.0
        )

        return {
            "total_tickets": total,
            "successfully_classified": successful,
            "automatically_classified": auto_classified,
            "human_review_count": human_review,
            "human_reviewed_count": human_reviewed,
            "failed_tickets": failed,
            "urgent_tickets": urgent_count,
            "priority_distribution": priority_dist,
            "category_distribution": category_dist,
            "processing_duration_seconds": round(duration, 2),
            "api_error_count": self.api_error_count,
        }

    def export_results_csv(
        self, output_path: str, empty_placeholder: str = "Pending Review"
    ) -> pd.DataFrame:
        """
        Generate results.csv matching assessment specifications:
        EXACTLY four columns in this order:
        id, category, priority, needs_review

        Rules:
        1. Generate exactly one row per input ticket.
        2. Preserve the original ticket ID in original input order.
        3. needs_review must contain only "yes" or "no".
        4. If category or priority is not given or pending human review,
           fills with appropriate placeholder message ("Pending Review").
           If a human has confirmed/reviewed it, the human-corrected labels are used.
        5. Do not add any extra columns to results.csv.
        """
        rows = []
        for t in self.tickets:
            tid = t["id"]
            res = self.results.get(tid, {})

            needs_review = res.get("needs_review", "yes")

            if needs_review == "yes":
                # If human has reviewed it, use confirmed labels; otherwise fill placeholder message
                if res.get("is_human_reviewed", False):
                    cat = res.get("final_category")
                    pri = res.get("final_priority")
                else:
                    cat = empty_placeholder
                    pri = empty_placeholder
            else:
                cat = res.get("final_category") or res.get("ai_category")
                pri = res.get("final_priority") or res.get("ai_priority")

            # Ensure neither column is left empty, None, or NaN
            cat_str = str(cat).strip() if cat is not None else ""
            pri_str = str(pri).strip() if pri is not None else ""

            if not cat_str or cat_str.lower() in ("nan", "none", ""):
                cat_str = empty_placeholder
            if not pri_str or pri_str.lower() in ("nan", "none", ""):
                pri_str = empty_placeholder

            rows.append({
                "id": tid,
                "category": cat_str,
                "priority": pri_str,
                "needs_review": needs_review,
            })

        df_out = pd.DataFrame(rows, columns=["id", "category", "priority", "needs_review"])
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        df_out.to_csv(output_path, index=False, encoding="utf-8")
        logger.info(f"Exported results.csv to {output_path} with {len(df_out)} rows.")
        return df_out

    def export_report_json(self, output_path: str) -> Dict[str, Any]:
        """
        Generate report.json clearly distinguishing predictions from verified accuracy measurements.
        """
        stats = self.get_summary_stats()
        report = {
            "metadata": {
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                "model": self.classifier.model,
                "confidence_threshold": DEFAULT_CONFIDENCE_THRESHOLD,
            },
            "metrics": {
                "total_tickets": stats["total_tickets"],
                "successfully_classified": stats["successfully_classified"],
                "automatically_classified": stats["automatically_classified"],
                "human_review_count": stats["human_review_count"],
                "human_reviewed_count": stats["human_reviewed_count"],
                "failed_tickets": stats["failed_tickets"],
                "urgent_tickets": stats["urgent_tickets"],
                "processing_duration_seconds": stats["processing_duration_seconds"],
                "api_error_count": stats["api_error_count"],
            },
            "distributions": {
                "priority_distribution": stats["priority_distribution"],
                "category_distribution": stats["category_distribution"],
            },
            "accuracy_notice": (
                "NOTE ON ACCURACY: The dataset does not contain ground-truth category or priority labels. "
                "Therefore, true classification accuracy (e.g., precision, recall, F1) cannot be mathematically verified. "
                "The metrics reported above represent model predictions and human-in-the-loop triage decisions, "
                "not verified ground-truth accuracy."
            ),
        }

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info(f"Exported report.json to {output_path}")
        return report
