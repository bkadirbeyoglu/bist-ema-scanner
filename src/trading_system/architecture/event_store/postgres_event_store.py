"""
PostgreSQL Event Store Implementation

This is the heart of our event sourcing system. It provides:
- Append-only event storage
- Event stream retrieval
- Event replay capabilities
- Optimistic concurrency control

DOMAIN CONCEPTS:
- Event: Immutable record of something that happened
- Aggregate: Domain object events relate to (Strategy, Backtest, etc.)
- Stream: Sequence of events for one aggregate
- Version: Order number within an aggregate's stream
"""

import json
import uuid
import logging
from typing import List, Optional, Dict, Any, Type
from datetime import datetime
from decimal import Decimal

import asyncpg

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool

logger = logging.getLogger(__name__)


# ============================================================================
# CUSTOM EXCEPTIONS
# ============================================================================

class EventStoreError(Exception):
    """Base exception for event store errors."""
    pass


class ConcurrencyError(EventStoreError):
    """
    Raised when concurrent modification detected.
    
    Example: Two processes try to append event with same version.
    """
    pass


class SerializationError(EventStoreError):
    """Raised when event serialization/deserialization fails."""
    pass


# ============================================================================
# EVENT STORE
# ============================================================================

class PostgresEventStore:
    """
    PostgreSQL-based event store.
    
    ARCHITECTURE PATTERN: Event Sourcing
    Stores all domain events in append-only log.
    Current state derived by replaying events.
    
    KEY FEATURES:
    - Append-only (no updates/deletes)
    - Optimistic concurrency control
    - Event type registry for deserialization
    - JSONB for flexible event storage
    """
    
    def __init__(self, connection_pool: PostgresConnectionPool):
        """
        Initialize event store.
        
        Args:
            connection_pool: PostgreSQL connection pool
        """
        self.pool = connection_pool.pool
        
        # Event type registry for deserialization
        self._event_registry: Dict[str, Type[BaseEvent]] = {}
        self._register_default_events()
    
    def _register_default_events(self):
        """Register all known event types."""
        from trading_system.shared_kernel.signal_events import (
            SignalGeneratedEvent
        )
        from trading_system.shared_kernel.backtest_events import (
            BacktestCompletedEvent
        )
        from trading_system.contexts.order_management.domain.events import (
            OrderCreatedEvent,
            OrderValidatedEvent,
            OrderRejectedEvent
        )
        
        # Register each event type by class name
        for event_class in [
            SignalGeneratedEvent,
            BacktestCompletedEvent,
            OrderCreatedEvent,
            OrderValidatedEvent,
            OrderRejectedEvent
        ]:
            self._event_registry[event_class.__name__] = event_class
    
    def register_event_type(self, event_class: Type[BaseEvent]):
        """
        Register custom event type.
        
        EXTENSIBILITY: Allow registering new event types at runtime
        """
        self._event_registry[event_class.__name__] = event_class
    
    def _get_event_class(self, event_type: str) -> Type[BaseEvent]:
        """Get event class from registry."""
        if event_type not in self._event_registry:
            raise SerializationError(f"Unknown event type: {event_type}")
        return self._event_registry[event_type]
    
    # ========================================================================
    # APPEND OPERATIONS
    # ========================================================================
    
    async def append(
        self,
        event: BaseEvent,
        expected_version: Optional[int] = None
    ) -> int:
        """
        Append event to store.
        
        OPTIMISTIC CONCURRENCY CONTROL:
        If expected_version is provided, will fail if aggregate's
        current version doesn't match. This prevents lost updates.
        
        Returns:
            Sequence number of appended event
        
        Raises:
            ConcurrencyError: If version mismatch detected
        """
        try:
            # Serialize event to JSON
            payload = self._serialize_event(event)
            
            # Get next version for this aggregate
            if expected_version is not None:
                current_version = await self._get_aggregate_version(
                    event.aggregate_id
                )
                if current_version != expected_version:
                    raise ConcurrencyError(
                        f"Version mismatch for aggregate {event.aggregate_id}: "
                        f"expected {expected_version}, got {current_version}"
                    )
                next_version = expected_version + 1
            else:
                next_version = await self._get_next_version(event.aggregate_id)
            
            # Insert event
            query = """
                INSERT INTO events (
                    event_id,
                    event_type,
                    aggregate_id,
                    aggregate_type,
                    payload,
                    occurred_at,
                    version
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING sequence_number
            """
            
            sequence_number = await self.pool.fetchval(
                query,
                event.event_id,
                type(event).__name__,
                event.aggregate_id,
                event.aggregate_type if hasattr(event, 'aggregate_type') else 'Unknown',
                json.dumps(payload),
                event.occurred_at,
                next_version
            )
            
            logger.info(
                f"Event appended",
                extra={
                    "event_id": event.event_id,
                    "event_type": type(event).__name__,
                    "aggregate_id": event.aggregate_id,
                    "version": next_version,
                    "sequence_number": sequence_number
                }
            )
            
            return sequence_number
            
        except asyncpg.UniqueViolationError as e:
            # UNIQUE constraint on (aggregate_id, version) violated
            raise ConcurrencyError(
                f"Concurrent modification detected for aggregate "
                f"{event.aggregate_id}"
            ) from e
        except Exception as e:
            logger.error(f"Failed to append event: {e}", exc_info=True)
            raise EventStoreError(f"Append failed: {e}") from e
    
    # ========================================================================
    # QUERY OPERATIONS
    # ========================================================================
    
    async def get_stream(
        self,
        aggregate_id: str,
        from_version: int = 1
    ) -> List[BaseEvent]:
        """
        Get all events for an aggregate.
        
        This is the core of event sourcing: retrieve all events
        that happened to one aggregate, in order.
        
        Example:
            # Get all signals from MA strategy for AAPL
            events = await store.get_stream("strategy-MovingAverage-AAPL")
        """
        query = """
            SELECT 
                event_id,
                event_type,
                aggregate_id,
                aggregate_type,
                payload,
                occurred_at,
                version,
                sequence_number
            FROM events
            WHERE aggregate_id = $1 AND version >= $2
            ORDER BY version ASC
        """
        
        rows = await self.pool.fetch(query, aggregate_id, from_version)
        
        events = [self._deserialize_event(row) for row in rows]
        
        logger.debug(
            f"Retrieved {len(events)} events for aggregate {aggregate_id}"
        )
        
        return events
    
    async def get_events_since(
        self,
        sequence_number: int,
        limit: int = 1000
    ) -> List[BaseEvent]:
        """
        Get events since a sequence number.
        
        USAGE: Event projection, catch-up subscriptions
        """
        query = """
            SELECT 
                event_id,
                event_type,
                aggregate_id,
                aggregate_type,
                payload,
                occurred_at,
                version,
                sequence_number
            FROM events
            WHERE sequence_number > $1
            ORDER BY sequence_number ASC
            LIMIT $2
        """
        
        rows = await self.pool.fetch(query, sequence_number, limit)
        return [self._deserialize_event(row) for row in rows]
    
    async def get_events_by_type(
        self,
        event_type: str,
        limit: int = 1000
    ) -> List[BaseEvent]:
        """
        Get all events of a specific type.
        
        Example:
            # Get all signal events
            signals = await store.get_events_by_type("SignalGeneratedEvent")
        """
        query = """
            SELECT 
                event_id,
                event_type,
                aggregate_id,
                aggregate_type,
                payload,
                occurred_at,
                version,
                sequence_number
            FROM events
            WHERE event_type = $1
            ORDER BY sequence_number ASC
            LIMIT $2
        """
        
        rows = await self.pool.fetch(query, event_type, limit)
        return [self._deserialize_event(row) for row in rows]
    
    async def get_events_in_range(
        self,
        start_time: datetime,
        end_time: datetime,
        event_type: Optional[str] = None
    ) -> List[BaseEvent]:
        """
        Get events within a time range.
        
        USAGE: Analysis, reporting, debugging
        
        Example:
            # Get all signals from yesterday
            yesterday_signals = await store.get_events_in_range(
                start_time=datetime(2024, 3, 14),
                end_time=datetime(2024, 3, 15),
                event_type="SignalGeneratedEvent"
            )
        """
        if event_type:
            query = """
                SELECT 
                    event_id,
                    event_type,
                    aggregate_id,
                    aggregate_type,
                    payload,
                    occurred_at,
                    version,
                    sequence_number
                FROM events
                WHERE occurred_at >= $1 
                  AND occurred_at < $2
                  AND event_type = $3
                ORDER BY occurred_at ASC
            """
            rows = await self.pool.fetch(query, start_time, end_time, event_type)
        else:
            query = """
                SELECT 
                    event_id,
                    event_type,
                    aggregate_id,
                    aggregate_type,
                    payload,
                    occurred_at,
                    version,
                    sequence_number
                FROM events
                WHERE occurred_at >= $1 AND occurred_at < $2
                ORDER BY occurred_at ASC
            """
            rows = await self.pool.fetch(query, start_time, end_time)
        
        return [self._deserialize_event(row) for row in rows]
    
    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    
    async def _get_aggregate_version(self, aggregate_id: str) -> int:
        """Get current version of aggregate."""
        query = """
            SELECT COALESCE(MAX(version), 0)
            FROM events
            WHERE aggregate_id = $1
        """
        return await self.pool.fetchval(query, aggregate_id)
    
    async def _get_next_version(self, aggregate_id: str) -> int:
        """Get next version number for aggregate."""
        current = await self._get_aggregate_version(aggregate_id)
        return current + 1
    
    def _serialize_event(self, event: BaseEvent) -> Dict[str, Any]:
        """Serialize event to JSON-compatible dict."""
        payload = {}
        
        for key, value in event.__dict__.items():
            if isinstance(value, Decimal):
                payload[key] = str(value)
            elif isinstance(value, datetime):
                payload[key] = value.isoformat()
            elif isinstance(value, uuid.UUID):
                payload[key] = str(value)
            else:
                payload[key] = value
        
        return payload
    
    def _deserialize_event(self, row: asyncpg.Record) -> BaseEvent:
        """Deserialize event from database row."""
        event_type = row['event_type']
        event_class = self._get_event_class(event_type)
        
        # Parse JSON payload
        payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
        
        # Reconstruct event
        if hasattr(event_class, 'from_dict'):
            return event_class.from_dict(payload)
        
        # Fallback: Try to construct directly
        return event_class(**payload)
    
    # ========================================================================
    # STATISTICS & MONITORING
    # ========================================================================
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get event store statistics."""
        stats_query = """
            SELECT 
                COUNT(*) as total_events,
                COUNT(DISTINCT aggregate_id) as total_aggregates,
                COUNT(DISTINCT event_type) as total_event_types,
                MIN(occurred_at) as first_event_at,
                MAX(occurred_at) as last_event_at
            FROM events
        """
        
        stats = await self.pool.fetchrow(stats_query)
        
        type_breakdown_query = """
            SELECT event_type, COUNT(*) as count
            FROM events
            GROUP BY event_type
            ORDER BY count DESC
        """
        
        type_breakdown = await self.pool.fetch(type_breakdown_query)
        
        return {
            "total_events": stats['total_events'],
            "total_aggregates": stats['total_aggregates'],
            "total_event_types": stats['total_event_types'],
            "first_event_at": stats['first_event_at'],
            "last_event_at": stats['last_event_at'],
            "events_by_type": {
                row['event_type']: row['count'] 
                for row in type_breakdown
            }
        }