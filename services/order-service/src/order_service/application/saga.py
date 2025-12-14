"""
Base Saga Implementation.

Provides the reusable foundation for all saga orchestrators.

NEW PYTHON FEATURE: @dataclass(frozen=True)
═══════════════════════════════════════════

The `frozen=True` parameter makes dataclass instances IMMUTABLE.
After creation, you cannot modify any attributes.

Example:
    @dataclass(frozen=True)
    class Point:
        x: int
        y: int
    
    p = Point(1, 2)
    p.x = 3  # Raises FrozenInstanceError!

Benefits for saga steps:
- Steps are value objects (identity doesn't matter)
- Prevents accidental modification during execution
- Thread-safe without locks
- Can be used as dict keys or in sets
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, Awaitable, Any, Optional
import logging

from order_service.domain.saga_state import SagaState, SagaExecution

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class SagaStep:
    """
    Represents a single step in a saga.

    Each step has:
    • name: Identifier for logging and debugging
    • forward: The action to perform (async function)
    • compensate: The action to undo the forward action (optional)
    
    Using frozen=True because:
    • Steps are defined once and never modified
    • Multiple saga executions can share step definitions
    • Prevents bugs from accidental modification
    """

    name: str

    # Forward action: the main work of this step
    #
    # Type signature breakdown:
    #   Callable[                         - A function/method that can be called
    #     [dict[str, Any]],               - Takes ONE argument: context dict
    #     Awaitable[dict[str, Any]]       - Returns awaitable (async) dict
    #   ]
    #
    # In plain English: "An async function that receives context and returns updated context"
    #
    # Example implementation:
    #   async def get_price(context: dict) -> dict:
    #       price = await market_data.get_price(context["symbol"])
    #       context["current_price"] = price    # ADD data to context
    #       return context                       # MUST return the context!
    #
    forward: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
    
    # Compensate action: undoes the forward action (rollback)
    #
    # Type signature breakdown:
    #   Callable[                         - A function/method that can be called
    #     [dict[str, Any]],               - Takes ONE argument: context dict  
    #     Awaitable[None]                 - Returns awaitable None (no return value)
    #   ]
    #
    # Returns None because compensation doesn't add to context - it just cleans up.
    # Optional because read-only steps (like getting a price) don't need compensation.
    #
    compensate: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None

    def __str__(self) -> str:
        """Human-readable representation."""
        has_comp = "yes" if self.compensate else "no"
        return f"SagaStep(name='{self.name}', has_compensation={has_comp})"
    
class Saga(ABC):
    """
    Abstract base class for saga implementations.
    
    HOW IT WORKS:
    ═════════════
    
    1. Subclass defines steps via add_step() in __init__
    2. Subclass implements build_initial_context()
    3. Call execute() to run the saga
    4. Base class handles execution order, failures, compensation
    
    CONTEXT FLOW THROUGH SAGA STEPS:
    ════════════════════════════════
    
    Each step receives the context, may READ from it, and ADDS new data:
    
    Initial Context: {order_id, symbol, quantity}
         │
    Step 1: validate    → READS: symbol, quantity │ ADDS: nothing                        │ COMP: none
         │
    Step 2: get_price   → READS: symbol, quantity │ ADDS: current_price, estimated_value │ COMP: none
         │                                          (estimated_value = price x quantity)
    Step 3: check_risk  → READS: estimated_value  │ ADDS: risk_allocation_id             │ COMP: release_risk
         │
    Step 4: reserve_$   → READS: estimated_value  │ ADDS: funds_allocation_id            │ COMP: release_funds
         │
    Step 5: submit      → READS: all              │ ADDS: broker_order_id                │ COMP: cancel_order
         │
    Final Context: All IDs available for compensation!
    
    KEY INSIGHT: Compensation uses IDs added during forward execution.
    """

    def __init__(self, saga_id: str):
        """
        Initialize saga with unique ID.
        
        Args:
            saga_id: Unique identifier (usually order ID or correlation ID)
        """
        self.saga_id = saga_id
        self._steps: list[SagaStep] = []
        self._execution = SagaExecution(
            saga_id=saga_id,
            saga_type=self.__class__.__name__
        )
    
    @property
    def steps(self) -> list[SagaStep]:
        """Get the list of steps (returns copy to prevent modification)."""
        return self._steps.copy()
    
    @property
    def execution(self) -> SagaExecution:
        """Get current execution state."""
        return self._execution

    def add_step(
        self,
        name: str,
        forward: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        compensate: Optional[Callable[[dict[str, Any]], Awaitable[None]]] = None
    ) -> None:
        """
        Add a step to the saga.
        
        Args:
            name: Step identifier (for logging)
            forward: Async function that performs the step
            compensate: Async function that undoes the step (optional)
        """
        step = SagaStep(name=name, forward=forward, compensate=compensate)
        self._steps.append(step)
        logger.debug(f"Added step '{name} to saga {self.saga_id}")
    
    @abstractmethod
    def build_initial_context(self) -> dict[str, Any]:
        """
        Create the initial context for saga execution.
        
        Subclasses implement this to provide saga-specific starting data.
        
        Returns:
            Initial context dict that will flow through all steps
        """
        pass

    async def execute(self) -> SagaExecution:
        """
        Execute the saga, running all steps in order.
        
        If any step fails, automatically runs compensating transactions
        for all completed steps in REVERSE order.
        
        Returns:
            Final SagaExecution state
        """
        # Initialize
        context = self.build_initial_context()
        self._execution.context = dict(context)
        self._execution.start()

        logger.info(
            f"Starting saga {self.saga_id} ({self.__class__.__name__}) "
            f"with {len(self._steps)} steps"
        )

        completed_steps: list[SagaStep] = []

        try:
            # Execute each step in order
            for step in self._steps:
                logger.info(f"Saga {self.saga_id}: Executing '{step.name}'")

                try:
                    # Run forward action
                    context = await step.forward(context)

                    # Record succesful completion
                    completed_steps.append(step)
                    self._execution.complete_step(step.name)
                    self._execution.context = dict(context)

                    logger.info(f"Saga {self.saga_id}: '{step.name}' completed")

                except Exception as e:
                    # Step failed - need to compensate
                    logger.error(
                        f"Saga {self.saga_id}: '{step.name}' FAILED: {e}"
                    )
                    self._execution.fail(step.name, str(e))

                    # Run compensations for completed stepss
                    await self.compensate(completed_steps, context)
                    return self._execution
                
            # All steps completed successfully!
            self._execution.complete()
            logger.info(f"Saga {self.saga_id}: COMPLETED successfully")
            return self._execution
        
        except Exception as e:
            # Unexpected error during saga execution
            logger.exception(f"Saga {self.saga_id}: Unexpected error: {e}")
            self._execution.failed_unrecoverable(str(e))
            return self._execution
        
    async def compensate(
        self,
        completed_steps: list[SagaStep],
        context: dict[str, Any]
    ) -> None:
        """
        Run compensating transactions in REVERSE order.
        
        Compensation is BEST-EFFORT (unlike forward execution which stops on first failure):
        • Forward steps STOP on failure because later steps depend on earlier ones
        • Compensation steps CONTINUE because each cleanup is independent
        • Example: If release_funds fails, we still try release_risk to minimize cleanup work
        • Saga still ends in FAILED state, but with less manual intervention needed
        
        Args:
            completed_steps: Steps that were successfully executed
            context: Current saga context (has all IDs needed for compensation)
        """
        logger.warning(
            f"Saga {self.saga_id}: Starting compensation for "
            f"{len(completed_steps)} completed steps"
        )
        
        # REVERSE order - last completed step compensated first
        for step in reversed(completed_steps):
            if step.compensate is None:
                logger.info(
                    f"Saga {self.saga_id}: '{step.name}' has no compensation (skipping)"
                )
                continue
            
            try:
                logger.info(f"Saga {self.saga_id}: Compensating '{step.name}'")
                await step.compensate(context)
                logger.info(f"Saga {self.saga_id}: '{step.name}' compensated")
            except Exception as e:
                # Log but CONTINUE - we want to compensate as much as possible
                logger.error(
                    f"Saga {self.saga_id}: Compensation failed for "
                    f"'{step.name}': {e}. Continuing with other compensations..."
                )

        self._execution.compensated()
        logger.info(f"Saga {self.saga_id}: Compensation completed")