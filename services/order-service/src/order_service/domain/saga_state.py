"""
Saga State Machine.

Manages the lifecycle states of a saga execution.

NEW PYTHON FEATURE: Enum with auto()
════════════════════════════════════

The `auto()` function automatically generates unique values for enum members.
Instead of manually assigning values (RED = 1, GREEN = 2), auto() does it for you.

Basic Example:
    class Color(Enum):
        RED = auto()    # Value: 1
        GREEN = auto()  # Value: 2
        BLUE = auto()   # Value: 3

Why use auto()?
- Avoids accidental duplicate values (auto() guarantees uniqueness)
- Less maintenance when adding/removing enum members
- Signals that the actual value doesn't matter, only the identity

How values are generated:
- By default, auto() returns incrementing integers starting from 1
- You can customize this by overriding _generate_next_value_() method
- Values are assigned in definition order

Comparison behavior:
    state = SagaState.RUNNING
    state == SagaState.RUNNING      # True  - identity comparison
    state == 2                       # False - Enum doesn't equal int!
    state.value == 2                 # True  - but .value does

WHEN TO USE auto():
- ✅ Internal state tracking (like SagaState), values compared by identity only
- ✅ When you only care about distinguishing between states, not the actual values
- ❌ Don't use for API responses (values might change if you reorder enum members!)
- ❌ Don't use for database storage (same reason - reordering breaks data)
- ❌ Don't use when external systems depend on specific values

Rule of thumb: "Will this value be stored or sent outside Python?" → YES = explicit strings
"""

from enum import Enum, auto
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any


class SagaState(Enum):
    """
    Represents the current state of a saga execution.
    
    State Transition Diagram:
    ═════════════════════════
    
    PENDING ──► RUNNING ──► COMPLETED
                   │
                   ├──► COMPENSATING ──► COMPENSATED
                   │
                   └──► FAILED (if compensation also fails)
    """

    # Initial state when saga is created
    PENDING = auto()

    # Saga is actively executing steps
    RUNNING = auto()

    # All steps completed successfully
    COMPLETED = auto()

    # A step failed, running compensating transactions
    COMPENSATING = auto()

    # Compensation completed (saga rolled back successfully)
    COMPENSATED = auto()

    # Saga failed AND compensation failed (needs manual intervention!)
    FAILED = auto()

    def is_terminal(self) -> bool:
        """Check if this is a final state (saga won't change anymore)."""
        return self in (
            SagaState.COMPLETED,
            SagaState.COMPENSATED,
            SagaState.FAILED
        )
    
    def allows_compensation(self) -> bool:
        """Check if compensation can be triggered from this state."""
        return self in (SagaState.RUNNING, SagaState.COMPENSATING)
    

@dataclass
class SagaExecution:
    """
    Tracks the execution state of a saga instance.

    This is like a "flight recorder" for the saga - it maintains the complete history
    for debugging and recovery.

    ⚠️ NOTE: This is an IN-MEMORY implementation.
    ═══════════════════════════════════════════
    
    For learning purposes, we store saga state in memory.
    This means:
    • State is lost on service restart
    • Cannot recover incomplete sagas after crash
    
    Production requirements (Day 11):
    • Persist to PostgreSQL with event sourcing
    • Add saga state table with status column
    • Implement recovery on service restart
    • Add distributed locking for concurrent access
    """

    saga_id: str
    saga_type: str      # e.g., "OrderPlacementSaga"
    state: SagaState = SagaState.PENDING

    # Step tracking
    current_step_index: int = 0
    completed_steps: list[str] = field(default_factory=list)
    failed_step: Optional[str] = None
    error_message: Optional[str] = None

    # Timestamps:
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Context (saga-specific data that flows through steps)
    context: dict[str, Any] = field(default_factory=dict)

    def start(self) -> None:
        """Mark saga as started."""
        if self.state != SagaState.PENDING:
            raise ValueError(f"Cannot start saga in state {self.state}")
        self.state = SagaState.RUNNING
        self.started_at = datetime.now(timezone.utc)

    def complete_step(self, step_name: str) -> None:
        """Record successful completion of a step."""
        self.completed_steps.append(step_name)
        self.current_step_index += 1

    def fail(self, step_name: str, error: str) -> None:
        """Record step failure and transition to compensating."""
        self.failed_step = step_name
        self.error_message = error
        self.state = SagaState.COMPENSATING

    def complete(self) -> None:
        """Mark saga as successfully completed."""
        self.state = SagaState.COMPLETED
        self.completed_at = datetime.now(timezone.utc)

    def compensated(self) -> None:
        """Mark saga as successfully compensated (rolled back)."""
        self.state = SagaState.COMPENSATED
        self.completed_at = datetime.now(timezone.utc)

    def failed_unrecoverable(self, error: str) -> None:
        """Mark saga as failed (compensation also failed)."""
        self.state = SagaState.FAILED
        self.error_message = error
        self.completed_at = datetime.now(timezone.utc)



