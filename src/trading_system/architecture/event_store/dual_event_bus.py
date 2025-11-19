"""
Dual Event Bus - Publishes to both SQS and PostgreSQL.

ARCHITECTURE PATTERN: Dual Write
Events are published to:
1. SQS - For real-time processing
2. PostgreSQL - For audit trail and event sourcing

This gives us both speed (SQS) and history (PostgreSQL).
"""

import logging
from typing import List, Optional

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.shared_kernel.event_bus import EventBus
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore

logger = logging.getLogger(__name__)


class DualEventBus(EventBus):
    """
    Event bus that publishes to both SQS and PostgreSQL.
    
    PATTERN: Decorator / Composite
    Wraps existing SQS event bus and adds PostgreSQL persistence.
    
    Usage:
        sqs_bus = SQSEventBus(...)
        event_store = PostgresEventStore(...)
        dual_bus = DualEventBus(sqs_bus, event_store)
        
        # Now publishes to both!
        await dual_bus.publish(event)
    """
    
    def __init__(
        self,
        sqs_bus: EventBus,
        event_store: PostgresEventStore,
        persist_to_postgres: bool = True
    ):
        """
        Initialize dual event bus.
        
        Args:
            sqs_bus: Existing SQS event bus
            event_store: PostgreSQL event store
            persist_to_postgres: Whether to persist to PostgreSQL (can disable for testing)
        """
        super().__init__()
        self.sqs_bus = sqs_bus
        self.event_store = event_store
        self.persist_to_postgres = persist_to_postgres
    
    async def publish(self, event: BaseEvent) -> None:
        """
        Publish event to both SQS and PostgreSQL.
        
        RELIABILITY PATTERN:
        1. Write to PostgreSQL first (durable)
        2. Then publish to SQS (fast, but ephemeral)
        
        If SQS fails, event is still in PostgreSQL for replay.
        """
        try:
            # 1. Persist to PostgreSQL (audit trail)
            if self.persist_to_postgres:
                sequence_number = await self.event_store.append(event)
                logger.debug(
                    f"Persisted event to PostgreSQL: seq={sequence_number}"
                )
            
            # 2. Publish to SQS (real-time processing)
            await self.sqs_bus.publish(event)
            
            logger.info(
                f"Published event to dual bus",
                extra={
                    "event_type": type(event).__name__,
                    "event_id": event.event_id,
                    "aggregate_id": event.aggregate_id
                }
            )
            
        except Exception as e:
            logger.error(
                f"Failed to publish event to dual bus: {e}",
                exc_info=True
            )
            # In production, might want to retry or use DLQ
            raise
    
    async def subscribe(
        self,
        event_type: str,
        handler: callable
    ) -> None:
        """
        Subscribe to events from SQS.
        
        Note: Subscriptions only apply to SQS.
        PostgreSQL is for storage/replay, not real-time subscriptions.
        """
        await self.sqs_bus.subscribe(event_type, handler)
    
    async def start(self) -> None:
        """Start the SQS event bus."""
        await self.sqs_bus.start()
    
    async def stop(self) -> None:
        """Stop the SQS event bus."""
        await self.sqs_bus.stop()