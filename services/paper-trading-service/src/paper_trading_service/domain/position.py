"""
Position Entity.

Represents a holding in a single security with P&L tracking.

═══════════════════════════════════════════════════════════════════════════════
PYTHON FEATURE: __slots__
═══════════════════════════════════════════════════════════════════════════════

HOW PYTHON NORMALLY STORES ATTRIBUTES:
--------------------------------------
By default, every Python object has a __dict__ dictionary that stores its
attributes. This is flexible—you can add any attribute at any time:

    class RegularClass:
        def __init__(self):
            self.x = 1
            self.y = 2
    
    obj = RegularClass()
    obj.z = 3              # ✅ Works! Added dynamically
    print(obj.__dict__)    # {'x': 1, 'y': 2, 'z': 3}

The problem? Dictionaries are memory-hungry:
    • Each __dict__ uses ~100-200 bytes overhead
    • Plus memory for each key-value pair
    • For 10,000 Position objects: ~2-3 MB just for __dict__ overhead!

WHAT __slots__ DOES:
--------------------
__slots__ tells Python: "These are the ONLY attributes this class will have."
Python then uses a compact C-style struct instead of a dictionary:

    class SlottedClass:
        __slots__ = ('x', 'y')  # Declare all attributes upfront
        
        def __init__(self):
            self.x = 1
            self.y = 2
    
    obj = SlottedClass()
    obj.z = 3              # ❌ AttributeError! Can't add new attributes
    print(obj.__dict__)    # ❌ AttributeError! No __dict__ exists

MEMORY COMPARISON:
------------------
    Regular class:  ~400 bytes per instance
    With __slots__: ~200 bytes per instance
    Savings:        ~50% (adds up fast with many instances!)

    Example - Trading System:
    • 1,000 positions × 400 bytes = 400 KB (regular)
    • 1,000 positions × 200 bytes = 200 KB (with __slots__)
    • 1,000,000 price ticks: saves ~200 MB!

SPEED BENEFIT:
--------------
Attribute access is faster because Python uses a fixed offset
instead of a dictionary hash lookup:

    Regular:     obj.x → hash('x') → lookup in __dict__ → value
    __slots__:   obj.x → fixed offset 0 → value (direct memory access)

COMMON GOTCHA - Typo Protection:
--------------------------------
    class Order:
        __slots__ = ('symbol', 'quantity', 'price')
        ...
    
    order = Order()
    order.symol = "AAPL"   # ❌ AttributeError: 'Order' object has no attribute 'symol'
                           # Typo caught immediately! (would silently work without __slots__)

When to use __slots__:
    ✅ Many instances (thousands of positions, millions of ticks)
    ✅ Performance-critical inner loops
    ✅ Want to catch attribute typos
    ❌ Classes needing dynamic attributes (like ORMs, mocks)
    ❌ Classes using multiple inheritance with other slotted classes
═══════════════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class PositionSide(str, Enum):
    """Position direction.
    
    Inherits from str so JSON serialization works automatically:
        json.dumps({"side": PositionSide.LONG})  # {"side": "LONG"}
    """
    LONG = "LONG"
    SHORT = "SHORT"


class Position:
    """
    A position in a single security.
    
    Uses __slots__ for memory efficiency—important when tracking
    many positions across paper trading sessions.
    """
    
    # Define all instance attributes upfront
    __slots__ = (
        '_id',
        '_symbol',
        '_quantity',
        '_entry_price',
        '_side',
        '_created_at'
    )

    def __init__(
        self,
        symbol: str,
        quantity: int,
        entry_price: Decimal,
        side: PositionSide = PositionSide.LONG,
        position_id: UUID | None = None
    ) -> None:
        """
        Create a new position.
        
        Args:
            symbol: Trading symbol (e.g., "AAPL")
            quantity: Number of shares (must be positive)
            entry_price: Price per share at entry
            side: LONG or SHORT (default LONG)
            position_id: Optional UUID (auto-generated if omitted)
        
        Raises:
            ValueError: If quantity or price is not positive
        """
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        if entry_price <= 0:
            raise ValueError(f"Entry price must be positive, got {entry_price}")
        
        self._id: UUID = position_id or uuid4()
        self._symbol: str = symbol.upper()
        self._quantity: int = quantity
        self._entry_price: Decimal = Decimal(str(entry_price))
        self._side: PositionSide = side
        self._created_at: datetime = datetime.now(timezone.utc)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Read-only Properties
    # ═══════════════════════════════════════════════════════════════════════

    @property
    def id(self) -> UUID:
        return self._id
    
    @property
    def symbol(self) -> str:
        return self._symbol
    
    @property
    def quantity(self) -> int:
        return self._quantity
    
    @property
    def entry_price(self) -> Decimal:
        """Weighted average entry price."""
        return self._entry_price
    
    @property
    def side(self) -> PositionSide:
        return self._side
    
    @property
    def cost_basis(self) -> Decimal:
        """Total cost to acquire this position."""
        return self._entry_price * self._quantity
    
    @property
    def is_closed(self) -> bool:
        """True if position has been fully sold."""
        return self._quantity == 0
    
    # ═══════════════════════════════════════════════════════════════════════
    # P&L Calculations
    # ═══════════════════════════════════════════════════════════════════════
    
    def market_value(self, current_price: Decimal) -> Decimal:
        """Current market value of the position."""
        return Decimal(str(current_price)) * self._quantity
    
    def unrealized_pnl(self, current_price: Decimal) -> Decimal:
        """
        Unrealized P&L at given price.
        
        For LONG positions: profit when price > entry
        For SHORT positions: profit when price < entry
        """
        current = Decimal(str(current_price))
        price_diff = current - self._entry_price
        
        if self._side == PositionSide.SHORT:
            price_diff = -price_diff
        
        return price_diff * self._quantity
    
    # ═══════════════════════════════════════════════════════════════════════
    # Position Modifications
    # ═══════════════════════════════════════════════════════════════════════

    def add_shares(self, quantity: int, price: Decimal) -> None:
        """
        Add shares to position (scale in).
        
        Updates entry price using weighted average:
            new_avg = (old_qty x old_price + new_qty x new_price) / total_qty
        
        Args:
            quantity: Shares to add (positive)
            price: Price paid per share
        """
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        
        price = Decimal(str(price))

        # Weighted average calculation
        old_value = self._quantity * self._entry_price
        new_value = quantity * price
        total_qty = self.quantity + quantity

        self._entry_price = ((old_value + new_value) / total_qty).quantize(Decimal("0.01"))
        self._quantity = total_qty

    def remove_shares(self, quantity: int, price: Decimal) -> Decimal:
        """
        Remove shares from position (scale out or close).
        
        Args:
            quantity: Shares to remove
            price: Price received per share
            
        Returns:
            Realized P&L from this sale
            
        Raises:
            ValueError: If quantity exceeds holdings
        """
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got {quantity}")
        if quantity > self._quantity:
            raise ValueError(
                f"Cannot remove {quantity} shares, only holding {self._quantity}"
            )
        
        price = Decimal(str(price))
        
        # Calculate realized P&L
        price_diff = price - self._entry_price
        if self._side == PositionSide.SHORT:
            price_diff = -price_diff
        
        realized_pnl = price_diff * quantity
        
        # Update quantity (entry price unchanged for remaining shares)
        self._quantity -= quantity
        
        return realized_pnl
    
    def __repr__(self) -> str:
        return f"Position({self.symbol}, qty={self._quantity}, entry={self._entry_price})"
    
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Position):
            return NotImplemented
        return self._id == other._id
    
    def __hash__(self) -> int:
        return hash(self._id)