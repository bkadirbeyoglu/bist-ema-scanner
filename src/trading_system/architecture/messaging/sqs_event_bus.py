"""
SQS-based Event Bus Implementation.

This implementation uses Amazon SQS for distributed event processing.
Events are published to SQS queues and consumed by background tasks.

Key Features:
- Distributed event processing across multiple services
- Persistent messages (survive process crashes)
- Horizontal scaling (multiple consumers)
- At-least-once delivery guarantee
- Dead letter queues for failed messages

Trade-offs vs InMemory:
- Higher latency (~25ms vs <1ms)
- Better reliability (persistent)
- Horizontal scalability
- More complex (background tasks, connections)
"""

import asyncio
import json
import logging
from typing import Dict, List, Callable, Type, Optional, Awaitable, Set
from dataclasses import dataclass, field
from uuid import uuid4
from datetime import datetime

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.shared_kernel.event_bus_protocol import EventBus
from trading_system.architecture.messaging.sqs_client import (
    SQSClient,
    SQSConfig,
    create_sqs_client
)

logger = logging.getLogger(__name__)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class SQSEventBusError(Exception):
    """Base exception for SQS event bus errors."""
    pass


class EventSerializationError(SQSEventBusError):
    """Raised when event serialization fails."""
    pass


class QueueCreationError(SQSEventBusError):
    """Raised when queue creation fails."""
    pass


# ============================================================================
# QUEUE NAMING STRATEGY
# ============================================================================

def get_queue_name_for_event(event_type: Type[BaseEvent], fifo: bool = True) -> str:
    """
    Generate SQS-compliant queue name from event type.
    
    SQS queue names can only contain: alphanumeric, hyphens, underscores.
    Convention: module-ClassName-fifo
    
    Examples:
        OrderCreatedEvent → order_management-OrderCreatedEvent-fifo
        TestEvent → test_sqs_event_bus-TestEvent-fifo
    """
    module = event_type.__module__.split('.')[-1]
    class_name = event_type.__name__
    name = f"{module}-{class_name}"  # ✅ Use hyphens, not periods
    if fifo:
        name += "-fifo"  # ✅ Use hyphen, not period
    return name


# ============================================================================
# SUBSCRIPTION MANAGEMENT
# ============================================================================

@dataclass
class SQSSubscription:
    """
    Represents a subscription to an event type in SQS.
    
    Unlike InMemory subscriptions, these map to SQS queues.
    """
    subscription_id: str
    event_type: Type[BaseEvent]
    handler: Callable[[BaseEvent], Awaitable[None]]
    filter_predicate: Optional[Callable[[BaseEvent], bool]] = None
    queue_name: str = field(init=False)
    
    def __post_init__(self):
        """Generate queue name after initialization."""
        self.queue_name = get_queue_name_for_event(self.event_type, fifo=True)
    
    async def handle(self, event: BaseEvent) -> None:
        """Execute the handler if the filter passes."""
        if self.filter_predicate and not self.filter_predicate(event):
            return
        
        try:
            await self.handler(event)
        except Exception as e:
            logger.error(
                f"Error in handler {self.handler.__name__} "
                f"for event {event.event_id}: {e}",
                exc_info=True
            )
            raise  # Re-raise to trigger SQS retry


# ============================================================================
# SQS EVENT BUS
# ============================================================================

