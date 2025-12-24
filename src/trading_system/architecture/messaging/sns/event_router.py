"""
Event Router with singledispatch.

Provides type-based event routing using Python's functools.singledispatch.
This pattern enables clean, extensible event handling without if-elif chains.

Usage:
    # The singledispatch function handles routing automatically
    result = handle_event(price_event)      # Calls price handler
    result = handle_event(order_event)      # Calls order handler
    
    # Or use EventRouter for stats tracking
    router = EventRouter()
    result = router.route(event)
    print(router.get_stats())
"""

import logging
from collections import Counter
from functools import singledispatch
from typing import Any

from trading_system.shared_kernel.sns_events import OrderCreatedEvent
from trading_system.shared_kernel.sns_events import OrderFilledEvent
from trading_system.shared_kernel.sns_events import PriceUpdatedEvent


logger = logging.getLogger(__name__)


# =============================================================================
# singledispatch Event Handler
# =============================================================================
# This is the core pattern - a single function that dispatches to
# type-specific implementations based on the argument type.

@singledispatch
def handle_event(event: Any) -> dict[str, Any]:
    """
    Route an event to its handler based on type.

    This base function handles unknown types. Specific handlers are registered 
    with @handle_event.register(Type).
    """
    raise NotImplementedError(f"No handler registered for event type: {type(event).__name__}")

@handle_event.register(PriceUpdatedEvent)
def _(event: PriceUpdatedEvent) -> dict[str, Any]:
    """Handle PriceUpdatedEvent - called automatically by singledispatch."""
    logger.debug(f"Handling price update: {event.symbol} @ {event.price}")
    return {
        "handler": "price_updated",
        "symbol": event.symbol,
        "price": event.price,
        "timestamp": event.timestamp.isoformat(),
    }

@handle_event.register(OrderCreatedEvent)
def _(event: OrderCreatedEvent) -> dict[str, Any]:
    """Handle OrderCreatedEvent - called when a new order is created."""
    logger.debug(f"Handling order created: {event.order_id}")
    return {
        "handler": "order_created",
        "order_id": str(event.order_id),
        "symbol": event.symbol,
        "side": event.side,
        "quantity": event.quantity,
        "order_type": event.order_type,
    }

@handle_event.register(OrderFilledEvent)
def _(event: OrderFilledEvent) -> dict[str, Any]:
    """Handle OrderFilledEvent - called when an order is executed."""
    logger.debug(f"Handling order filled: {event.order_id}")
    return {
        "handler": "order_filled",
        "order_id": str(event.order_id),
        "symbol": event.symbol,
        "side": event.side,
        "quantity": event.quantity,
        "fill_price": event.fill_price,
    }


# =============================================================================
# EventRouter Class (Optional Wrapper for Stats)
# =============================================================================

class EventRouter:
    """
    Thin wrapper around handle_event that adds statistics tracking.
    
    Use this when you need to track how many events were processed.
    For simple routing, just call handle_event() directly.
    """

    def __init__(self) -> None:
        self._processed_count = 0
        self._error_count = 0
        self._type_counts: Counter[str] = Counter()

    @property
    def processed_count(self) -> int:
        """Total events processed."""
        return self._processed_count

    @property
    def error_count(self) -> int:
        """Events that resulted in errors."""
        return self._error_count

    def get_stats(self) -> dict[str, int]:
        """Get processing counts by event type."""
        return dict(self._type_counts)

    def route(self, event: Any) -> dict[str, Any]:
        """Route event and track statistics."""
        event_type_name = type(event).__name__
        
        try:
            result = handle_event(event)
            self._processed_count += 1
            self._type_counts[event_type_name] += 1
            return result
        
        except Exception as e:
            self._error_count += 1
            logger.error(f"Error routing {event_type_name}: {e}")
            return {"error": True, "event_type": event_type_name, "message": str(e)}
        
    def list_registered_handlers() -> dict[str, str]:
        """
        List all registered singledispatch handlers.
        
        Useful for debugging and introspection.
        
        Returns:
            Dictionary mapping event type names to handler function names
        """
        return {
            cls.__name__: func.__name__
            for cls, func in handle_event.registry.items()
            if cls is not object
        }
