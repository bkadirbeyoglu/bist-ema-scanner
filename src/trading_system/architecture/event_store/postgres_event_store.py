# src/trading_system/architecture/event_store/postgres_event_store.py
"""
PostgreSQL Event Store Implementation.

Provides append-only event storage with:
1. Event persistence (store events)
2. Event retrieval (query events)
3. Version conflict detection (optimistic locking)
4. Event replay support
"""

import json
import logging
from decimal import Decimal
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

import asyncpg

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.shared_kernel.base_event import BaseEvent

logger = logging.getLogger(__name__)


class ConcurrencyError(Exception):
    """Raised when optimistic concurrency check fails."""
    pass


class EventStoreError(Exception):
    """Raised when event store operation fails."""
    pass


class PostgresEventStore:
    """PostgreSQL-based event store for event sourcing."""
    
    def __init__(self, pool: PostgresConnectionPool):
        """Initialize event store with connection pool."""
        self.pool = pool
    
    def _serialize_event(self, event: BaseEvent) -> dict:
        """Serialize event to dictionary with JSON-safe types."""
        if hasattr(event, 'to_dict'):
            return event.to_dict()
        
        # Fallback: manually serialize
        result = {}
        for key, value in event.__dict__.items():
            if isinstance(value, Enum):
                result[key] = value.value
            elif isinstance(value, Decimal):
                result[key] = str(value)
            elif isinstance(value, datetime):
                result[key] = value.isoformat()
            else:
                result[key] = value
        
        return result
    
    @staticmethod
    def _json_encoder(obj):
        """Custom JSON encoder for types that json.dumps doesn't handle."""
        if isinstance(obj, Enum):
            return obj.value
        if isinstance(obj, Decimal):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
    
    async def _get_aggregate_version(self, aggregate_id: str) -> int:
        """Get current version for an aggregate."""
        # FIXED: Added schema prefix 'events.events'
        query = """
        SELECT COALESCE(MAX(version), -1) as version
        FROM events.events
        WHERE aggregate_id = $1
        """
        
        row = await self.pool.fetchrow(query, aggregate_id)
        return row['version'] if row else -1
    
    async def _get_next_version(self, aggregate_id: str) -> int:
        """Get next version number for an aggregate."""
        current = await self._get_aggregate_version(aggregate_id)
        return current + 1
    
    async def append(
        self,
        event: BaseEvent,
        expected_version: Optional[int] = None
    ) -> int:
        """Append event to store."""
        try:
            # Step 1: Get current version and determine next version
            current_version = await self._get_aggregate_version(event.aggregate_id)
            
            # Step 2: Check optimistic locking if expected_version provided
            if expected_version is not None:
                if current_version != expected_version:
                    raise ConcurrencyError(
                        f"Version mismatch for aggregate {event.aggregate_id}: "
                        f"expected {expected_version}, got {current_version}"
                    )
            
            # Step 3: Calculate next version
            next_version = current_version + 1
            
            # Step 4: Serialize event to dictionary
            payload = self._serialize_event(event)
            
            # CRITICAL FIX: Override the version in payload with next_version
            # This ensures the stored event has the correct version,
            # not the version=0 default from the event object
            payload['version'] = next_version
            
            # Step 5: Insert event with correct version
            query = """
                INSERT INTO events.events (
                    event_id,
                    event_type,
                    aggregate_id,
                    aggregate_type,
                    payload,
                    occurred_at,
                    version
                ) VALUES ($1, $2, $3, $4, $5::jsonb, $6, $7)
                RETURNING sequence_number
            """
            
            # Convert payload to JSON string with custom encoder
            payload_json = json.dumps(payload, default=self._json_encoder)
            
            sequence_number = await self.pool.fetchval(
                query,
                event.event_id,
                type(event).__name__,
                event.aggregate_id,
                event.aggregate_type if hasattr(event, 'aggregate_type') else 'Unknown',
                payload_json,
                event.occurred_at,
                next_version  # Use calculated next_version
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
            raise ConcurrencyError(
                f"Concurrent modification detected for aggregate "
                f"{event.aggregate_id}"
            ) from e
        except ConcurrencyError:
            # Re-raise ConcurrencyError without wrapping
            raise
        except Exception as e:
            logger.error(f"Failed to append event: {e}", exc_info=True)
            raise EventStoreError(f"Append failed: {e}") from e
    
    async def get_events(
        self,
        aggregate_id: str,
        from_version: int = 0
    ) -> List[Dict[str, Any]]:
        """Get all events for an aggregate, starting from a specific version."""
        query = """
        SELECT 
            event_id,
            event_type,
            aggregate_id,
            aggregate_type,
            version,
            payload,
            occurred_at,
            sequence_number
        FROM events.events
        WHERE aggregate_id = $1 AND version >= $2
        ORDER BY sequence_number ASC
        """
        
        rows = await self.pool.fetch(query, aggregate_id, from_version)
        
        events = []
        for row in rows:
            # Parse JSON payload if it's a string
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            event_data = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "aggregate_id": row["aggregate_id"],
                "aggregate_type": row["aggregate_type"],
                "version": row["version"],
                "occurred_at": row["occurred_at"],
                "sequence_number": row["sequence_number"],
                **payload
            }
            events.append(event_data)
        
        logger.debug(f"Retrieved {len(events)} events for aggregate {aggregate_id}")
        return events
    
    async def get_events_by_type(
        self,
        event_type: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get recent events of a specific type."""
        query = """
        SELECT 
            event_id,
            event_type,
            aggregate_id,
            aggregate_type,
            version,
            payload,
            occurred_at,
            sequence_number
        FROM events.events
        WHERE event_type = $1
        ORDER BY occurred_at DESC
        LIMIT $2
        """
        
        rows = await self.pool.fetch(query, event_type, limit)
        
        events = []
        for row in rows:
            # Parse JSON payload if it's a string
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            event_data = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "aggregate_id": row["aggregate_id"],
                "aggregate_type": row["aggregate_type"],
                "version": row["version"],
                "occurred_at": row["occurred_at"],
                "sequence_number": row["sequence_number"],
                **payload
            }
            events.append(event_data)
        
        logger.debug(f"Retrieved {len(events)} events of type {event_type}")
        return events
    
    async def get_events_by_time_range(
        self,
        start_time: datetime,
        end_time: datetime,
        aggregate_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get events within a time range."""
        if aggregate_type:
            query = """
            SELECT 
                event_id,
                event_type,
                aggregate_id,
                aggregate_type,
                version,
                payload,
                occurred_at,
                sequence_number
            FROM events.events
            WHERE occurred_at >= $1 
              AND occurred_at <= $2
              AND aggregate_type = $3
            ORDER BY occurred_at ASC
            """
            rows = await self.pool.fetch(query, start_time, end_time, aggregate_type)
        else:
            query = """
            SELECT 
                event_id,
                event_type,
                aggregate_id,
                aggregate_type,
                version,
                payload,
                occurred_at,
                sequence_number
            FROM events.events
            WHERE occurred_at >= $1 
              AND occurred_at <= $2
            ORDER BY occurred_at ASC
            """
            rows = await self.pool.fetch(query, start_time, end_time)
        
        events = []
        for row in rows:
            # Parse JSON payload if it's a string
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            
            event_data = {
                "event_id": row["event_id"],
                "event_type": row["event_type"],
                "aggregate_id": row["aggregate_id"],
                "aggregate_type": row["aggregate_type"],
                "version": row["version"],
                "occurred_at": row["occurred_at"],
                "sequence_number": row["sequence_number"],
                **payload
            }
            events.append(event_data)
        
        logger.debug(
            f"Retrieved {len(events)} events from {start_time} to {end_time}"
        )
        return events
    
    async def get_statistics(self) -> Dict[str, Any]:
        """Get event store statistics."""
        # Total events
        total_query = "SELECT COUNT(*) as count FROM events.events"
        
        # By event type
        by_type_query = """
        SELECT event_type, COUNT(*) as count
        FROM events.events
        GROUP BY event_type
        ORDER BY count DESC
        """
        
        # By aggregate type
        by_aggregate_query = """
        SELECT aggregate_type, COUNT(*) as count
        FROM events.events
        GROUP BY aggregate_type
        ORDER BY count DESC
        """
        
        total_row = await self.pool.fetchrow(total_query)
        type_rows = await self.pool.fetch(by_type_query)
        aggregate_rows = await self.pool.fetch(by_aggregate_query)
        
        return {
            "total_events": total_row["count"],
            "event_types": {row["event_type"]: row["count"] for row in type_rows},
            "aggregate_types": {row["aggregate_type"]: row["count"] for row in aggregate_rows}
        }