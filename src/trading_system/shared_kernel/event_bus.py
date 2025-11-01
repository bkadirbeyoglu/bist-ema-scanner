"""
In-Memory Event Bus Implementation.

This implementation routes events within a single process.
Perfect for development and testing, but doesn't support distributed systems.
"""

import asyncio
import logging
from collections import defaultdict
from typing import Dict, List, Callable, Type, Optional, Awaitable
from dataclasses import dataclass
from uuid import uuid4

from trading_system.shared_kernel.events import BaseEvent
from trading_system.shared_kernel.event_bus_protocol import EventBus  # ← Import ABC
# ← Add this import:
from trading_system.shared_kernel.event_bus_protocol import EventBus as EventBusProtocol

logger = logging.getLogger(__name__)


@dataclass
class Subscription:
    """Represents a subscription to an event type."""
    subscription_id: str
    event_type: Type[BaseEvent]
    handler: Callable[[BaseEvent], Awaitable[None]]
    filter_predicate: Optional[Callable[[BaseEvent], bool]] = None
    
    async def handle(self, event: BaseEvent) -> None:
        """Execute the handler if the filter passes."""
        if self.filter_predicate and not self.filter_predicate(event):
            return
        
        try:
            await self.handler(event)
        except Exception as e:
            logger.error(
                "Error in handler %s for event %s: %s",
                self.handler.__name__, event.event_id, str(e)
            )


class InMemoryEventBus:  # ← No inheritance needed!
    """
    In-memory implementation of EventBus protocol.
    
    This class automatically conforms to the EventBus protocol by implementing
    all required methods. No explicit inheritance needed thanks to Protocol!
    
    Characteristics:
    - Synchronous (zero latency)
    - Not persistent (lost on crash)
    - Single-process only
    
    Perfect for:
    - Development and testing
    - Monolithic applications
    - When performance is critical
    """
    
    def __init__(self) -> None:
        """Initialize the in-memory event bus."""
        self._subscriptions: Dict[Type[BaseEvent], List[Subscription]] = defaultdict(list)
        self._subscription_registry: Dict[str, Subscription] = {}
        self._running = False
        self._event_count = 0
        self._error_count = 0
    
    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to all subscribers.
        
        Events are delivered immediately to all handlers in the current process.
        Handlers run concurrently but failures are isolated.
        """
        if not isinstance(event, BaseEvent):
            raise TypeError(f"Event must be a BaseEvent, got {type(event)}")
        
        subscriptions = self._subscriptions.get(type(event), [])
        
        if not subscriptions:
            logger.debug(f"No subscribers for {type(event).__name__}")
            return
        
        self._event_count += 1
        
        # Create async tasks for all handlers
        # List comprehension builds list of coroutines
        tasks = [
            self._execute_handler(subscription, event)
            for subscription in subscriptions
        ]
        
        # Execute all handlers concurrently
        # gather() runs them in parallel and waits for all to complete
        # return_exceptions=True prevents one failure from cancelling others
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Count errors
        for result in results:
            if isinstance(result, Exception):
                self._error_count += 1
        
        logger.debug(
            f"Published {type(event).__name__} to {len(subscriptions)} subscribers"
        )
    
    def subscribe(
        self,
        event_type: Type[BaseEvent],
        handler: Callable[[BaseEvent], Awaitable[None]],
        filter_predicate: Optional[Callable[[BaseEvent], bool]] = None
    ) -> str:
        """Subscribe a handler to an event type."""
        subscription_id = str(uuid4())
        
        subscription = Subscription(
            subscription_id=subscription_id,
            event_type=event_type,
            handler=handler,
            filter_predicate=filter_predicate
        )
        
        self._subscriptions[event_type].append(subscription)
        self._subscription_registry[subscription_id] = subscription
        
        logger.debug(
            f"Subscribed handler {handler.__name__} to {event_type.__name__}"
        )
        
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """Unsubscribe a handler."""
        subscription = self._subscription_registry.pop(subscription_id, None)
        
        if not subscription:
            return False
        
        # Remove from subscriptions list
        self._subscriptions[subscription.event_type].remove(subscription)
        
        logger.debug(f"Unsubscribed {subscription_id}")
        return True
    
    async def start(self) -> None:
        """
        Start the event bus.
        
        For in-memory implementation, this is a no-op since there are
        no background tasks or connections to manage.
        """
        self._running = True
        logger.info("InMemoryEventBus started")
    
    async def stop(self) -> None:
        """
        Stop the event bus.
        
        For in-memory implementation, just mark as stopped.
        """
        self._running = False
        logger.info(
            f"InMemoryEventBus stopped. "
            f"Events processed: {self._event_count}, Errors: {self._error_count}"
        )
    
    def clear(self) -> None:
        """
        Clear all subscriptions and reset statistics.
        
        Useful for:
        - Testing (clean state between tests)
        - Shutdown/cleanup
        - Reset after error condition
        
        Note: This is synchronous (not async) because it doesn't do any I/O
        """
        self._subscriptions.clear()
        self._subscription_registry.clear()
        self._event_count = 0
        self._error_count = 0
        logger.debug("Event bus cleared")
    
    async def _execute_handler(
        self, 
        subscription: Subscription, 
        event: BaseEvent
    ) -> None:
        """
        Execute a single handler with error handling.
        
        Leading underscore (_) indicates:
        - Private/internal method
        - Not part of public API
        - May change without notice
        - Should not be called directly by users
        
        This separation of concerns:
        - Public method (publish) handles routing
        - Private method handles execution
        - Easier to test and modify
        """
        try:
            # Delegate to subscription's handle method
            await subscription.handle(event)
            logger.debug(
                f"Handler {subscription.handler.__name__} processed event {event.event_id}"
            )
        except Exception as e:
            # Log with full stack trace
            # exc_info=True adds traceback to log
            logger.error(
                f"Error in handler {subscription.handler.__name__}: {e}",
                exc_info=True
            )
            # Re-raise so gather() can catch
            # This allows us to track errors in results
            raise
    
    def get_stats(self) -> dict:
        """
        Get statistics about the event bus.
        
        Useful for:
        - Monitoring/metrics
        - Debugging
        - Performance analysis
        """
        return {
            'total_events_published': self._event_count,
            'total_errors': self._error_count,
            'active_subscriptions': len(self._subscription_registry),
            'subscribed_event_types': len(self._subscriptions),
            'running': self._running
        }