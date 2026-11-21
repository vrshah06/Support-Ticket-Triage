import os
import sys
import io
import json

# Ensure project root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest
import pandas as pd
from unittest.mock import MagicMock, patch

from config import (
    ALLOWED_CATEGORIES,
    ALLOWED_PRIORITIES,
    DEFAULT_CONFIDENCE_THRESHOLD,
)
from classifier import TicketClassifier, ClassificationResult
from processor import TicketProcessor, REQUIRED_COLUMNS


@pytest.fixture
def sample_csv_data():
    return (
        "id,received_at,customer,subject,body\n"
        "T-0001,2026-11-16 07:37,Emma,Wrong item,Order arrived with EU plug\n"
        "T-0002,2026-11-16 07:49,Mateo,Card update,Can I pay with bank transfer?\n"
        "T-0093,2026-11-16 08:00,Ghost,(no subject),\n"
    )


@pytest.fixture
def mock_classifier():
    classifier = MagicMock(spec=TicketClassifier)
    classifier.model = "mock-model"

    def side_effect(ticket_id, subject, body):
        if "EU plug" in body:
            return ClassificationResult(
                category="Shipping",
                priority="Medium",
                confidence=0.92,
                explanation="Wrong physical plug delivered.",
            )
        elif "bank transfer" in body:
            return ClassificationResult(
                category="Billing",
                priority="Low",
                confidence=0.75,  # below 0.80 -> goes to human review
                explanation="Payment method query with low certainty.",
            )
        elif "urgent" in subject.lower() or "fraud" in body.lower():
            return ClassificationResult(
                category="Billing",
                priority="Urgent",
                confidence=0.95,
                explanation="Potential unauthorized charges.",
            )
        else:
            return ClassificationResult(
                category="Other",
                priority="Medium",
                confidence=0.85,
                explanation="General inquiry.",
            )

    classifier.classify.side_effect = side_effect
    return classifier


def test_load_and_validate_csv_success(sample_csv_data):
    processor = TicketProcessor()
    buf = io.StringIO(sample_csv_data)
    valid, errors = processor.load_and_validate_csv(buf)
    assert valid is True
    assert len(errors) == 0
    assert len(processor.tickets) == 3


def test_load_and_validate_csv_missing_columns():
    invalid_csv = "id,customer,subject\nT-0001,Emma,Wrong item"
    processor = TicketProcessor()
    buf = io.StringIO(invalid_csv)
    valid, errors = processor.load_and_validate_csv(buf)
    assert valid is False
    assert any("Missing required columns" in err for err in errors)


def test_all_five_categories_supported():
    expected_categories = {"Billing", "Technical", "Account", "Shipping", "Other"}
    assert set(ALLOWED_CATEGORIES) == expected_categories


def test_all_four_priorities_supported():
    expected_priorities = {"Low", "Medium", "High", "Urgent"}
    assert set(ALLOWED_PRIORITIES) == expected_priorities


def test_confidence_based_routing(mock_classifier):
    processor = TicketProcessor(classifier=mock_classifier)
    csv_data = (
        "id,received_at,customer,subject,body\n"
        "T-0001,2026-11-16 07:37,Emma,Order,Order arrived with EU plug\n"
        "T-0002,2026-11-16 07:49,Mateo,Payment,Can I pay with bank transfer?\n"
    )
    processor.load_and_validate_csv(io.StringIO(csv_data))
    processor.process_all_tickets(confidence_threshold=0.80)

    # T-0001: confidence 0.92 >= 0.80 -> automatic classification (needs_review == "no")
    res1 = processor.results["T-0001"]
    assert res1["needs_review"] == "no"
    assert res1["ai_category"] == "Shipping"
    assert res1["final_category"] == "Shipping"

    # T-0002: confidence 0.75 < 0.80 -> human review (needs_review == "yes")
    res2 = processor.results["T-0002"]
    assert res2["needs_review"] == "yes"
    assert "Low confidence" in res2["review_reason"]


def test_empty_ticket_body_routes_to_human_review(mock_classifier):
    processor = TicketProcessor(classifier=mock_classifier)
    csv_data = "id,received_at,customer,subject,body\nT-0093,2026-11-16 08:00,Ghost,(no subject),\n"
    processor.load_and_validate_csv(io.StringIO(csv_data))
    processor.process_all_tickets()

    res = processor.results["T-0093"]
    assert res["needs_review"] == "yes"
    assert "Empty ticket body" in res["review_reason"]
    # Classifier shouldn't be called for empty body
    mock_classifier.classify.assert_not_called()


def test_conservative_escalation_for_urgent(mock_classifier):
    processor = TicketProcessor(classifier=mock_classifier)
    csv_data = "id,received_at,customer,subject,body\nT-0008,2026-11-16 08:38,Fatima,Urgent help,Someone is using my saved card\n"
    processor.load_and_validate_csv(io.StringIO(csv_data))
    processor.process_all_tickets()

    res = processor.results["T-0008"]
    # Despite confidence 0.95, Urgent / fraud tickets must route to human review
    assert res["needs_review"] == "yes"
    assert "Conservative escalation" in res["review_reason"]


