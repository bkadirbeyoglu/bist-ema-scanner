"""
In-Memory Event Bus Implementation.

This is our first implementation - a simple in-memory event bus that will
later be replaced with Amazon SQS (and eventually Kafka in Day 10). 

Why start with in-memory?
1. Simpler to test and debug
2. Faster development cycle
3. Same interface as SQS version (easy to swap later)
4. No AWS infrastructure needed for development

The Event Bus pattern:
- Publishers emit events without knowing subscribers
- Subscribers register handlers for event types
- Bus routes events to appropriate handlers
- Similar to Observer pattern but more flexible

Migration path:
- Days 2-3: In-memory event bus (this implementation)
- Days 4-9: Amazon SQS for distributed messaging
- Day 10: Migrate to Apache Kafka for higher throughput
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import (
    Dict, List, Callable, Type, TypeVar, Optional, 
    Awaitable, Any, Set
)
from dataclasses import dataclass, field
from datetime import datetime

from trading_system.shared_kernel.events import BaseEvent

# Logging best practices:
# - Use module-level logger
# - Logger name matches module path
# - Allows hierarchical configuration
logger = logging.getLogger(__name__)

# Generic type for event handling
# Allows type-safe generic functions
EventType = TypeVar('EventType', bound=BaseEvent)


# ============================================
# SUBSCRIPTION MANAGEMENT
# ============================================

@dataclass
class Subscription:
    """
    Represents a subscription to an event type.
    
    Encapsulates:
    - What event type to listen for
    - What handler to call
    - Optional filtering logic
    - Unique identifier for unsubscribe
    """
    subscription_id: str
    event_type: Type[BaseEvent]  # Type[X] means "the class X itself, not an instance"
    handler: Callable[[BaseEvent], Awaitable[None]]  # Async function signature
    filter_predicate: Optional[Callable[[BaseEvent], bool]] = None
    
    async def handle(self, event: BaseEvent) -> None:
        """
        Execute the handler if the filter passes.
        
        This method:
        1. Checks filter (if any)
        2. Calls handler
        3. Handles errors gracefully
        
        Note: Methods can be async in Python!
        Just add 'async' and use 'await' inside
        """
        # Check filter if one exists
        if self.filter_predicate and not self.filter_predicate(event):
            return  # Skip this handler
        
        try:
            # await is crucial here - handler is async
            await self.handler(event)
        except Exception as e:
            # Log error but don't crash
            # __name__ in f-string gets function name
            logger.error(
                "Error in handler %s for event %s: %s",
                self.handler.__name__, event.event_id, str(e)
            )
            # In production, might want to:
            # - Send to error tracking (Sentry)
            # - Increment error metrics
            # - Trigger alerts if error rate too high


class InMemoryEventBus:
    """
    In-memory implementation of an event bus.
    
    This implementation:
    - Routes events to registered handlers
    - Executes handlers concurrently
    - Isolates handler failures
    - Tracks statistics
    
    Thread-safety note:
    This implementation is NOT thread-safe, only async-safe.
    For threads, would need locks around subscription modifications.
    """
    
    def __init__(self):
        """
        Initialize the event bus.
        
        defaultdict is a dict subclass that:
        - Provides default value for missing keys
        - Prevents KeyError on access
        - Cleaner than checking if key exists
        
        Compare:
        # Without defaultdict:
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(handler)
        
        # With defaultdict:
        self._subscriptions[event_type].append(handler)  # Auto-creates list
        """
        # Type annotations for clarity
        # Dict[Type[BaseEvent], List[Subscription]] means:
        # - Keys are event classes (not instances)
        # - Values are lists of Subscription objects
        self._subscriptions: Dict[Type[BaseEvent], List[Subscription]] = defaultdict(list)
        
        # Registry for quick lookup by ID
        self._subscription_registry: Dict[str, Subscription] = {}
        
        # Initialize statistics counters in __init__ to avoid Pylint warnings
        # These track metrics for monitoring
        self._event_count: int = 0
        self._error_count: int = 0
    
    def subscribe(
        self,
        event_type: Type[EventType],
        handler: Callable[[EventType], Awaitable[None]],
        filter_predicate: Optional[Callable[[EventType], bool]] = None
    ) -> str:
        """
        Subscribe a handler to an event type.
        
        Parameters explained:
        
        event_type: Type[EventType]
        - Type[X] means "the class X, not an instance"
        - We pass OrderCreatedEvent, not OrderCreatedEvent()
        
        handler: Callable[[EventType], Awaitable[None]]
        - Callable = a function that can be called
        - [[EventType], ...] = takes one parameter of type EventType
        - Awaitable[None] = async function that returns None when awaited
        - Full meaning: an async function like: async def handler(event: EventType) -> None
        
        Example valid handler:
            async def process_order(event: OrderCreatedEvent) -> None:
                await save_to_db(event)  # No return value
        
        Invalid handlers:
            def sync_handler(event): ...  # Not async!
            async def wrong_return(event) -> str: ...  # Returns value!
        
        filter_predicate: Optional[Callable[[EventType], bool]]
        - Optional sync function that returns True/False
        - Used to conditionally handle events
        
        Returns:
        - Unique subscription ID for later unsubscribe
        """
        # Generate unique ID for this subscription
        subscription_id = str(uuid.uuid4())
        
        # Create subscription object
        subscription = Subscription(
            subscription_id=subscription_id,
            event_type=event_type,
            handler=handler,
            filter_predicate=filter_predicate
        )
        
        # Add to both data structures
        # 1. By event type (for publishing)
        self._subscriptions[event_type].append(subscription)
        # 2. By ID (for unsubscribe)
        self._subscription_registry[subscription_id] = subscription
        
        # Debug logging with lazy % formatting (Pylint best practice)
        # Lazy formatting means the string is only built if logging is enabled
        logger.debug(
            "Subscribed %s to %s with ID %s",
            handler.__name__, event_type.__name__, subscription_id
        )
        
        return subscription_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription by ID.
        
        Why return bool?
        - True = successfully unsubscribed
        - False = subscription not found
        - Allows caller to handle missing subscriptions
        
        This is idempotent - calling twice is safe
        """
        # Check if subscription exists
        if subscription_id not in self._subscription_registry:
            logger.warning("Subscription %s not found", subscription_id)
            return False
        
        # Get subscription details
        subscription = self._subscription_registry[subscription_id]
        
        # Remove from event type list
        self._subscriptions[subscription.event_type].remove(subscription)
        
        # Remove from registry
        del self._subscription_registry[subscription_id]
        
        logger.debug("Unsubscribed %s", subscription_id)
        return True
    
    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to all registered handlers.
        
        This method:
        1. Finds matching handlers
        2. Executes them concurrently
        3. Isolates failures
        4. Logs errors
        
        Key design decisions:
        - Handlers run concurrently (not sequentially)
        - One handler failure doesn't stop others
        - No guarantee of handler execution order
        - Fire-and-forget (doesn't wait for handlers)
        """
        self._event_count += 1
        
        # Find all matching handlers
        handlers_to_execute: List[Subscription] = []
        
        # Check each subscription type
        # isinstance allows for inheritance - subscribing to BaseEvent
        # receives ALL events (useful for logging, audit, etc.)
        for event_type, subscriptions in self._subscriptions.items():
            if isinstance(event, event_type):
                handlers_to_execute.extend(subscriptions)
        
        if not handlers_to_execute:
            logger.debug("No handlers for event type %s", type(event).__name__)
            return
        
        # Create async tasks for all handlers
        # List comprehension builds list of coroutines (not yet running!)
        # 
        # This is equivalent to:
        # tasks = []
        # for subscription in handlers_to_execute:
        #     coroutine = self._execute_handler(subscription, event)
        #     tasks.append(coroutine)  # Coroutine created but NOT running yet
        #
        # Each self._execute_handler() call returns a coroutine object
        # The coroutine doesn't start running until awaited
        tasks = [
            self._execute_handler(subscription, event)
            for subscription in handlers_to_execute
        ]
        
        # Execute all handlers concurrently
        # asyncio.gather() runs multiple coroutines concurrently
        # return_exceptions=True means:
        # - Exceptions are returned as results, not raised
        # - One failure doesn't cancel others
        # - We can log errors afterward
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # * operator unpacks list into arguments:
        # gather(*[a, b, c]) becomes gather(a, b, c)
        
        # Check for errors in results
        for result in results:
            if isinstance(result, Exception):
                self._error_count += 1
                logger.error("Handler error: %s", result)
    
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
                "Handler %s processed event %s",
                subscription.handler.__name__, event.event_id
            )
        except Exception as e:
            # Log with full stack trace using lazy formatting
            # exc_info=True adds traceback to log
            logger.error(
                "Error in handler %s: %s",
                subscription.handler.__name__, str(e),
                exc_info=True
            )
            # Re-raise so gather() can catch
            # This allows us to track errors in results
            raise
    
    def clear(self) -> None:
        """
        Clear all subscriptions.
        
        Useful for:
        - Testing (clean state between tests)
        - Shutdown/cleanup
        - Reset after error condition
        
        Note: This is synchronous (not async)
        because it doesn't do any I/O
        """
        self._subscriptions.clear()
        self._subscription_registry.clear()
        self._event_count = 0
        self._error_count = 0
        logger.debug("Event bus cleared")
    
    def get_stats(self) -> dict:
        """
        Get statistics about the event bus.
        
        Useful for:
        - Monitoring/metrics
        - Debugging
        - Performance analysis
        
        Could be @property but we use method to indicate
        this performs calculation (not just field access)
        """
        return {
            'total_events_published': self._event_count,
            'total_errors': self._error_count,
            'active_subscriptions': len(self._subscription_registry),
            'subscribed_event_types': len(self._subscriptions)
        }