"""
SQS Consumer for Market Data Events.

Listens to the market-data-prices queue and maintains a price cache.

NEW PYTHON FEATURE: contextlib.suppress
═══════════════════════════════════════

`suppress` ignores specified exceptions cleanly:

    # Instead of:
    try:
        await some_operation()
    except asyncio.CancelledError:
        pass
    
    # Use:
    with suppress(asyncio.CancelledError):
        await some_operation()

Use when you INTENTIONALLY want to ignore an expected exception.
"""

import asyncio
import json  # ← IMPORTANT: Don't forget this import!
import logging
from contextlib import suppress
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Callable, Awaitable, Any
from dataclasses import dataclass, field

import aioboto3

from order_service.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class PriceUpdate:
    """Represents a price update received from Market Data Service."""
    symbol: str
    price: Decimal
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    volume: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = "market-data-service"


class SQSConsumer:
    """
    Generic SQS message consumer.
    
    Uses long polling for efficient message retrieval.
    """
    
    def __init__(
        self,
        queue_name: str,
        handler: Callable[[dict[str, Any]], Awaitable[None]],
        max_messages: int = 10,
        wait_time_seconds: int = 20
    ):
        """
        Initialize SQS consumer.
        
        Args:
            queue_name: SQS queue to consume from
            handler: Async function to process each message
            max_messages: Max messages per poll (1-10)
            wait_time_seconds: Long poll duration (1-20)
        """
        self._queue_name = queue_name
        self._handler = handler
        self._max_messages = min(max_messages, 10)
        self._wait_time_seconds = min(wait_time_seconds, 20)
        
        self._settings = get_settings()
        self._session: Optional[aioboto3.Session] = None
        self._queue_url: Optional[str] = None
        self._running = False
        self._task: Optional[asyncio.Task[None]] = None
    
    async def start(self) -> None:
        """Start consuming messages in background."""
        if self._running:
            logger.warning("Consumer already running")
            return
        
        logger.info(f"Starting SQS consumer for: {self._queue_name}")
        
        self._session = aioboto3.Session()
        self._running = True
        
        # Get or create queue
        await self._ensure_queue()
        
        # Start background consumer task
        # asyncio.create_task schedules coroutine to run concurrently
        self._task = asyncio.create_task(self._consume_loop())
        
        logger.info(f"SQS consumer started for {self._queue_name}")
    
    async def stop(self) -> None:
        """Stop consuming gracefully."""
        if not self._running:
            return
        
        logger.info(f"Stopping SQS consumer for {self._queue_name}")
        self._running = False
        
        if self._task:
            self._task.cancel()
            # suppress ignores CancelledError - we expect it here
            with suppress(asyncio.CancelledError):
                await self._task
        
        logger.info("SQS consumer stopped")
    
    async def _ensure_queue(self) -> None:
        """Get queue URL, creating if necessary."""
        async with self._session.client(
            'sqs',
            region_name=self._settings.aws_region,
            endpoint_url=self._settings.aws_endpoint_url,
            aws_access_key_id=self._settings.aws_access_key_id,
            aws_secret_access_key=self._settings.aws_secret_access_key
        ) as sqs:
            try:
                response = await sqs.get_queue_url(QueueName=self._queue_name)
                self._queue_url = response['QueueUrl']
                logger.info(f"Found queue: {self._queue_url}")
            except Exception:
                response = await sqs.create_queue(QueueName=self._queue_name)
                self._queue_url = response['QueueUrl']
                logger.info(f"Created queue: {self._queue_url}")
    
    async def _consume_loop(self) -> None:
        """Main consumption loop."""
        while self._running:
            try:
                await self._poll_and_process()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Consumer error: {e}")
                await asyncio.sleep(5)  # Back off on error
    
    async def _poll_and_process(self) -> None:
        """Poll for messages and process them."""
        async with self._session.client(
            'sqs',
            region_name=self._settings.aws_region,
            endpoint_url=self._settings.aws_endpoint_url,
            aws_access_key_id=self._settings.aws_access_key_id,
            aws_secret_access_key=self._settings.aws_secret_access_key
        ) as sqs:
            response = await sqs.receive_message(
                QueueUrl=self._queue_url,
                MaxNumberOfMessages=self._max_messages,
                WaitTimeSeconds=self._wait_time_seconds,
                MessageAttributeNames=['All']
            )
            
            messages = response.get('Messages', [])
            if not messages:
                return
            
            logger.debug(f"Received {len(messages)} messages")
            
            for message in messages:
                await self._process_message(sqs, message)
    
    async def _process_message(self, sqs: Any, message: dict) -> None:
        """Process and acknowledge a single message."""
        receipt_handle = message['ReceiptHandle']
        
        try:
            body = json.loads(message['Body'])
            await self._handler(body)
            
            # Delete (acknowledge) message
            await sqs.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle
            )
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in message: {e}")
            # Delete malformed messages to prevent retry loop
            await sqs.delete_message(
                QueueUrl=self._queue_url,
                ReceiptHandle=receipt_handle
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            # Don't delete - will become visible again after timeout


class MarketDataConsumer:
    """
    Specialized consumer for market data price updates.
    
    Maintains a price cache that can be queried synchronously.
    """
    
    def __init__(self) -> None:
        """Initialize market data consumer."""
        self._settings = get_settings()
        self._consumer: Optional[SQSConsumer] = None
        self._price_cache: dict[str, PriceUpdate] = {}
        self._subscribers: list[Callable[[PriceUpdate], Awaitable[None]]] = []
    
    async def start(self) -> None:
        """Start consuming market data."""
        self._consumer = SQSConsumer(
            queue_name=self._settings.sqs_market_data_queue,
            handler=self._handle_price_event
        )
        await self._consumer.start()
    
    async def stop(self) -> None:
        """Stop consuming."""
        if self._consumer:
            await self._consumer.stop()
    
    def subscribe(self, callback: Callable[[PriceUpdate], Awaitable[None]]) -> None:
        """Subscribe to price updates."""
        self._subscribers.append(callback)
    
    def get_price(self, symbol: str) -> Optional[PriceUpdate]:
        """Get cached price for symbol."""
        return self._price_cache.get(symbol.upper())
    
    def get_all_prices(self) -> dict[str, PriceUpdate]:
        """Get all cached prices."""
        return self._price_cache.copy()
    
    async def _handle_price_event(self, event: dict[str, Any]) -> None:
        """Handle incoming price update event."""
        event_type = event.get("event_type")
        
        if event_type != "PriceUpdatedEvent":
            return
        
        data = event.get("data", {})
        
        price_update = PriceUpdate(
            symbol=data.get("symbol", "").upper(),
            price=Decimal(str(data.get("price", "0"))),
            bid=Decimal(str(data["bid"])) if data.get("bid") else None,
            ask=Decimal(str(data["ask"])) if data.get("ask") else None,
            timestamp=datetime.fromisoformat(
                data.get("timestamp", datetime.now(timezone.utc).isoformat())
            )
        )
        
        # Update cache
        self._price_cache[price_update.symbol] = price_update
        
        logger.debug(f"Price update: {price_update.symbol} = ${price_update.price}")
        
        # Notify subscribers
        for subscriber in self._subscribers:
            try:
                await subscriber(price_update)
            except Exception as e:
                logger.error(f"Subscriber error: {e}")