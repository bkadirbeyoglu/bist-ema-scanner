"""
Saga Orchestrator.

Coordinates saga execution and tracks all active/completed sagas.
This is the central point for starting and monitoring sagas.
"""

import asyncio
import logging
from typing import Dict, Optional, Callable, Awaitable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from order_service.domain.entities import Order
from order_service.domain.saga_state import SagaExecution, SagaState
from order_service.application.order_saga import OrderPlacementSaga

logger = logging.getLogger(__name__)


@dataclass
class SagaTracker:
    """Tracks a single saga execution with its associated order."""
    execution: SagaExecution
    order: Order
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class SagaOrchestrator:
    """
    Central coordinator for all saga executions.
    
    Responsibilities:
    • Start new sagas
    • Track active and completed sagas
    • Provide status queries
    • Trigger callbacks on completion/failure
    
    ⚠️ NOTE: This is an IN-MEMORY implementation.
    ═══════════════════════════════════════════
    
    Production requirements:
    • Persist to PostgreSQL with event sourcing
    • Implement recovery on service restart
    • Add distributed locking for concurrent access
    """

    def __init__(self) -> None:
        """Initialize orchestrator with empty saga registry.""" 
        self._sagas: Dict[str, SagaTracker] = {}
        self._lock = asyncio.Lock()

        # Callbacks for saga lifecycle events
        self._on_complete: list[Callable[Order, SagaExecution], Awaitable[None]] = []
        self._on_failed: list[Callable[Order, SagaExecution], Awaitable[None]] = []

    def on_complete(
        self,
        callback: Callable[[Order, SagaExecution], Awaitable[None]]
    ) -> None:
        """Register callback for succesful saga completion."""
        self._on_complete.append(callback)

    def on_failed(
        self, 
        callback: Callable[[Order, SagaExecution], Awaitable[None]]
    ) -> None:
        """Register callback for saga failure (including compensated)."""
        self._on_failed.append(callback)
    
    async def start_order_saga(self, order: Order) -> SagaExecution:
        """
        Start a new order placement saga.
        
        Args:
            order: The order to process
            
        Returns:
            Final SagaExecution state
            
        Raises:
            ValueError: If saga already exists for this order
        """
        async with self._lock:
            if order.id in self._sagas:
                raise ValueError(f"Saga already exists for order {order.id}")
            
            # Create and register saga
            saga = OrderPlacementSaga(order)
            order.saga_id = saga.saga_id

            self._sagas[order.id] = SagaTracker(
                execution=saga.execution,
                order=order
            )

            logger.info(f"Registered saga for order {order.id}")

        # Execute saga (outside lock to avoid blocking)
        execution = await saga.execute()

        # Update tracker with final state
        async with self._lock:
            self._sagas[order.id].execution = execution
        
        # Trigger callbacks
        await self._trigger_callbacks(order, execution)
        
        return execution
    
    async def _trigger_callbacks(
        self, 
        order: Order, 
        execution: SagaExecution
    ) -> None:
        """Trigger appropriate callbacks based on saga outcome."""
        callbacks = []
        
        if execution.state == SagaState.COMPLETED:
            callbacks = self._on_complete
        elif execution.state in (SagaState.COMPENSATED, SagaState.FAILED):
            callbacks = self._on_failed
        
        for callback in callbacks:
            try:
                await callback(order, execution)
            except Exception as e:
                logger.error(f"Callback error: {e}")
    
    async def get_saga_status(self, order_id: str) -> Optional[SagaExecution]:
        """Get current saga status by order ID."""
        async with self._lock:
            tracker = self._sagas.get(order_id)
            return tracker.execution if tracker else None
    
    async def get_order(self, order_id: str) -> Optional[Order]:
        """Get order associated with a saga."""
        async with self._lock:
            tracker = self._sagas.get(order_id)
            return tracker.order if tracker else None
    
    async def get_active_sagas(self) -> list[SagaExecution]:
        """Get all non-terminal saga executions."""
        async with self._lock:
            return [
                tracker.execution 
                for tracker in self._sagas.values()
                if not tracker.execution.state.is_terminal()  # pylint: disable=no-member
            ]
    
    def stats(self) -> dict:
        """Get orchestrator statistics."""
        by_state: dict[str, int] = {}
        
        for tracker in self._sagas.values():
            state_name = tracker.execution.state.name
            by_state[state_name] = by_state.get(state_name, 0) + 1
        
        return {
            "total_sagas": len(self._sagas),
            "by_state": by_state
        }


# Module-level singleton
_orchestrator: Optional[SagaOrchestrator] = None


def get_orchestrator() -> SagaOrchestrator:
    """Get the singleton orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SagaOrchestrator()
    return _orchestrator