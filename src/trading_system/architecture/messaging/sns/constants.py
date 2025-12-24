"""
SNS configuration constants.

Domain constants (topic names) are hardcoded - they're the same across all environments.
Environment config (endpoint, region) comes from environment variables.
"""

import os
from typing import Final

# -----------------------------------------------------------------------------
# Domain Constants - Same everywhere, part of the system's design
# -----------------------------------------------------------------------------
TOPIC_PRICE_UPDATES: Final[str] = "price-updates"
TOPIC_ORDER_EVENTS: Final[str] = "order-events"
TOPIC_TRADE_SIGNALS: Final[str] = "trade-signals"
DEFAULT_MESSAGE_GROUP_ID: Final[str] = "trading-system"

# -----------------------------------------------------------------------------
# Environment Configuration - Changes per deployment (local, staging, prod)
# -----------------------------------------------------------------------------
# AWS_ENDPOINT_URL: Set to LocalStack URL for local dev, leave unset for real AWS
# AWS_REGION: Defaults to us-east-1, override for other regions
AWS_ENDPOINT_URL: Final[str | None] = os.getenv("AWS_ENDPOINT_URL", "http://localhost:4566")
AWS_REGION: Final[str] = os.getenv("AWS_REGION", "us-east-1")