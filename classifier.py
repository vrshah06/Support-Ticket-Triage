import re
import json
from typing import Optional, Literal
from pydantic import BaseModel, Field
import openai
from config import (
    ALLOWED_CATEGORIES,
    ALLOWED_PRIORITIES,
    DEFAULT_MODEL,
    MAX_BODY_CHARS,
    CRITICAL_KEYWORDS,
)

CategoryType = Literal["Billing", "Technical", "Account", "Shipping", "Other"]
PriorityType = Literal["Low", "Medium", "High", "Urgent"]


class ClassificationResult(BaseModel):
    category: CategoryType = Field(
        ...,
        description="The primary category of the support ticket: Billing, Technical, Account, Shipping, or Other",
    )
    priority: PriorityType = Field(
        ...,
        description="The urgency of the ticket: Low, Medium, High, or Urgent",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Confidence score from 0.0 to 1.0 reflecting certainty in the classification",
    )
    explanation: str = Field(
        ...,
        max_length=300,
        description="Concise rationale for the assigned category and priority",
    )


CLASSIFICATION_SYSTEM_PROMPT = """You are an expert AI customer support triage agent for an IoT and smart hardware / software company (Lumora).
Analyze the customer's support ticket (subject and body) and output a structured classification with:
1. category: EXACTLY one of: Billing, Technical, Account, Shipping, Other
2. priority: EXACTLY one of: Low, Medium, High, Urgent
3. confidence: A float between 0.0 and 1.0 representing your certainty
4. explanation: A concise explanation (1-2 sentences) justifying your choices.

Category Definitions:
- Billing: Payment issues, invoices, card updates, refunds, subscription charges, bank transfers, pricing.
- Technical: Firmware errors, device bugs, connectivity issues, camera feed errors, crash logs, sensor failures.
- Account: Password resets, 2FA issues, account deletion, profile changes, login lockouts.
- Shipping: Deliveries, tracking numbers, delayed packages, wrong items received, customs, missing parcels.
- Other: Reseller enquiries, general partnerships, compliments, non-technical feedback.

Priority Guidelines:
- Urgent: Active fraud/unauthorized charges, critical lockouts (e.g., clinic supply rooms), severe safety or operational blockage.
- High: Core product unusable without immediate workaround, persistent sync/handshake failures affecting main functionality.
- Medium: Normal support requests, feature bugs with workarounds, billing discrepancies.
- Low: General questions, invoice copy requests, reseller inquiries, feedback.

Be objective. If information is ambiguous, assign a lower confidence score (e.g. 0.50 - 0.75)."""


class TicketClassifier:
    """Handles AI ticket classification via OpenAI API or fallback heuristic."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key or ""
        self.model = model or DEFAULT_MODEL
        self._client: Optional[openai.OpenAI] = None
        if self.api_key:
            self._client = openai.OpenAI(api_key=self.api_key)

    def set_api_key(self, api_key: str):
        self.api_key = api_key
        self._client = openai.OpenAI(api_key=api_key) if api_key else None

    def classify(self, ticket_id: str, subject: str, body: str) -> ClassificationResult:
        """Classify a support ticket using OpenAI API or heuristic fallback."""
        clean_subject = (subject or "").strip()
        clean_body = (body or "").strip()

        # Check for empty body
        if not clean_body and not clean_subject:
            return ClassificationResult(
                category="Other",
                priority="Low",
                confidence=0.10,
                explanation="Ticket subject and body are both empty.",
            )

        # Truncate overly long body for prompt safety
        truncated_body = clean_body[:MAX_BODY_CHARS]
        if len(clean_body) > MAX_BODY_CHARS:
            truncated_body += f"\n... [Truncated: {len(clean_body)} total characters]"

        # Call OpenAI if client is available
        if self._client:
            return self._call_openai(ticket_id, clean_subject, truncated_body)

        # Otherwise use rule-based heuristic classifier
        return self._heuristic_classify(ticket_id, clean_subject, clean_body)

    def _call_openai(
        self, ticket_id: str, subject: str, body: str
    ) -> ClassificationResult:
        """Call OpenAI API with structured output."""
        user_message = f"Ticket ID: {ticket_id}\nSubject: {subject}\n\nBody:\n{body}"

        # Use OpenAI structured output parsing
        completion = self._client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {"role": "system", "content": CLASSIFICATION_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            response_format=ClassificationResult,
            temperature=0.0,
        )

        message = completion.choices[0].message
        if message.parsed:
            return message.parsed

        # Fallback to manual parsing if needed
        data = json.loads(message.content)
        return ClassificationResult(**data)

    def _heuristic_classify(
        self, ticket_id: str, subject: str, body: str
    ) -> ClassificationResult:
        """Rule-based heuristic classifier for offline testing, demos, or fallback."""
        text = f"{subject} {body}".lower()

        # Check for critical / urgent keywords first
        is_urgent = any(kw in text for kw in CRITICAL_KEYWORDS)

        # 1. Billing keywords
        billing_keywords = [
            "card", "payment", "bank transfer", "invoice", "refund", "subscription",
            "charge", "billing", "receipt", "plan", "cost", "price", "pay",
            "unauthorised", "unauthorized", "money"
        ]
        # 2. Account keywords
        account_keywords = [
            "password", "reset link", "login", "log in", "delete my account",
            "close my account", "2fa", "two-factor", "email settings", "profile",
            "credentials", "sign in"
        ]
        # 3. Shipping keywords
        shipping_keywords = [
            "order", "arrived", "plug", "delivered", "shipping", "courier",
            "tracking", "customs", "package", "dispatch", "wrong item", "delivery"
        ]
        # 4. Technical keywords
        technical_keywords = [
            "error", "ota.update", "net.mqtt", "hub.sync", "live view", "camera",
            "firmware", "bug", "crash", "handshake failed", "timeout", "offline",
            "disconnect", "sensor", "hardware", "device"
        ]
        # 5. Other keywords
        other_keywords = [
            "reseller", "partner", "business enquiry", "talk about", "distributor"
        ]

        scores = {
            "Billing": sum(1 for kw in billing_keywords if kw in text),
            "Account": sum(1 for kw in account_keywords if kw in text),
            "Shipping": sum(1 for kw in shipping_keywords if kw in text),
            "Technical": sum(1 for kw in technical_keywords if kw in text),
            "Other": sum(1 for kw in other_keywords if kw in text),
        }

        # Determine best category
        best_category = max(scores, key=scores.get)
        max_score = scores[best_category]

        if max_score == 0:
            category: CategoryType = "Other"
            confidence = 0.50
            explanation = "Ambiguous ticket text with no strong domain keywords."
        else:
            category: CategoryType = best_category  # type: ignore
            confidence = min(0.95, 0.70 + (max_score * 0.08))
            explanation = f"Classified based on keywords matched in ticket text (score={max_score})."

        # Determine priority
        if is_urgent:
            priority: PriorityType = "Urgent"
            confidence = max(0.85, confidence)
            explanation += " Urgent indicator detected (security, lockout, or active fraud)."
        elif any(w in text for w in ["cannot unlock", "supply room", "fail", "not working", "broken"]):
            priority: PriorityType = "High"
        elif any(w in text for w in ["invoice", "copy", "reseller", "enquiry", "minor", "receipt"]):
            priority: PriorityType = "Low"
        else:
            priority: PriorityType = "Medium"

        return ClassificationResult(
            category=category,
            priority=priority,
            confidence=round(confidence, 2),
            explanation=explanation,
        )
