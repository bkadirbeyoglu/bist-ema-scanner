"""
Event handlers for Portfolio Management context.

Event handlers are the "ears" of a bounded context - they listen for events
from other contexts and react appropriately.
"""

import logging

from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.contexts.order_management.domain.events import (
    OrderCreatedEvent  # We'll use this existing event for demonstration
)
# Note: OrderFilledEvent and PriceUpdatedEvent will be created in future sessions
# For now, we'll demonstrate with OrderCreatedEvent

logger = logging.getLogger(__name__)


class PortfolioEventHandlers:
    """
    Event handlers for portfolio management.
    
    Key Principles:
    --------------
    1. Single Responsibility: Each handler does one thing
    2. Idempotency: Handlers can be called multiple times safely
    3. Error Isolation: One handler failure doesn't affect others
    4. Async Processing: Handlers don't block each other
    """
    def __init__(self, event_bus: InMemoryEventBus):
        self.event_bus = event_bus
        self._subscribe_to_events()

    def _subscribe_to_events(self):
        """
        Subscribe to relevant events from other contexts.
        
        We subscribe to event TYPES, not specific events.
        When any event of that type is published, our handler is called.
        """
        # For now, subscribe to OrderCreatedEvent
        # In future sessions, we'll add OrderFilledEvent and PriceUpdatedEvent
        self.event_bus.subscribe(
            OrderCreatedEvent,
            self.on_order_created
        )
        
        logger.info("Portfolio event handlers subscribed")
    
    async def on_order_created(self, event: OrderCreatedEvent):
        """
        Handle order created event - prepare for position tracking.
        
        Event Flow:
        ----------
        1. Order Management: Order is created
        2. Order Management: Publishes OrderCreatedEvent
        3. Event Bus: Routes event to all subscribers
        4. This Handler: Prepares portfolio for potential fill
        
        Note: In production, we'd also have on_order_filled() handler
        that updates positions when orders execute.
        """
        logger.info(
            f"Portfolio handling OrderCreatedEvent: {event.order_id} "
            f"{event.symbol} {event.quantity}"
        )
        
        try:
            # In real implementation:
            # 1. Load portfolio aggregate
            # 2. Mark funds as reserved for this order
            # 3. Persist changes
            
            logger.info(f"Portfolio prepared for order {event.symbol}")
            
        except Exception as e:
            # Log error but don't raise - other handlers should still run
            logger.error(f"Failed to process order creation: {e}")
    
    # Template for future OrderFilledEvent handler (to be implemented later)
    # async def on_order_filled(self, event: OrderFilledEvent):
    #     """Handle order filled event - update positions when orders execute."""
    #     logger.info(f"Portfolio handling OrderFilledEvent: {event.order_id}")
    #     # Update position logic here
    
    # Template for future PriceUpdatedEvent handler (to be implemented later)
    # async def on_price_updated(self, event: PriceUpdatedEvent):
    #     """Handle price update event - recalculate portfolio values."""
    #     logger.info(f"Portfolio handling PriceUpdatedEvent: {event.symbol}")
    #     # Update portfolio value logic here