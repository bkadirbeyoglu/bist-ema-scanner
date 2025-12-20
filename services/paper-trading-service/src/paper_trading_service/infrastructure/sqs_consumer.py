"""
SQS Consumer for Paper Trading Service.

Uses asyncio.TaskGroup (Python 3.11+) for structured concurrency.
For Python 3.10, falls back to asyncio.gather().
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from contextlib import suppress

import aioboto3

from paper_trading_service.application.signal_handler import SignalHandler
from paper_trading_service.config import Settings


logger = logging.getLogger(__name__)


class SQSConsumer:
    """Consumes messages from SQS using long polling."""
    
    def __init__(
        self,
        signal_handler: SignalHandler,
        settings: Settings | None = None,
    ) -> None:
        self._signal_handler = signal_handler
        self._settings = settings or Settings()
        self._running = False
        self._session = aioboto3.Session()
        self._message_count = 0
    
    @property
    def message_count(self) -> int:
        """Number of messages processed."""
        return self._message_count
    
    @property
    def is_running(self) -> bool:
        """Whether the consumer is running."""
        return self._running
    
    async def start(self) -> None:
        """Start consuming messages from SQS."""
        self._running = True
        logger.info("SQS Consumer starting...")
        
        async with self._session.client(
            "sqs",
            endpoint_url=self._settings.sqs_endpoint_url,
            region_name=self._settings.sqs_region,
        ) as sqs:
            # Get queue URL
            try:
                response = await sqs.get_queue_url(
                    QueueName=self._settings.signal_queue_name
                )
                queue_url = response["QueueUrl"]
                logger.info("Connected to queue: %s", queue_url)
            except Exception as e:
                logger.error("Failed to get queue URL: %s", e)
                return
            
            # Main consume loop
            while self._running:
                await self._poll_and_process(sqs, queue_url)
    
    async def stop(self) -> None:
        """Stop consuming messages."""
        self._running = False
        logger.info("SQS Consumer stopped")
    
    async def _poll_and_process(self, sqs, queue_url: str) -> None:
        """Poll for messages and process them."""
        try:
            # Long polling (waits up to 5 seconds for messages)
            response = await sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=5,
                MessageAttributeNames=["All"],
            )
            
            messages = response.get("Messages", [])
            if not messages:
                return
            
            # Process messages concurrently
            if sys.version_info >= (3, 11):
                # Python 3.11+: Use TaskGroup
                # ┌────────────────────────────────────────────────────────────┐
                # │ PYTHON FEATURE: asyncio.TaskGroup                         │
                # ├────────────────────────────────────────────────────────────┤
                # │ TaskGroup ensures all tasks complete (or are cancelled)   │
                # │ before exiting the context. If any task raises an         │
                # │ exception, all other tasks are cancelled automatically.   │
                # └────────────────────────────────────────────────────────────┘
                async with asyncio.TaskGroup() as tg:
                    for message in messages:
                        tg.create_task(
                            self._process_message(sqs, queue_url, message)
                        )
            else:
                # Python 3.10: Use gather
                tasks = [
                    asyncio.create_task(
                        self._process_message(sqs, queue_url, message)
                    )
                    for message in messages
                ]
                await asyncio.gather(*tasks, return_exceptions=True)
        
        except asyncio.CancelledError:
            raise  # Don't catch cancellation
        except Exception as e:
            logger.error("Error polling messages: %s", e)
            await asyncio.sleep(1)  # Backoff on error
    
    async def _process_message(
        self,
        sqs,
        queue_url: str,
        message: dict,
    ) -> None:
        """Process a single SQS message."""
        receipt_handle = message.get("ReceiptHandle")
        
        try:
            # Parse message body
            body = json.loads(message.get("Body", "{}"))
            self._message_count += 1
            
            logger.debug(
                "Processing message #%d: %s",
                self._message_count,
                body.get("event_type"),
            )
            
            # Process through signal handler
            await self._signal_handler.handle_event(body)
            
            # Delete message on success
            await sqs.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle,
            )
        
        except json.JSONDecodeError as e:
            logger.error("Invalid JSON in message: %s", e)
            # Delete malformed messages to prevent infinite retries
            with suppress(Exception):
                await sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=receipt_handle,
                )
        except Exception as e:
            logger.error("Error processing message: %s", e)
            # Don't delete - message will be retried after visibility timeout