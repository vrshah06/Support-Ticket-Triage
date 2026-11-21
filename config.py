import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Allowed labels as strictly specified by assessment
ALLOWED_CATEGORIES = ["Billing", "Technical", "Account", "Shipping", "Other"]
ALLOWED_PRIORITIES = ["Low", "Medium", "High", "Urgent"]

# Default thresholds and model settings
DEFAULT_CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "0.80"))
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Retry and concurrency settings
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
MAX_CONCURRENT_WORKERS = 8

# Conservative escalation rules
# LLM self-reported confidence is not a calibrated probability of correctness.
# Urgent or high-risk issues require human oversight.
ESCALATE_PRIORITIES = ["Urgent"]
CRITICAL_KEYWORDS = [
    "unauthorised", "unauthorized", "fraud", "hacked", "stolen",
    "lockout", "locked out", "clinic", "hospital", "supply room",
    "emergency", "lawsuit", "legal action", "police", "breach"
]

# Max characters of body to send to LLM (prevents context overflow on logs)
MAX_BODY_CHARS = 4000