def test_long_ticket_message_handling():
    classifier = TicketClassifier()
    long_body = "Error log line\n" * 2000  # ~30,000 chars
    result = classifier.classify("T-TEST", "Crash report", long_body)
    assert result is not None
    assert result.category in ALLOWED_CATEGORIES
    assert result.priority in ALLOWED_PRIORITIES


def test_api_failure_handling_and_retries():
    failing_classifier = MagicMock(spec=TicketClassifier)
    failing_classifier.model = "failing-model"
    failing_classifier.classify.side_effect = Exception("API Connection Timeout")

    processor = TicketProcessor(classifier=failing_classifier)
    csv_data = "id,received_at,customer,subject,body\nT-FAIL,2026-11-16 09:00,User,Bug,App crashed\n"
    processor.load_and_validate_csv(io.StringIO(csv_data))

    with patch("time.sleep", return_value=None):
        processor.process_all_tickets()

    res = processor.results["T-FAIL"]
    assert res["status"] == "failed"
    assert res["needs_review"] == "yes"
    assert "API failure" in res["review_reason"]
    assert failing_classifier.classify.call_count == 3  # MAX_RETRIES


def test_human_review_correction_preserves_ai_prediction(mock_classifier):
    processor = TicketProcessor(classifier=mock_classifier)
    csv_data = "id,received_at,customer,subject,body\nT-0002,2026-11-16 07:49,Mateo,Payment,Can I pay with bank transfer?\n"
    processor.load_and_validate_csv(io.StringIO(csv_data))
    processor.process_all_tickets()

    # Before review:
    res = processor.results["T-0002"]
    assert res["ai_category"] == "Billing"
    assert res["ai_priority"] == "Low"
    assert res["is_human_reviewed"] is False

    # Human reviewer corrects to Account / Medium
    success = processor.apply_human_review("T-0002", "Account", "Medium")
    assert success is True

    # After review:
    assert res["is_human_reviewed"] is True
    assert res["human_category"] == "Account"
    assert res["human_priority"] == "Medium"
    assert res["final_category"] == "Account"
    assert res["final_priority"] == "Medium"
    # Original AI prediction is preserved
    assert res["ai_category"] == "Billing"
    assert res["ai_priority"] == "Low"


def test_export_results_csv_schema_and_rows(tmp_path, mock_classifier):
    processor = TicketProcessor(classifier=mock_classifier)
    csv_data = (
        "id,received_at,customer,subject,body\n"
        "T-0001,2026-11-16 07:37,Emma,Order,Order arrived with EU plug\n"
        "T-0002,2026-11-16 07:49,Mateo,Payment,Can I pay with bank transfer?\n"
    )
    processor.load_and_validate_csv(io.StringIO(csv_data))
    processor.process_all_tickets()

    out_file = str(tmp_path / "results.csv")
    df = processor.export_results_csv(out_file)

    # 1. Exactly four columns in exact order
    assert list(df.columns) == ["id", "category", "priority", "needs_review"]
    # 2. Exactly one row per input ticket
    assert len(df) == 2
    # 3. Preserve original ticket ID
    assert list(df["id"]) == ["T-0001", "T-0002"]
    # 4. needs_review only "yes" or "no"
    assert set(df["needs_review"]).issubset({"yes", "no"})
    # 5. T-0001 was automatic -> category & priority populated
    row1 = df[df["id"] == "T-0001"].iloc[0]
    assert row1["needs_review"] == "no"
    assert row1["category"] == "Shipping"
    assert row1["priority"] == "Medium"
    # 6. T-0002 was review and unreviewed -> filled with placeholder message
    row2 = df[df["id"] == "T-0002"].iloc[0]
    assert row2["needs_review"] == "yes"
    assert row2["category"] == "Pending Review"
    assert row2["priority"] == "Pending Review"


def test_export_report_json_format(tmp_path, mock_classifier):
    processor = TicketProcessor(classifier=mock_classifier)
    csv_data = (
        "id,received_at,customer,subject,body\n"
        "T-0001,2026-11-16 07:37,Emma,Order,Order arrived with EU plug\n"
    )
    processor.load_and_validate_csv(io.StringIO(csv_data))
    processor.process_all_tickets()

    report_path = str(tmp_path / "report.json")
    report = processor.export_report_json(report_path)

    assert "metrics" in report
    assert "distributions" in report
    assert "accuracy_notice" in report
    metrics = report["metrics"]
    assert metrics["total_tickets"] == 1
    assert metrics["successfully_classified"] == 1
    assert "accuracy" not in metrics  # accuracy should NOT be claimed without ground truth!


def test_full_dataset_300_tickets():
    """Verify loading the actual dataset file with 300 tickets."""
    actual_csv_path = os.path.join(
        os.path.dirname(__file__), "..", "candidate", "tickets.csv"
    )
    assert os.path.exists(actual_csv_path), "tickets.csv must exist in candidate directory"

    processor = TicketProcessor()
    with open(actual_csv_path, "r", encoding="utf-8") as f:
        valid, errors = processor.load_and_validate_csv(f)

    assert valid is True
    assert len(errors) == 0
    assert len(processor.tickets) == 300
    ids = [t["id"] for t in processor.tickets]
    assert len(set(ids)) == 300, "All 300 ticket IDs must be unique"
