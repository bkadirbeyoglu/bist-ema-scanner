"""
Event Bus Protocol - Defines the interface for event bus implementations.

This protocol uses structural subtyping (PEP 544) to define what it means
to "be an event bus" without requiring explicit inheritance.

Any class that implements these methods can be used as an EventBus,
making it easy to swap implementations (InMemory, SQS, Kafka, etc.)
"""

from typing import Protocol, Callable, Awaitable, Type, Optional, runtime_checkable

from trading_system.shared_kernel.events import BaseEvent


@runtime_checkable  # ← Allows isinstance() checks at runtime
class EventBus(Protocol):
    """
    Protocol defining the event bus interface.
    
    This is Python's answer to interfaces in other languages, but more flexible:
    - No explicit inheritance required
    - Static type checking via mypy
    - Runtime checking via @runtime_checkable
    
    Any class implementing these methods IS an EventBus, regardless of inheritance.
    
    Usage:
        # Implementation doesn't need to inherit:
        class MyEventBus:
            async def publish(self, event): ...
            def subscribe(self, event_type, handler): ...
            async def start(self): ...
            async def stop(self): ...
        
        # Type checker knows MyEventBus IS an EventBus:
        bus: EventBus = MyEventBus()  # ✓ Valid!
        
        # Runtime check also works:
        assert isinstance(bus, EventBus)  # ✓ True!
    """
    
    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to the bus.
        
        Args:
            event: Domain event to publish
        
        Behavior:
            - InMemory: Immediately invokes handlers
            - SQS: Sends to queue, handlers invoked async
            - Kafka: Sends to topic partition
        """
        ...
    
    def subscribe(
        self,
        event_type: Type[BaseEvent],
        handler: Callable[[BaseEvent], Awaitable[None]],
        filter_predicate: Optional[Callable[[BaseEvent], bool]] = None
    ) -> str:
        """
        Subscribe to an event type.
        
        Args:
            event_type: The event class to subscribe to
            handler: Async function to handle the event
            filter_predicate: Optional filter (only handle if predicate returns True)
        
        Returns:
            Subscription ID (for unsubscribe)
        
        Examples:
            # Simple subscription
            bus.subscribe(OrderCreatedEvent, handle_order)
            
            # With filter
            bus.subscribe(
                OrderCreatedEvent,
                handle_large_order,
                filter_predicate=lambda e: e.quantity > 1000
            )
        """
        ...
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription.
        
        Args:
            subscription_id: ID returned from subscribe()
        
        Returns:
            True if found and removed, False otherwise
        """
        ...
    
    async def start(self) -> None:
        """
        Start the event bus.
        
        Behavior:
            - InMemory: No-op (always ready)
            - SQS: Start consumer tasks
            - Kafka: Connect to brokers, create consumer group
        """
        ...
    
    async def stop(self) -> None:
        """
        Stop the event bus gracefully.
        
        Should:
            - Finish processing current events
            - Stop accepting new events
            - Clean up resources (connections, tasks)
        """
        ...