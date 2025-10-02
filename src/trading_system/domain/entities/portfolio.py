"""
Portfolio - Aggregate root managing positions and cash.

Advanced features:
- Context manager for transactions
- Generators for efficient iteration
- Complex state management
"""

# PYTHON FEATURE: __future__ import for forward references
# This allows us to use 'Portfolio' as a type hint inside the Portfolio class itself
# Without this, we'd need to use string quotes: 'Portfolio'

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, List, Optional, Iterator, Generator
from uuid import UUID, uuid4
import logging

from trading_system.domain.entities.trade import Trade, TradeType
from trading_system.domain.value_objects.symbol import Symbol
from trading_system.domain.value_objects.money import Money
from trading_system.domain.exceptions import *

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """
    Position in a single security.
    
    DESIGN PATTERN: Part of aggregate
    - Not directly accessible from outside Portfolio
    - Portfolio maintains consistency
    - All modifications go through Portfolio methods
    """

    symbol: Symbol
    quantity: int = 0

    # PYTHON PATTERN: Private attribute with None default
    # We use Optional[Money] with None default to avoid mutable default issues
    # The actual Money object is created in __post_init__
    _average_cost: Optional[Money] = field(default=None, init=False)

    # PYTHON DATACLASS FIELD() EXPLAINED:
    # 
    # field() gives fine control over dataclass attributes.
    # Key parameters:
    #   - default: For immutable default values
    #   - default_factory: For mutable defaults or function calls
    #   - init: Include in __init__? (default True)
    #   - repr: Include in __repr__? (default True)
    #   - compare: Include in __eq__? (default True)
    
    # CRITICAL PYTHON GOTCHA: Mutable default arguments
    # NEVER do this: trades: List[Trade] = []  # All instances share same list!
    # 
    # Why? The [] is created ONCE when class is defined, not per instance.
    # Example of the problem:
    #   p1 = Portfolio()
    #   p2 = Portfolio()
    #   p1.trades.append(trade)
    #   print(p2.trades)  # [trade] - p2 has p1's trades!
    #
    # ALWAYS use field(default_factory=list) for mutable defaults
    # default_factory is a FUNCTION called for each instance:
    #   - list means: call list() to create new empty list
    #   - dict means: call dict() to create new empty dict
    #   - lambda: ... for complex initialization
    trades: List[Trade] = field(default_factory=list)       # Avoid mutable default!

    def __post_init__(self):
        """
        Initialize average cost after instance creation.
        
        This pattern avoids the mutable default problem:
        - Can't use Money.zero() as default (would be shared)
        - Can't use field(default_factory=Money.zero) (Money.zero needs currency arg)
        - Solution: Use None, then create Money here
        """
        if self._average_cost is None:
            self._average_cost = Money.zero()

    @property
    def average_cost(self) -> Money:
        """
        Read-only property for average cost.
        
        ENCAPSULATION PATTERN:
        - Private _average_cost can't be directly modified
        - Only updated through add_trade() method
        - Ensures consistency of calculation
        """
        return self._average_cost
    
    @property
    def market_value(self) -> Money:
        """
        Calculate current position value.
        
        Python features:
        - @property makes this accessible like an attribute
        - Calculated on-demand (not stored)
        - abs() handles both long and short positions
        """
        if self.quantity == 0:
            return Money.zero(self._average_cost.currency)
        
        # abs() for absolute value - works for negative quantities (short positions)
        return self._average_cost * abs(self.quantity)
    
    def add_trade(self, trade: Trade) -> Position:
        """
        Process trade and update position.
        
        METHOD CHAINING PATTERN:
        - Returns self to enable: position.add_trade(t1).add_trade(t2)
        - Common in Python (pandas, SQLAlchemy use this pattern)
        - Makes code more fluent and readable
        
        Returns:
            Position: Returns self for method chaining
        """
        self.trades.append(trade)
        
        if trade.trade_type == TradeType.BUY:
            # Average cost recalculation for FIFO accounting
            if self.quantity >= 0:
                # PYTHON NUMERIC OPERATIONS:
                # Using Money's operator overloading (__mul__, __add__)
                total = (self._average_cost * self.quantity) + trade.total_cost
                self.quantity += trade.quantity
                
                if self.quantity > 0:
                    # Decimal division preserves precision
                    # str() conversion ensures no float contamination
                    self._average_cost = Money(
                        total.amount / Decimal(str(self.quantity)),
                        total.currency
                    )
        else:  # SELL
            if trade.quantity > self.quantity:
                raise InvalidQuantityError(trade.quantity, f"Only have {self.quantity}")
            self.quantity -= trade.quantity
        
        return self  # Enable chaining: position.add_trade(t1).add_trade(t2)
    
    
