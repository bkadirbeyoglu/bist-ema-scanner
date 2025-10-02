"""
Trade Entity representing an executed transaction.

Demonstrates:
- Enum for type-safe constants
- Factory methods for object creation
- Properties with setters for encapsulation
- Calculated properties for derived values
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, auto
from typing import Optional, ClassVar, Final
from uuid import UUID, uuid4
import logging

from trading_system.domain.value_objects.symbol import Symbol
from trading_system.domain.value_objects.money import Money

logger = logging.getLogger(__name__)

class TradeType(Enum):
    """ Type-safe trade direction """
    BUY = auto()
    SELL = auto()

@dataclass
class Trade:
    """
    Trade entity with identity and lifecycle.

    Key features:
    - Unique ID (entity characteristic)
    - Mutable state (can be settled)
    - Business login encapsulation
    """

    # Class-level configuration
    # ClassVar indicates this is shared across all instances
    # We can't use ClassVar[Final[Decimal]] - Python doesn't support nested type hints
    DEFAULT_COMMISSION_RATE: ClassVar[Decimal] = Decimal("0.001")  # Intended as final/constant

    # Required fields:
    symbol: Symbol
    quantity: int
    price: Money
    trade_type: TradeType

    # Optional with defaults
    commission_rate: Decimal = field(
        default_factory=lambda: Trade.DEFAULT_COMMISSION_RATE
    )

    # Auto-generated
    id: UUID = field(default_factory=uuid4)
    executed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Private state with property access
    _settled: bool = field(default=False, init=False, repr=False)
    settled_at: Optional[datetime] = field(default=None, init=False)

    def __post_init__(self) -> None:
        """ Validate business rules """
        if self.quantity <= 0:
            raise ValueError("Trade quantity must be positive")
        
        if self.commission_rate < 0:
            raise ValueError("Commission rate cannot be negative")
        
    # Calculated properties
    @property
    def total_value(self) -> Money:
        """ Price * quantity """
        return self.price * self.quantity
    
    @property
    def commission(self) -> Money:
        """ Commission amount """
        amount = self.total_value.amount * self.commission_rate
        return Money(amount.quantize(Decimal('0.01')), self.total_value.currency)
    
    @property
    def total_cost(self) -> Money:
        """ Total cost for buy trades """
        if self.trade_type != TradeType.BUY:
            raise ValueError("total cost only for BUY trades")
        return self.total_value + self.commission
    
    @property
    def net_proceeds(self) -> Money:
        """ Net proceeds for sell trades """
        if self.trade_type != TradeType.SELL:
            raise ValueError("net proceeds only for SELL trades")
        return self.total_value - self.commission
    
    # Property with setter
    @property
    def settled(self) -> bool:
        return self._settled
    
    @settled.setter
    def settled(self, value: bool) -> None:
        """ Set with validation and side effects """
        if self._settled and not value:
            raise ValueError("Cannot unsettle a settled trade")
        
        if value and not self._settled:
            self._settled = True
            self.settled_at = datetime.now(timezone.utc)
            logger.info(f"Trade {self.id} settled")

    # Factory methods
    @classmethod
    def create_buy(cls, symbol: Symbol, quantity: int, price: Money, **kwargs) -> 'Trade':
        """ Factory for buy trades """
        return cls(symbol=symbol, quantity=quantity, price=price,
                   trade_type=TradeType.BUY, **kwargs)
    
    @classmethod
    def create_sell(cls, symbol: Symbol, quantity: int, price: Money, **kwargs) -> 'Trade':
        """ Factory for buy trades """
        return cls(symbol=symbol, quantity=quantity, price=price,
                   trade_type=TradeType.SELL, **kwargs)
    
    # Entity equality (by ID, not attributes)
    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Trade):
            return NotImplemented
        return self.id == other.id
    
    def __hash__(self) -> int:
        return hash(self.id)
    
    
    


