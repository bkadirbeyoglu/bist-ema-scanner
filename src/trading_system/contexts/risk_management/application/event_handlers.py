# src/trading_system/contexts/risk_management/application/event_handlers.py
"""
Event handlers for Risk Management context.
"""

import logging
from decimal import Decimal

from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.contexts.order_management.domain.events import (
    OrderCreatedEvent
)
from trading_system.contexts.risk_management.domain.events import (
    RiskLimitBreachedEvent,
    RiskCheckPassedEvent
)

logger = logging.getLogger(__name__)


class RiskManagementEventHandlers:
    """Event handlers for risk management."""
    
    def __init__(self, event_bus: InMemoryEventBus):
        self.event_bus = event_bus
        self.max_order_size = Decimal("10000")
        self._subscribe_to_events()
    
    def _subscribe_to_events(self):
        """Subscribe to events from other contexts."""
        self.event_bus.subscribe(
            OrderCreatedEvent,
            self.on_order_created
        )
        logger.info("Risk management event handlers subscribed")
    
    async def on_order_created(self, event: OrderCreatedEvent):
        """
        Validate order against risk limits.
        
        RISK CHECKS:
        1. Order size within limits?
        2. Would this breach position limits?
        3. Portfolio exposure within limits?
        """
        logger.info(
            f"Risk checking order {event.order_id}: "
            f"{event.symbol} {event.notional_value}"
        )
        
        # Check order size
        if event.notional_value > self.max_order_size:
            logger.warning(
                f"Order {event.order_id} exceeds size limit: "
                f"${event.notional_value} > ${self.max_order_size}"
            )
            
            breach_event = RiskLimitBreachedEvent(
                event_id=event.event_id,
                timestamp=event.timestamp,
                version=1,
                portfolio_id="default",
                limit_type="order_size",
                limit_value=self.max_order_size,
                current_value=event.notional_value,
                breach_percentage=(
                    (event.notional_value - self.max_order_size) 
                    / self.max_order_size * 100
                ),
                severity="critical",
                details={"order_id": event.order_id}
            )
            
            await self.event_bus.publish(breach_event)
            return
        
        # All checks passed
        logger.info(f"Order {event.order_id} passed risk checks")
        
        passed_event = RiskCheckPassedEvent(
            event_id=event.event_id,
            timestamp=event.timestamp,
            version=1,
            order_id=event.order_id,
            checks_performed=["order_size"]
        )
        
        await self.event_bus.publish(passed_event)