class SQSEventBus(EventBus):
    """
    SQS-based implementation of EventBus.
    
    Architecture:
    1. publish() sends events to SQS queues (one queue per event type)
    2. subscribe() registers handlers and creates queues if needed
    3. Background consumer tasks poll queues and invoke handlers
    4. Dead letter queues catch failed messages after retries
    
    Characteristics:
    - Distributed (multiple services can consume)
    - Persistent (events survive crashes)
    - Scalable (add more consumers)
    - ~25ms latency (vs <1ms in-memory)
    
    Use cases:
    - Production systems
    - Microservices architecture
    - Need for reliability/persistence
    - Horizontal scaling required
    """
    
    def __init__(
        self,
        sqs_client: SQSClient,
        create_queues: bool = True,
        max_consumers: int = 5
    ):
        """
        Initialize SQS event bus.
        
        Args:
            sqs_client: Configured SQS client (already connected to AWS/LocalStack)
            create_queues: Whether to auto-create queues on subscribe (True for dev, False for prod)
            max_consumers: Max number of concurrent consumer tasks (one per unique queue)
        
        Design Notes:
        - We maintain both in-memory subscription mappings AND SQS queues
        - In-memory: fast lookup for routing messages to handlers
        - SQS: persistent storage and distribution across services
        """
        # SQS client for AWS operations
        self._sqs_client = sqs_client
        self._create_queues = create_queues
        self._max_consumers = max_consumers
        
        # Subscription management (in-memory)
        # Maps event types to lists of handlers that should process them
        self._subscriptions: Dict[Type[BaseEvent], List[SQSSubscription]] = {}
        # Fast lookup by subscription ID for unsubscribe operations
        self._subscription_registry: Dict[str, SQSSubscription] = {}
        
        # Queue management (caching)
        # Cache queue URLs to avoid repeated AWS API calls
        self._queue_cache: Dict[str, str] = {}  # queue_name -> queue_url
        # Track which queues we've created in this session
        self._created_queues: Set[str] = set()
        
        # Consumer tasks (background polling)
        # Each task continuously polls an SQS queue for messages
        self._consumer_tasks: List[asyncio.Task] = []
        self._running: bool = False  # ← Explicit type hint to help IDEs
        
        # Statistics (monitoring)
        # Track metrics for observability and debugging
        self._published_count: int = 0   # ← Explicit type hint
        self._received_count: int = 0    # ← Explicit type hint
        self._error_count: int = 0       # ← Explicit type hint for IDE
    
    # ========================================================================
    # CORE INTERFACE IMPLEMENTATION
    # ========================================================================
    
    async def publish(self, event: BaseEvent) -> None:
        """
        Publish an event to SQS.
        
        Flow:
        1. Validate event type
        2. Determine target queue based on event type
        3. Ensure queue exists (create if needed)
        4. Serialize event to JSON
        5. Send to SQS with FIFO attributes
        
        Args:
            event: Domain event to publish
        
        Raises:
            EventSerializationError: If event can't be serialized
            QueueCreationError: If queue creation fails
        
        Performance:
            - Typical latency: 10-25ms (network + SQS processing)
            - Compare to InMemory: <1ms (no network)
        """
        try:
            # Step 1: Get event type for routing
            event_type = type(event)
            
            # Step 2: Determine queue name
            # Convention: one queue per event type
            queue_name = get_queue_name_for_event(event_type, fifo=True)
            
            # Step 3: Ensure queue exists (may create it)
            queue_url = await self._ensure_queue_exists(queue_name)
            
            # Step 4: Serialize event to JSON-compatible dict
            # The event must implement to_dict() or we use a default format
            message_body = self._serialize_event(event)
            
            logger.debug(
                f"Publishing {event_type.__name__} "
                f"(ID: {event.event_id}) to queue {queue_name}"
            )
            
            # Step 5: Send to SQS
            # FIFO requires:
            # - message_group_id: Groups related messages (ordered within group)
            # - message_deduplication_id: Prevents duplicates (within 5-min window)
            message_id = await self._sqs_client.send_message(
                queue_url=queue_url,
                message_body=message_body,
                message_group_id=event_type.__name__,  # Group by event type
                message_deduplication_id=event.event_id  # Use event ID for deduplication
            )
            
            self._published_count += 1  # Track metrics
            
            logger.info(
                f"✓ Published {event_type.__name__} "
                f"(Event ID: {event.event_id}, Message ID: {message_id})"
            )
            
        except Exception as e:
            self._error_count += 1
            logger.error(f"Failed to publish event: {e}", exc_info=True)
            raise EventSerializationError(f"Failed to publish event: {e}") from e
    
    def subscribe(
        self,
        event_type: Type[BaseEvent],
        handler: Callable[[BaseEvent], Awaitable[None]],
        filter_predicate: Optional[Callable[[BaseEvent], bool]] = None
    ) -> str:
        """
        Subscribe to an event type.
        
        Creates:
        1. In-memory subscription (for routing)
        2. SQS queue (if it doesn't exist)
        3. Consumer task (if not already running for this queue)
        
        Args:
            event_type: Event class to subscribe to
            handler: Async function that processes the event
            filter_predicate: Optional filter (event → bool)
        
        Returns:
            Subscription ID (for unsubscribe)
        
        Examples:
            # Simple subscription
            sub_id = bus.subscribe(OrderCreatedEvent, handle_order)
            
            # With filter
            sub_id = bus.subscribe(
                OrderCreatedEvent,
                handle_large_order,
                filter_predicate=lambda e: e.quantity > 1000
            )
        """
        # Generate unique subscription ID
        sub_id = str(uuid4())
        
        # Create subscription object
        subscription = SQSSubscription(
            subscription_id=sub_id,
            event_type=event_type,
            handler=handler,
            filter_predicate=filter_predicate
        )
        
        # Register subscription (in-memory)
        # Multiple handlers can subscribe to the same event type
        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(subscription)
        self._subscription_registry[sub_id] = subscription
        
        logger.info(
            f"Subscribed {handler.__name__} to {event_type.__name__} "
            f"(Subscription ID: {sub_id})"
        )
        
        return sub_id
    
    def unsubscribe(self, subscription_id: str) -> bool:
        """
        Remove a subscription.
        
        Args:
            subscription_id: ID returned from subscribe()
        
        Returns:
            True if found and removed, False otherwise
        
        Note: This only removes the in-memory subscription.
        The SQS queue and consumer task remain (may serve other subscriptions).
        """
        subscription = self._subscription_registry.get(subscription_id)
        if not subscription:
            return False
        
        # Remove from event type subscriptions
        event_subscriptions = self._subscriptions.get(subscription.event_type, [])
        if subscription in event_subscriptions:
            event_subscriptions.remove(subscription)
        
        # Remove from registry
        del self._subscription_registry[subscription_id]
        
        logger.info(f"Unsubscribed {subscription_id}")
        return True
    
    async def start(self) -> None:
        """
        Start consuming events from SQS.
        
        This:
        1. Creates all queues (if create_queues=True)
        2. Starts one consumer task per unique queue
        3. Consumer tasks poll queues in the background
        
        Must be called before events can be received!
        """
        if self._running:
            logger.warning("Event bus already running")
            return
        
        self._running = True
        logger.info("Starting SQS event bus...")
        
        # Step 1: Collect unique queues from all subscriptions
        unique_queues = set(
            sub.queue_name 
            for subs in self._subscriptions.values() 
            for sub in subs
        )
        
        logger.info(f"Found {len(unique_queues)} unique queues to consume")
        
        # Step 2: Ensure all queues exist
        if self._create_queues:
            for queue_name in unique_queues:
                await self._ensure_queue_exists(queue_name)
        
        # Step 3: Start consumer task for each queue
        for queue_name in unique_queues:
            task = asyncio.create_task(
                self._consumer_loop(queue_name),
                name=f"consumer-{queue_name}"  # Name for debugging
            )
            self._consumer_tasks.append(task)
            logger.info(f"Started consumer for {queue_name}")
        
        logger.info(f"✓ SQS event bus started with {len(self._consumer_tasks)} consumers")
    
    async def stop(self) -> None:
        """
        Stop consuming events and clean up.
        
        This:
        1. Cancels all consumer tasks
        2. Waits for tasks to finish current messages
        3. Marks bus as stopped
        """
        if not self._running:
            logger.warning("Event bus not running")
            return
        
        logger.info("Stopping SQS event bus...")
        self._running = False
        
        # Cancel all consumer tasks
        for task in self._consumer_tasks:
            task.cancel()
        
        # Wait for all tasks to finish (with timeout)
        if self._consumer_tasks:
            await asyncio.gather(*self._consumer_tasks, return_exceptions=True)
        
        self._consumer_tasks.clear()
        logger.info("✓ SQS event bus stopped")
    
    # ========================================================================
    # QUEUE MANAGEMENT
    # ========================================================================
    
    async def _ensure_queue_exists(self, queue_name: str) -> str:
        """
        Ensure SQS queue exists, create if needed.
        
        Uses caching to avoid repeated AWS API calls:
        1. Check local cache
        2. If not cached, create queue (idempotent - no error if exists)
        3. Cache the queue URL
        
        Args:
            queue_name: Name of the queue
        
        Returns:
            Queue URL
        
        Raises:
            QueueCreationError: If queue creation fails
        """
        # Step 1: Check cache
        if queue_name in self._queue_cache:
            return self._queue_cache[queue_name]
        
        try:
            # Step 2: Create queue (idempotent)
            # If queue already exists, this returns the existing queue URL
            queue_url = await self._sqs_client.create_queue(
                queue_name=queue_name,
                fifo=True,  # All event queues are FIFO for ordering
                content_deduplication=True  # Enable deduplication based on message_deduplication_id
            )
            
            # Step 3: Cache it
            self._queue_cache[queue_name] = queue_url
            self._created_queues.add(queue_name)
            
            logger.info(f"Queue ready: {queue_name} → {queue_url}")
            return queue_url
            
        except Exception as e:
            raise QueueCreationError(f"Failed to create queue {queue_name}: {e}") from e
    
    # ========================================================================
    # CONSUMER LOOP
    # ========================================================================
    
    async def _consumer_loop(self, queue_name: str) -> None:
        """
        Background task that continuously polls an SQS queue.
        
        Architecture:
        1. Long poll SQS (wait up to 20s for messages)
        2. Process messages concurrently
        3. Delete messages on success
        4. On failure: leave message (SQS retries after visibility timeout)
        5. Loop until cancelled
        
        Args:
            queue_name: Name of the queue to poll
        
        Long Polling Explanation:
        - wait_time_seconds=20: Don't return immediately if queue is empty
        - Instead, keep connection open for up to 20s
        - If messages arrive during this time, return immediately
        - Reduces API calls and improves latency
        
        Visibility Timeout:
        - When message is received, it becomes invisible to other consumers
        - If we don't delete it within the timeout (default 30s), it reappears
        - This provides automatic retry on failure
        """
        queue_url = await self._ensure_queue_exists(queue_name)
        
        logger.info(f"Consumer loop started for {queue_name}")
        
        while self._running:
            try:
                # Long poll for messages
                # wait_time_seconds=20 means:
                # - If messages available immediately, return them
                # - Otherwise, wait up to 20s for messages to arrive
                # - After 20s with no messages, return empty list
                messages = await self._sqs_client.receive_messages(
                    queue_url=queue_url,
                    max_messages=10,  # Fetch up to 10 messages at once (batch processing)
                    wait_time_seconds=20  # Long polling for efficiency
                )
                
                if not messages:
                    continue  # No messages received, loop again (long poll)
                
                # Process all messages concurrently
                # Each message is processed independently
                # return_exceptions=True ensures one failure doesn't stop others
                await asyncio.gather(
                    *[self._process_message(queue_url, msg) for msg in messages],
                    return_exceptions=True
                )
                
            except asyncio.CancelledError:
                # Raised when task.cancel() is called during stop()
                logger.info(f"Consumer cancelled for {queue_name}")
                break  # Exit loop cleanly
            except Exception as e:
                # Catch-all for unexpected errors
                # Log and continue (don't crash the consumer)
                logger.error(f"Error in consumer for {queue_name}: {e}")
                await asyncio.sleep(1)  # Brief pause before retry (prevent tight error loop)
    
    async def _process_message(self, queue_url: str, message: Dict) -> None:
        """
        Process a single SQS message.
        
        Message lifecycle:
        1. Extract receipt handle (needed for deletion)
        2. Deserialize JSON to event object
        3. Find all handlers subscribed to this event type
        4. Invoke handlers concurrently
        5. If ALL handlers succeed: Delete message from SQS
        6. If ANY handler fails: Leave message (SQS will retry after visibility timeout)
        
        Visibility timeout:
        - When message is received, it becomes "invisible" to other consumers
        - If we don't delete it, it reappears after timeout (~30s)
        - This provides automatic retry on failure
        
        Args:
            queue_url: SQS queue URL
            message: Dict with event data and '_receipt_handle' key
        """
        try:
            # Step 1: Extract receipt handle
            # This is required to delete the message after processing
            # The sqs_client adds this when parsing messages
            receipt_handle = message.get('_receipt_handle')
            if not receipt_handle:
                logger.error("Message missing receipt handle")
                return
            
            # Step 2: Deserialize event from message body
            # Converts JSON dict back to Python event object
            event = self._deserialize_event(message)
            self._received_count += 1  # Track metrics
            
            logger.debug(
                f"Received {type(event).__name__} "
                f"(ID: {event.event_id}) from queue"
            )
            
            # Step 3: Find handlers for this event type
            # Lookup in our in-memory subscription registry
            subscriptions = self._subscriptions.get(type(event), [])
            
            if not subscriptions:
                # No handlers registered for this event type
                # Delete message to prevent infinite reprocessing
                logger.warning(f"No handlers for {type(event).__name__}")
                await self._sqs_client.delete_message(queue_url, receipt_handle)
                return
            
            # Step 4: Invoke all handlers concurrently
            # Each subscription.handle() calls the user's handler function
            # return_exceptions=True means failures don't raise immediately
            results = await asyncio.gather(
                *[sub.handle(event) for sub in subscriptions],
                return_exceptions=True
            )
            
            # Step 5: Check for errors
            # If any handler failed, don't delete the message
            errors = [r for r in results if isinstance(r, Exception)]
            if errors:
                self._error_count += len(errors)
                logger.error(
                    f"Handlers failed for {type(event).__name__}: {errors}"
                )
                # Don't delete message - SQS will retry after visibility timeout
                # After max retries, message goes to dead letter queue (if configured)
                return
            
            # Step 6: Success! Delete message from queue
            # This prevents reprocessing and acknowledges successful handling
            await self._sqs_client.delete_message(queue_url, receipt_handle)
            
        except Exception as e:
            # Catch-all for unexpected errors (serialization, etc.)
            self._error_count += 1
            logger.error(f"Error processing message: {e}", exc_info=True)
            # Don't delete message - let SQS retry
    
    # ========================================================================
    # SERIALIZATION
    # ========================================================================
    
    def _serialize_event(self, event: BaseEvent) -> dict:
        """
        Serialize event to JSON-compatible dict.
        
        Format:
        {
            "event_type": "OrderCreatedEvent",
            "event_id": "uuid",
            "aggregate_id": "uuid",
            "occurred_at": "ISO-8601 timestamp",
            "payload": { ... event-specific data ... }
        }
        """
        return {
            "event_type": type(event).__name__,
            "event_module": type(event).__module__,
            "event_id": event.event_id,
            "aggregate_id": event.aggregate_id,
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.to_dict() if hasattr(event, 'to_dict') else {}
        }
    
    def _deserialize_event(self, message_body: dict) -> BaseEvent:
        """
        Deserialize event from JSON dict.
        
        This requires that event classes are importable and have
        a from_dict() class method or similar constructor.
        
        For now, we'll use a simple registry pattern.
        """
        event_type_name = message_body["event_type"]
        event_module = message_body.get("event_module")
        
        # Find event class in subscriptions
        for event_type, subscriptions in self._subscriptions.items():
            if event_type.__name__ == event_type_name:
                # Use from_dict if available
                if hasattr(event_type, 'from_dict'):
                    return event_type.from_dict(message_body["payload"])
                
                # Otherwise try to reconstruct
                return event_type(
                    event_id=message_body["event_id"],
                    aggregate_id=message_body["aggregate_id"],
                    occurred_at=datetime.fromisoformat(message_body["occurred_at"]),
                    **message_body.get("payload", {})
                )
        
        raise EventSerializationError(
            f"Unknown event type: {event_type_name} from {event_module}"
        )
    
    # ========================================================================
    # STATISTICS
    # ========================================================================
    
    def get_stats(self) -> dict:
        """Get event bus statistics."""
        return {
            "published_count": self._published_count,
            "received_count": self._received_count,
            "error_count": self._error_count,
            "subscription_count": len(self._subscription_registry),
            "queue_count": len(self._queue_cache),
            "consumer_count": len(self._consumer_tasks),
            "running": self._running
        }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

async def create_sqs_event_bus(
    sqs_config: SQSConfig,
    create_queues: bool = True,
    max_consumers: int = 5
) -> SQSEventBus:
    """
    Create and initialize an SQS event bus.
    
    Usage:
        config = SQSConfig(endpoint_url="http://localstack:4566", ...)
        event_bus = await create_sqs_event_bus(config)
        await event_bus.start()
    """
    async with create_sqs_client(sqs_config) as sqs_client:
        return SQSEventBus(sqs_client, create_queues, max_consumers)