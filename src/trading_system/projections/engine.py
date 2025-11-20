"""
Projection Engine - Transforms events into read models.

ARCHITECTURE:
Events (immutable) → Projection Engine → Read Models (optimized)

KEY CONCEPTS:
- Projections are event handlers that update read models
- Checkpointing enables resumption after crashes
- Idempotency ensures safe event replay
- Catch-up handles missed events during downtime
"""

import logging
import json
from typing import List, Protocol, Optional, Type
from abc import ABC, abstractmethod

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore
from trading_system.shared_kernel.base_event import BaseEvent

logger = logging.getLogger(__name__)


# ============================================
# PROJECTION INTERFACE
# ============================================

class IProjection(Protocol):
    """
    Contract for all projections.
    
    PATTERN: Strategy Pattern
    Each projection implements this interface.
    """
    
    def can_handle(self, event_type: str) -> bool:
        """Check if this projection handles this event type."""
        ...
    
    async def project(self, event: BaseEvent) -> None:
        """Process event and update read model."""
        ...
    
    async def initialize(self) -> None:
        """Create database tables/indexes."""
        ...
    
    async def reset(self) -> None:
        """Clear read model (for rebuild)."""
        ...


# ============================================
# PROJECTION CHECKPOINT
# ============================================

class ProjectionCheckpoint:
    """
    Tracks last processed event for each projection.
    
    WHY NEEDED:
    - Server crashes → resume from last checkpoint
    - Projections can run at different speeds
    - Multiple projection instances can coordinate
    """
    
    def __init__(self, pool: PostgresConnectionPool):
        self.pool = pool
    
    async def initialize(self):
        """Create checkpoints table if not exists."""
        async with self.pool.pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS read_models.projection_checkpoints (
                    projection_name VARCHAR(255) PRIMARY KEY,
                    last_event_sequence BIGINT NOT NULL,
                    last_event_id UUID NOT NULL,
                    events_processed INT NOT NULL DEFAULT 0,
                    last_processed_at TIMESTAMP NOT NULL,
                    last_error TEXT
                )
            """)
    
    async def save(
        self,
        projection_name: str,
        sequence: int,
        event_id: str
    ) -> None:
        """Save checkpoint after processing event."""
        async with self.pool.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO read_models.projection_checkpoints 
                (projection_name, last_event_sequence, last_event_id, 
                 events_processed, last_processed_at)
                VALUES ($1, $2, $3, 1, NOW())
                ON CONFLICT (projection_name) DO UPDATE SET
                    last_event_sequence = $2,
                    last_event_id = $3,
                    events_processed = read_models.projection_checkpoints.events_processed + 1,
                    last_processed_at = NOW()
            """, projection_name, sequence, event_id)
    
    async def load(self, projection_name: str) -> Optional[int]:
        """Load last processed sequence number."""
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT last_event_sequence 
                FROM read_models.projection_checkpoints
                WHERE projection_name = $1
            """, projection_name)
            return row['last_event_sequence'] if row else None


# ============================================
# PROJECTION ENGINE
# ============================================

class ProjectionEngine:
    """
    Manages projections and processes events from event store.
    
    ARCHITECTURE:
    1. Reads events from PostgresEventStore (Session 1)
    2. Routes to appropriate projections
    3. Updates read models in PostgreSQL
    4. Saves checkpoints for resumption
    
    PATTERN: Event-driven pipeline
    """
    
    def __init__(
        self,
        event_store: PostgresEventStore,
        connection_pool: PostgresConnectionPool
    ):
        self.event_store = event_store
        self.pool = connection_pool
        self.checkpoint = ProjectionCheckpoint(connection_pool)
        self.projections: List[IProjection] = []
        self._is_running = False
        
        logger.info("Projection engine initialized")
    
    async def initialize(self):
        """Initialize projection system."""
        await self.checkpoint.initialize()
        
        # Create read_models schema if not exists
        async with self.pool.pool.acquire() as conn:
            await conn.execute("CREATE SCHEMA IF NOT EXISTS read_models")
        
        logger.info("Projection system initialized")
    
    def register_projection(self, projection: IProjection) -> None:
        """Register a projection with the engine."""
        self.projections.append(projection)
        logger.info(f"Registered projection: {projection.__class__.__name__}")
    
    async def project_event(self, event: BaseEvent, sequence: int) -> None:
        """
        Project a single event through all relevant projections.
        
        Args:
            event: Event to project
            sequence: Sequence number from event store
        """
        event_type = event.__class__.__name__
        
        for projection in self.projections:
            if not projection.can_handle(event_type):
                continue
            
            projection_name = projection.__class__.__name__
            
            try:
                # Project the event
                await projection.project(event)
                
                # Save checkpoint
                await self.checkpoint.save(
                    projection_name=projection_name,
                    sequence=sequence,
                    event_id=event.event_id
                )
                
                logger.debug(f"Projected event {event_type} through {projection_name}")
                
            except Exception as e:
                logger.error(
                    f"Projection error: {projection_name}",
                    extra={
                        "event_type": event_type,
                        "event_id": event.event_id,
                        "error": str(e)
                    },
                    exc_info=True
                )
                # Continue with other projections
    
    async def catch_up(self, projection_name: str) -> None:
        """
        Catch up a projection from its last checkpoint.
        
        USE CASE:
        - Projection was down, needs to catch up
        - New projection added, needs historical data
        """
        # Find projection
        projection = next(
            (p for p in self.projections if p.__class__.__name__ == projection_name),
            None
        )
        
        if not projection:
            raise ValueError(f"Projection not found: {projection_name}")
        
        # Get last checkpoint
        last_sequence = await self.checkpoint.load(projection_name)
        start_sequence = (last_sequence or 0) + 1
        
        logger.info(f"Catching up {projection_name} from sequence {start_sequence}")
        
        # Stream events from event store
        async with self.pool.pool.acquire() as conn:
            async with conn.transaction():
                # Query events after checkpoint
                rows = await conn.fetch("""
                    SELECT sequence_number, event_id, event_type, 
                           aggregate_id, aggregate_type, payload, occurred_at
                    FROM events.events
                    WHERE sequence_number >= $1
                    ORDER BY sequence_number ASC
                """, start_sequence)
                
                event_count = 0
                for row in rows:
                    # Reconstruct event
                    event_class = self._get_event_class(row['event_type'])
                    if not event_class:
                        logger.warning(f"Unknown event type: {row['event_type']}")
                        continue
                    
                    # Check if projection handles this event
                    if not projection.can_handle(row['event_type']):
                        continue
                    
                    # Deserialize event
                    # Parse JSON payload (asyncpg may return JSONB as string)
                    payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
                    event = event_class.from_dict(payload)
                    
                    # Project it
                    await projection.project(event)
                    
                    # Save checkpoint
                    await self.checkpoint.save(
                        projection_name=projection_name,
                        sequence=row['sequence_number'],
                        event_id=row['event_id']
                    )
                    
                    event_count += 1
                    
                    # Progress logging
                    if event_count % 100 == 0:
                        logger.info(f"Processed {event_count} events for {projection_name}")
        
        logger.info(f"Catch-up complete: {projection_name} processed {event_count} events")
    
    async def rebuild_all(self) -> None:
        """
        Rebuild all projections from scratch.
        
        USE CASE:
        - Read model corrupted
        - Schema changed
        - Need to reprocess with new logic
        """
        logger.info("Starting full rebuild of all projections")
        
        # Reset all projections
        for projection in self.projections:
            logger.info(f"Resetting {projection.__class__.__name__}")
            await projection.reset()
        
        # Process all events
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT sequence_number, event_id, event_type, 
                       aggregate_id, aggregate_type, payload, occurred_at
                FROM events.events
                ORDER BY sequence_number ASC
            """)
            
            total = len(rows)
            logger.info(f"Rebuilding from {total} events")
            
            for i, row in enumerate(rows):
                # Reconstruct event
                event_class = self._get_event_class(row['event_type'])
                if not event_class:
                    continue
                
                # Parse JSON payload (asyncpg may return JSONB as string)
                payload = json.loads(row['payload']) if isinstance(row['payload'], str) else row['payload']
                event = event_class.from_dict(payload)
                
                # Project through all projections
                await self.project_event(event, row['sequence_number'])
                
                # Progress logging
                if (i + 1) % 1000 == 0:
                    logger.info(f"Rebuild progress: {i + 1}/{total}")
        
        logger.info("Rebuild complete")
    
    def _get_event_class(self, event_type: str) -> Optional[Type[BaseEvent]]:
        """
        Map event type string to event class.
        
        This should be enhanced with proper event registry.
        For now, we handle the key event types from Day 6/7.
        """
        from trading_system.shared_kernel.signal_events import SignalGeneratedEvent
        from trading_system.shared_kernel.backtest_events import BacktestCompletedEvent
        
        mapping = {
            "SignalGeneratedEvent": SignalGeneratedEvent,
            "BacktestCompletedEvent": BacktestCompletedEvent,
        }
        
        return mapping.get(event_type)