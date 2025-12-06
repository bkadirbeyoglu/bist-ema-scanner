"""
SQS Event Publisher.

Publishes price update events to Amazon SQS for consumption
by the trading monolith and other services.

DESIGN PATTERN: Adapter (Hexagonal Architecture)
- Implements EventPublisher protocol
- Adapts our domain events to SQS messages
- Handles AWS-specific concerns
"""

import json
from typing import Any
import aioboto3
import structlog

from market_data_service.domain.events import PriceUpdatedEvent
from market_data_service.config import Settings

logger = structlog.get_logger()


class SQSPublisher:
    """
    Publishes domain events to Amazon SQS.
    
    IMPLEMENTATION NOTES:
    - Uses aioboto3 for async AWS operations
    - Creates queue if it doesn't exist
    - Handles serialization of domain events
    
    SQS CONCEPTS:
    - Queue: Named message buffer
    - Message: JSON payload with attributes
    - SendMessage: Add message to queue
    
    Usage:
        >>> publisher = SQSPublisher(settings)
        >>> await publisher.connect()
        >>> await publisher.publish(price_event)
        >>> await publisher.disconnect()
    """
    
    def __init__(self, settings: Settings):
        """
        Initialize SQS Publisher.
        
        Args:
            settings: Service configuration with AWS settings
        """
        self._settings = settings
        self._session = aioboto3.Session()
        self._queue_url: str | None = None
        self._client = None
        
        self._logger = logger.bind(
            publisher="sqs",
            queue_name=settings.sqs_price_queue_name
        )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # NEW PYTHON FEATURE: Manual Async Context Manager Handling
    # ═══════════════════════════════════════════════════════════════════════════
    #
    # NORMAL USAGE (automatic cleanup):
    # ┌────────────────────────────────────────────────────────────────────────┐
    # │ async with session.client("sqs") as client:                            │
    # │     await client.send_message(...)                                     │
    # │     await client.send_message(...)                                     │
    # │ # Client is automatically closed here when block exits                 │
    # └────────────────────────────────────────────────────────────────────────┘
    #
    # PROBLEM: We need the client to stay open across multiple method calls!
    #
    # ┌────────────────────────────────────────────────────────────────────────┐
    # │ class SQSPublisher:                                                    │
    # │     async def connect(self):                                           │
    # │         async with self._session.client("sqs") as client:              │
    # │             self._client = client                                      │
    # │         # ❌ Client is CLOSED here! self._client is now unusable!      │
    # │                                                                        │
    # │     async def publish(self, event):                                    │
    # │         await self._client.send_message(...)  # ❌ Error! Client closed│
    # └────────────────────────────────────────────────────────────────────────┘
    #
    # SOLUTION: Manually call __aenter__ and __aexit__
    #
    # ┌────────────────────────────────────────────────────────────────────────┐
    # │ class SQSPublisher:                                                    │
    # │     async def connect(self):                                           │
    # │         # Manually enter the context (don't exit yet!)                 │
    # │         self._client = await self._session.client("sqs").__aenter__()  │
    # │         # ✓ Client stays open!                                         │
    # │                                                                        │
    # │     async def publish(self, event):                                    │
    # │         await self._client.send_message(...)  # ✓ Works!               │
    # │                                                                        │
    # │     async def disconnect(self):                                        │
    # │         # Manually exit the context (now we close it)                  │
    # │         await self._client.__aexit__(None, None, None)                 │
    # │         # ✓ Client properly closed                                     │
    # └────────────────────────────────────────────────────────────────────────┘
    #
    # WHAT IS __aenter__ AND __aexit__?
    # ─────────────────────────────────
    # These are the "dunder methods" that make `async with` work.
    #
    # When you write:
    #     async with some_object as value:
    #         # use value
    #
    # Python translates it to:
    #     value = await some_object.__aenter__()
    #     try:
    #         # use value
    #     finally:
    #         await some_object.__aexit__(exc_type, exc_val, exc_tb)
    #
    # __aexit__ PARAMETERS:
    # ─────────────────────
    # __aexit__(self, exc_type, exc_val, exc_tb)
    #
    # - exc_type: Exception class (or None if no exception)
    # - exc_val: Exception instance (or None)
    # - exc_tb: Traceback object (or None)
    #
    # When exiting normally (no exception):
    #     await client.__aexit__(None, None, None)
    #
    # When exiting due to exception (rare for manual calls):
    #     await client.__aexit__(type(e), e, e.__traceback__)
    #
    # WHEN TO USE MANUAL HANDLING:
    # ────────────────────────────
    # ✓ Object lifecycle spans multiple method calls
    # ✓ Connect/disconnect are separate methods
    # ✓ Class manages resource lifecycle
    # ✗ Single operation (just use `async with`)
    # ✗ Scope fits in one function (just use `async with`)
    #
    # ALTERNATIVE: Store the context manager itself
    # ─────────────────────────────────────────────
    # Another pattern is to store the context manager and enter it:
    #
    # self._client_cm = self._session.client("sqs")  # Store context manager
    # self._client = await self._client_cm.__aenter__()  # Enter it
    # # Later...
    # await self._client_cm.__aexit__(None, None, None)  # Exit it
    #
    # This is useful when __aexit__ needs the original context manager object.
    # For aioboto3, calling __aexit__ on the client itself works fine.
    #
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def connect(self) -> None:
        """
        Connect to SQS and ensure queue exists.
        
        IDEMPOTENT QUEUE CREATION:
        - CreateQueue returns existing queue if name matches
        - Safe to call multiple times
        
        LOCALSTACK NOTE:
        - Uses endpoint_url for local development
        - In production, endpoint_url is None (uses real AWS)
        """
        self._logger.info("Connecting to SQS")
        
        # ─────────────────────────────────────────────────────────────────────
        # MANUAL __aenter__: Keep client open across method calls
        # ─────────────────────────────────────────────────────────────────────
        # 
        # Normal pattern would be:
        #     async with self._session.client("sqs", ...) as client:
        #         # client only valid in this block
        #
        # But we need client to persist, so we manually enter the context:
        #
        self._client = await self._session.client(
            "sqs",
            region_name=self._settings.aws_region,
            endpoint_url=self._settings.aws_endpoint_url
        ).__aenter__()
        #
        # Now self._client is open and will stay open until we call __aexit__
        # ─────────────────────────────────────────────────────────────────────
        
        # Create queue (idempotent)
        try:
            response = await self._client.create_queue(
                QueueName=self._settings.sqs_price_queue_name,
                Attributes={
                    # Message retention: 4 days (default)
                    "MessageRetentionPeriod": "345600",
                    # Visibility timeout: 30 seconds
                    # Time a message is hidden after being received
                    "VisibilityTimeout": "30",
                    # Receive wait time: 20 seconds (long polling)
                    # Reduces empty receives, saves costs
                    "ReceiveMessageWaitTimeSeconds": "20"
                }
            )
            self._queue_url = response["QueueUrl"]
            
            self._logger.info(
                "SQS queue ready",
                queue_url=self._queue_url
            )
            
        except Exception as e:
            self._logger.error(
                "Failed to create/get SQS queue",
                error=str(e)
            )
            raise
    
    async def disconnect(self) -> None:
        """
        Disconnect from SQS.
        
        MANUAL __aexit__: Clean up the client we opened in connect()
        
        The three None arguments represent:
        - exc_type: None (no exception)
        - exc_val: None (no exception value)
        - exc_tb: None (no traceback)
        
        This tells __aexit__ that we're exiting normally, not due to an error.
        """
        if self._client:
            # ─────────────────────────────────────────────────────────────────
            # MANUAL __aexit__: Now we close the client
            # ─────────────────────────────────────────────────────────────────
            await self._client.__aexit__(None, None, None)
            self._client = None
        
        self._queue_url = None
        self._logger.info("Disconnected from SQS")
    
    async def publish(self, event: PriceUpdatedEvent) -> None:
        """
        Publish price update event to SQS.
        
        MESSAGE FORMAT:
        - Body: JSON-serialized event
        - MessageAttributes: Metadata for filtering
        
        MESSAGE ATTRIBUTES:
        - event_type: For consumers to filter messages
        - symbol: For topic-based routing (future)
        - source: Data lineage tracking
        
        Args:
            event: Price update event to publish
            
        Raises:
            RuntimeError: If not connected
            Exception: If SQS operation fails
        """
        if not self._client or not self._queue_url:
            raise RuntimeError("SQS publisher not connected")
        
        # Serialize event to JSON
        message_body = event.to_json()
        
        # Message attributes for filtering/routing
        # SQS CONCEPT: MessageAttributes
        # - Key-value pairs attached to message
        # - Consumers can filter on these without parsing body
        # - Limited to string/number/binary types
        message_attributes = {
            "event_type": {
                "DataType": "String",
                "StringValue": event.event_type
            },
            "symbol": {
                "DataType": "String",
                "StringValue": event.symbol
            },
            "source": {
                "DataType": "String",
                "StringValue": event.source
            }
        }
        
        # Add correlation ID if present
        if event.correlation_id:
            message_attributes["correlation_id"] = {
                "DataType": "String",
                "StringValue": event.correlation_id
            }
        
        try:
            response = await self._client.send_message(
                QueueUrl=self._queue_url,
                MessageBody=message_body,
                MessageAttributes=message_attributes
            )
            
            self._logger.debug(
                "Message published to SQS",
                message_id=response.get("MessageId"),
                symbol=event.symbol,
                price=str(event.price)
            )
            
        except Exception as e:
            self._logger.error(
                "Failed to publish message",
                symbol=event.symbol,
                error=str(e)
            )
            raise
    
    async def get_queue_stats(self) -> dict[str, Any]:
        """
        Get queue statistics for monitoring.
        
        METRICS:
        - ApproximateNumberOfMessages: Messages waiting
        - ApproximateNumberOfMessagesNotVisible: Being processed
        - ApproximateNumberOfMessagesDelayed: Delayed delivery
        
        Returns:
            Dictionary of queue metrics
        """
        if not self._client or not self._queue_url:
            return {"error": "Not connected"}
        
        response = await self._client.get_queue_attributes(
            QueueUrl=self._queue_url,
            AttributeNames=[
                "ApproximateNumberOfMessages",
                "ApproximateNumberOfMessagesNotVisible",
                "ApproximateNumberOfMessagesDelayed"
            ]
        )
        
        return response.get("Attributes", {})