@dataclass
class Portfolio:
    """
    Portfolio aggregate root.
    
    AGGREGATE ROOT PATTERN (DDD):
    - Entry point for all position modifications
    - Maintains consistency across positions and cash
    - Enforces all business rules
    - Provides transaction boundaries
    
    Advanced Python features demonstrated:
    - Context managers for transactions
    - Generators for memory-efficient iteration
    - Properties for computed values
    - Complex state management with rollback
    """
    
    # FIELD() WITH DEFAULT_FACTORY PATTERNS:
    #
    # default_factory must be a callable (function) that returns the default value
    # Common patterns:
    #
    # 1. Simple factory functions (no arguments):
    #    field(default_factory=list)    → calls list() → []
    #    field(default_factory=dict)    → calls dict() → {}
    #    field(default_factory=set)     → calls set()  → set()
    #    field(default_factory=uuid4)   → calls uuid4() → new UUID
    #
    # 2. Lambda for functions with arguments:
    #    field(default_factory=lambda: Money(Decimal("10000")))
    #    field(default_factory=lambda: datetime.now(timezone.utc))
    #    
    # Why lambda? Because default_factory needs a function with NO arguments.
    # Money(Decimal("10000")) is a function CALL (returns Money object)
    # lambda: Money(Decimal("10000")) is a FUNCTION (returns function that creates Money)

    name: str

    # Lambda wraps Money constructor with arguments
    # Each portfolio gets its own Money instance with $10,000
    cash: Money = field(default_factory=lambda: Money(Decimal("10000.00")))
    
    # TYPE HINTS: Dict[str, Position]
    # Tells IDEs and type checkers that:
    # - Keys are strings (symbol names)
    # - Values are Position objects
    # dict is the function that creates empty dictionary
    positions: Dict[str, Position] = field(default_factory=dict)
    
    # list is the function that creates empty list
    trades: List[Trade] = field(default_factory=list)
    
    # uuid4 is a function that generates new UUID
    id: UUID = field(default_factory=uuid4)

    # Risk management limits with lambda for complex defaults
    max_position_size: Money = field(default_factory=lambda: Money(Decimal("50000.00")))
    max_positions: int = 10

    # TRANSACTION STATE MANAGEMENT
    # Leading underscore indicates "private" (convention, not enforced)
    # init=False: Not included in __init__ parameters
    # This means you CAN'T do: Portfolio(..., _in_transaction=True)
    # The field is created but not part of constructor
    _in_transaction: bool = field(default=False, init=False)

    # None is immutable, so we can use 'default' instead of 'default_factory'
    # init=False means not in constructor parameters
    _transaction_backup: Optional[Dict] = field(default=None, init=False)


    @contextmanager
    def transaction(self):
        """
        Context manager for all-or-nothing transaction execution.
        
        PYTHON CONTEXT MANAGER PATTERN:
        
        How it works:
        1. Code before 'yield' runs when entering 'with' block
        2. 'yield' pauses and runs the with block
        3. Code after 'yield' runs when exiting (even on exception)
        4. 'finally' always runs for cleanup
        
        Usage:
            with portfolio.transaction():
                portfolio.execute_trade(trade1)  # These run at yield
                portfolio.execute_trade(trade2)
                # If any trade fails, all are rolled back
        
        @contextmanager decorator:
        - Converts generator function into context manager
        - Simpler than implementing __enter__ and __exit__
        - 'yield' marks where the with block executes
        
        Why use context managers?
        - Guaranteed cleanup (even on exceptions)
        - Clear transaction boundaries
        - Automatic rollback on failure
        - Similar to database transactions
        """
        if self._in_transaction:
            raise RuntimeError("Already in transaction")
        
        # ENTER PHASE: Backup current state
        self._in_transaction = True

        # PYTHON COPYING PATTERNS:
        # dict(self.positions): Creates shallow copy of dictionary
        # self.trades.copy(): Creates shallow copy of list
        # We store references to original objects (sufficient for rollback)
        self._transaction_backup = {
            "cash": self.cash,  # Money is immutable, so reference is safe
            "positions": dict(self.positions),  # Shallow copy of dict
            "trades": self.trades.copy()  # Shallow copy of list
        }

        try:
            # YIELD: This is where the 'with' block code executes
            # Execution pauses here and resumes after the with block
            yield
        
            # COMMIT PHASE: If we reach here, no exception occurred
            self._transaction_backup = None
            logger.info("Transaction committed")

        except Exception as e:
            # ROLLBACK PHASE: Exception occurred in with block
            logger.error(f"Transaction failed, rolling back: {e}")
        
            if self._transaction_backup:
                # Restore previous state
                self.cash = self._transaction_backup['cash']
                self.positions = self._transaction_backup['positions']
                self.trades = self._transaction_backup['trades']
            
            # Re-raise exception to caller
            # This preserves the stack trace for debugging
            raise

        finally:
            # CLEANUP PHASE: Always executed
            # Ensures we don't stay in transaction state
            self._in_transaction = False
            self._transaction_backup = None

    def execute_trade(self, trade: Trade):
        """
        Execute trade with validation and error handling.
        
        PYTHON EXCEPTION CHAINING:
        - 'raise ... from e' preserves original exception
        - Creates linked exception chain
        - Original traceback available for debugging
        - Better than losing original error context
        """
        try:
            # Currency validation
            if trade.price.currency != self.cash.currency:
                raise ValueError("Currency mismatch")

            if trade.trade_type == TradeType.BUY:
                # Insufficient funds check
                if trade.total_cost > self.cash:
                    # Custom exception with rich context
                    raise InsufficientFundsError(
                        trade.total_cost.amount,
                        self.cash.amount,
                        self.cash.currency
                    )
                
                # Using Money's __sub__ operator overloading
                self.cash -= trade.total_cost

                # STRING CONVERSION PATTERN:
                # str(trade.symbol) converts Symbol to string for dict key
                # Ensures consistent key format
                symbol_str = str(trade.symbol)

                # Create position if doesn't exist
                if symbol_str not in self.positions:
                    self.positions[symbol_str] = Position(trade.symbol)
                
                # Method chaining on position
                self.positions[symbol_str].add_trade(trade)

            else:  # SELL
                symbol_str = str(trade.symbol)
                
                # Check position exists
                if symbol_str not in self.positions:
                    raise PositionNotFoundError(symbol_str)
                
                position = self.positions[symbol_str]
                position.add_trade(trade)  # Will validate quantity internally
                
                # Using Money's __add__ operator overloading
                self.cash += trade.net_proceeds
                
                # Clean up closed positions
                if position.quantity == 0:
                    # del removes key from dictionary
                    del self.positions[symbol_str]
            
            self.trades.append(trade)
            
        except (InsufficientFundsError, PositionNotFoundError, InvalidQuantityError):
            # Domain exceptions pass through unchanged
            raise
        
        except Exception as e:
            raise RuntimeError(f"Trade execution failed: {trade.id}") from e
        
    @property
    def total_value(self) -> Money:
        """
        Calculate total portfolio value.
        
        PROPERTY PATTERN:
        - Accessed like attribute: portfolio.total_value
        - Calculated on-demand (not stored)
        - Always up-to-date
        - No parentheses when accessing
        
        Python iteration:
        - positions.values() returns dict values
        - Iterating and summing using Money's __add__
        """
        total = self.cash
        
        # Iterate over all positions
        # dict.values() returns view of dictionary values
        for position in self.positions.values():
            # Uses Money.__add__ operator overloading
            total += position.market_value
        
        return total
    
    def iter_long_positions(self) -> Generator[Position, None, None]:
        """
        Generate long positions using yield.
        
        GENERATOR FUNCTION PATTERN:
        
        What is a generator?
        - Function that uses 'yield' instead of 'return'
        - Produces values one at a time (lazy evaluation)
        - Doesn't create list in memory
        - Pauses and resumes execution
        
        Generator[Position, None, None] type hint means:
        - Yields: Position objects
        - Receives: Nothing (None)
        - Returns: Nothing (None)
        
        Why use generators?
        - Memory efficient (no list created)
        - Can handle infinite sequences
        - Caller can stop early without waste
        - Perfect for large portfolios
        
        Example usage:
            for position in portfolio.iter_long_positions():
                print(position)  # Processes one at a time
                if some_condition:
                    break  # Generator stops, no waste
        
        Compare to list approach (less efficient):
            def get_long_positions(self) -> List[Position]:
                return [p for p in self.positions.values() if p.quantity > 0]
            # This creates entire list in memory immediately
        """
        for position in self.positions.values():
            if position.quantity > 0:
                # yield pauses function and returns position
                # Function resumes here on next iteration
                yield position
                # Execution continues from here when next() called again
    
    def get_position(self, symbol: Symbol) -> Optional[Position]:
        """
        Get position for symbol if exists.
        
        TYPE HINT: Optional[Position]
        - Means: Position or None
        - Same as: Union[Position, None]
        - Tells callers to handle None case
        - Better than just returning None without type hint
        
        dict.get() method:
        - Returns value if key exists
        - Returns None if key doesn't exist
        - Safer than positions[key] which raises KeyError
        """
        return self.positions.get(str(symbol))
    
    def has_position(self, symbol: Symbol) -> bool:
        """
        Check if portfolio has position.
        
        PYTHON IDIOM: 'in' operator
        - Checks dictionary key existence
        - More Pythonic than: positions.get(key) is not None
        - Very efficient for dictionaries (O(1) lookup)
        """
        return str(symbol) in self.positions