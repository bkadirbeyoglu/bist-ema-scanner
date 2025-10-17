# src/trading_system/contexts/risk_management/domain/events.py
"""
Domain events for Risk Management context.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Dict, Any, List

from trading_system.shared_kernel.events import BaseEvent


@dataclass(frozen=True)
class RiskCheckPassedEvent(BaseEvent):
    """
    Published when an order passes all risk checks.
    
    This event signals to other contexts that the order is safe
    to proceed with execution.
    """
    order_id: str
    checks_performed: List[str]  # e.g., ["order_size", "position_limit", "exposure"]


@dataclass(frozen=True)
class RiskLimitBreachedEvent(BaseEvent):
    """
    Published when an order violates risk limits.
    
    This is a critical event that should:
    - Prevent order execution
    - Alert risk managers
    - Be logged for compliance
    """
    portfolio_id: str
    limit_type: str  # e.g., "order_size", "position_limit", "daily_loss"
    limit_value: Decimal
    current_value: Decimal
    breach_percentage: Decimal
    severity: str  # "warning", "critical"
    details: Dict[str, Any]  # Additional context