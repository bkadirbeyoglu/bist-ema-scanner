"""
SQS Consumer for receiving SNS notifications.

This consumer polls the SQS queue that is subscribed to the order-events
SNS topic (set up in Day 11). It processes incoming order events and
generates notifications.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import aioboto3

from notification_service.config import SQS_QUEUE_NOTIFICATIONS
from notification_service.config import get_settings

logger = logging.getLogger(__name__)


class SQSConsumer:
    """
    Async SQS consumer for processing SNS notifications.
    
    The message flow:
    1. Order Service publishes to SNS topic (order-events)
    2. SNS delivers to subscribed SQS queue (notifications)
    3. This consumer polls the queue
    4. Messages are processed by the handler callback
    5. Successfully processed messages are deleted
    
    Attributes:
        queue_name: Name of SQS queue to poll
        handler: Async callback to process each message
        poll_interval: Seconds between polls when queue is empty
    """
    
    # =========================================================================
    # Understanding the Handler Type Hint
    # =========================================================================
    #
    # WHAT IS A COROUTINE?
    # --------------------
    # A coroutine is a function defined with "async def". When called, it
    # returns a coroutine object that must be awaited to get its result.
    #
    #   # Regular function - runs immediately, returns result
    #   def greet(name: str) -> str:
    #       return f"Hello, {name}"
    #   
    #   result = greet("Alice")  # Returns "Hello, Alice" immediately
    #
    #   # Coroutine function - returns coroutine object, must be awaited
    #   async def greet_async(name: str) -> str:
    #       return f"Hello, {name}"
    #   
    #   coro = greet_async("Alice")  # Returns <coroutine object>, NOT the string!
    #   result = await coro           # NOW returns "Hello, Alice"
    #
    # The Coroutine type hint describes what a coroutine object looks like:
    #   Coroutine[YieldType, SendType, ReturnType]
    #
    #   - YieldType: What it yields (usually Any for simple coroutines)
    #   - SendType: What can be sent into it (usually Any)
    #   - ReturnType: What it returns when complete  <-- THIS IS THE ONE YOU CARE ABOUT
    #
    # PRACTICAL TRUTH: For 99% of async/await code, only ReturnType matters!
    # YieldType and SendType are for advanced generator-based coroutines.
    # That's why we use "Any" for the first two - we don't care about them.
    #
    # SIMPLE EXAMPLES:
    # ----------------
    #
    #   async def fetch_user(user_id: str) -> User:
    #       ...
    #   # Type: Coroutine[Any, Any, User]
    #   #                          ^^^^
    #   #                 Returns a User when awaited
    #
    #   async def save_to_db(data: dict) -> None:
    #       ...
    #   # Type: Coroutine[Any, Any, None]
    #   #                          ^^^^
    #   #                 Returns None when awaited (side-effect only)
    #
    #   async def count_items() -> int:
    #       ...
    #   # Type: Coroutine[Any, Any, int]
    #   #                          ^^^
    #   #                 Returns an int when awaited
    #
    # SO WHEN YOU SEE:
    #   Coroutine[Any, Any, None]
    #
    # Just read it as: "A coroutine that returns None when awaited"
    # Ignore the first two "Any" - they're there for completeness but rarely matter.
    #
    # WHY THREE TYPE PARAMETERS?
    # --------------------------
    # Coroutines in Python evolved from generators. Generators can:
    #   - yield values (YieldType)
    #   - receive values via .send() (SendType)
    #   - return a final value (ReturnType)
    #
    # Example of a generator with all three (advanced, rarely used):
    #
    #   def accumulator() -> Generator[int, int, str]:
    #       #                          ^^^  ^^^  ^^^
    #       #                          │    │    └── ReturnType: final return value
    #       #                          │    └─────── SendType: what .send() accepts
    #       #                          └──────────── YieldType: what yield produces
    #       total = 0
    #       while True:
    #           value = yield total      # Yields int, receives int
    #           if value is None:
    #               return f"Final: {total}"  # Returns str
    #           total += value
    #
    # HOW TO USE THIS GENERATOR:
    #
    #   gen = accumulator()        # Create generator object
    #   
    #   # Step 1: Start the generator (runs until first yield)
    #   current = next(gen)        # Returns 0 (initial total)
    #   print(current)             # Output: 0
    #   
    #   # Step 2: Send values - each .send() resumes the generator,
    #   # passes a value to "value = yield", and runs until next yield
    #   current = gen.send(10)     # Sends 10, total becomes 10, yields 10
    #   print(current)             # Output: 10
    #   
    #   current = gen.send(5)      # Sends 5, total becomes 15, yields 15
    #   print(current)             # Output: 15
    #   
    #   current = gen.send(25)     # Sends 25, total becomes 40, yields 40
    #   print(current)             # Output: 40
    #   
    #   # Step 3: Send None to trigger the return statement
    #   try:
    #       gen.send(None)         # Sends None, triggers "return f'Final: {total}'"
    #   except StopIteration as e:
    #       print(e.value)         # Output: "Final: 40"
    #                              # The return value is in StopIteration.value!
    #
    # VISUAL TIMELINE:
    #
    #   Your Code                    Generator (accumulator)
    #   ─────────────────────────────────────────────────────────────
    #   gen = accumulator()          # Created, not started yet
    #   next(gen) ──────────────►    total = 0
    #                                yield total ────────────► returns 0
    #   gen.send(10) ───────────►    value = 10 (from yield)
    #                                total = 0 + 10 = 10
    #                                yield total ────────────► returns 10
    #   gen.send(5) ────────────►    value = 5 (from yield)
    #                                total = 10 + 5 = 15
    #                                yield total ────────────► returns 15
    #   gen.send(None) ─────────►    value = None (from yield)
    #                                if value is None: ✓
    #                                return "Final: 15" ─────► StopIteration
    #
    # This is powerful but complex! For async/await, we almost never use
    # yield or send - we just await and get the return value. That's why
    # we use Coroutine[Any, Any, X] where X is the actual return type.
    #
    # READING THE HANDLER TYPE HINT
    # -----------------------------
    # handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    #
    # Let's break this down piece by piece:
    #
    #   Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
    #   ├─────────────────────────────────────────────────────┤
    #   │                                                     │
    #   Callable[  [dict[str, Any]]  ,  Coroutine[Any, Any, None]  ]
    #              ├──────────────┤     ├──────────────────────┤
    #              │              │     │                      │
    #              INPUT ARGS     │     RETURN TYPE            │
    #              (a dict)       │     (a coroutine that      │
    #                             │      returns None)         │
    #
    # In plain English: "A function that takes a dict and returns a coroutine
    #                    that eventually produces None"
    #
    # This matches our handler signature:
    #
    #   async def handle_message(data: dict[str, Any]) -> None:
    #       # Process the message
    #       await notification_service.handle_order_event(data)
    #
    # WHY Coroutine[Any, Any, None] INSTEAD OF just None?
    # ----------------------------------------------------
    # Because async functions don't return their result directly - they return
    # a coroutine object. The type system needs to express this:
    #
    #   def sync_handler(data: dict) -> None:        # Returns None directly
    #   async def async_handler(data: dict) -> None: # Returns Coroutine[..., None]
    #
    # When we await the coroutine, we get the None:
    #   coro = async_handler({"key": "value"})  # Coroutine object
    #   result = await coro                      # None
    #
    
    def __init__(
        self,
        handler: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        queue_name: str = SQS_QUEUE_NOTIFICATIONS,
        poll_interval: float = 1.0,
    ) -> None:
        """
        Initialize SQS consumer.
        
        Args:
            handler: Async function to process each message
            queue_name: SQS queue name
            poll_interval: Seconds between polls
        """
        self._handler = handler
        self._queue_name = queue_name
        self._poll_interval = poll_interval
        self._running = False
        self._session = aioboto3.Session()
        self._settings = get_settings()
    
    async def start(self) -> None:
        """
        Start the consumer loop.
        
        Runs until stop() is called. Polls the queue continuously,
        processing messages as they arrive.
        """
        self._running = True
        logger.info(f"Starting SQS consumer for queue: {self._queue_name}")
        
        async with self._session.client(
            "sqs",
            endpoint_url=self._settings.aws_endpoint_url,
            region_name=self._settings.aws_region,
        ) as sqs:
            # Get queue URL
            response = await sqs.get_queue_url(QueueName=self._queue_name)
            queue_url = response["QueueUrl"]
            logger.info(f"Connected to queue: {queue_url}")
            
            while self._running:
                try:
                    await self._poll_and_process(sqs, queue_url)
                except Exception as e:
                    logger.error(f"Error in consumer loop: {e}")
                    await asyncio.sleep(self._poll_interval)
    
    async def stop(self) -> None:
        """Stop the consumer loop."""
        logger.info("Stopping SQS consumer...")
        self._running = False
    
    async def _poll_and_process(self, sqs: Any, queue_url: str) -> None:
        """Poll queue and process messages."""
        
        # Long polling (WaitTimeSeconds=20) is more efficient than
        # short polling - reduces API calls and cost
        response = await sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
            MessageAttributeNames=["All"],
        )
        
        messages = response.get("Messages", [])
        
        if not messages:
            logger.debug("No messages received")
            return
        
        logger.info(f"Received {len(messages)} messages")
        
        for message in messages:
            try:
                await self._process_message(message)
                
                # Delete message after successful processing
                await sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
                logger.debug(f"Deleted message: {message['MessageId']}")
                
            except Exception as e:
                logger.error(f"Error processing message {message['MessageId']}: {e}")
                # Message will become visible again after VisibilityTimeout
    
    async def _process_message(self, message: dict[str, Any]) -> None:
        """
        Process a single SQS message.
        
        SNS wraps the original message in an envelope. We need to:
        1. Parse the SQS message body (which is the SNS notification JSON)
        2. Extract the actual message from the SNS envelope
        3. Pass the event data to the handler
        """
        message_id = message["MessageId"]
        body = message["Body"]
        
        logger.debug(f"Processing message: {message_id}")
        
        # Parse the SNS notification envelope
        # When RawMessageDelivery=false (default), SNS wraps the message
        sns_notification = json.loads(body)
        
        # Check if this is an SNS notification
        if "Type" in sns_notification and sns_notification["Type"] == "Notification":
            # Extract the actual message from SNS envelope
            event_data = json.loads(sns_notification["Message"])
            logger.info(
                f"Received SNS notification",
                extra={
                    "message_id": sns_notification.get("MessageId"),
                    "topic_arn": sns_notification.get("TopicArn"),
                    "event_type": event_data.get("event_type"),
                },
            )
        else:
            # Direct SQS message (not from SNS)
            event_data = sns_notification
        
        # Call the handler with the event data
        await self._handler(event_data)


class NotificationEventHandler:
    """
    Event handler that bridges SQS consumer to notification service.
    
    This class provides the handler callback for SQSConsumer,
    translating raw events into notification service calls.
    """
    
    def __init__(
        self,
        notification_service: Any,  # NotificationApplicationService
        default_channels: list[Any] | None = None,
        default_recipient: str = "trader@example.com",
    ) -> None:
        """
        Initialize event handler.
        
        Args:
            notification_service: The application service to use
            default_channels: Channels to send notifications to
            default_recipient: Default email address
        """
        from notification_service.domain.value_objects import NotificationChannel
        
        self._service = notification_service
        self._channels = default_channels or [
            NotificationChannel.EMAIL,
            NotificationChannel.SLACK,
        ]
        self._recipient = default_recipient
    
    async def __call__(self, event_data: dict[str, Any]) -> None:
        """
        Handle an incoming event.
        
        This is called by SQSConsumer for each message.
        """
        event_type = event_data.get("event_type", "Unknown")
        logger.info(f"Handling event: {event_type}")
        
        try:
            results = await self._service.handle_order_event(
                event_data=event_data,
                channels=self._channels,
                recipient_address=self._recipient,
            )
            
            logger.info(f"Created {len(results)} notifications for {event_type}")
            
        except ValueError as e:
            # Unknown event type - log and skip
            logger.warning(f"Skipping event: {e}")
        except Exception as e:
            logger.error(f"Error handling event: {e}")
            raise  # Re-raise to prevent message deletion