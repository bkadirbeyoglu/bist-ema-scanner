"""
Virtual Portfolio.

The aggregate root for paper trading—manages cash and positions.

═══════════════════════════════════════════════════════════════════════════════
PYTHON FEATURE: TypedDict
═══════════════════════════════════════════════════════════════════════════════

THE PROBLEM WITH REGULAR DICTS:
-------------------------------
Regular dictionaries have no type information for their contents:

    def get_portfolio() -> dict:
        return {"cash": 85000, "positions": [...], "total_value": 100000}
    
    snapshot = get_portfolio()
    snapshot["cash"]         # What type is this? IDE doesn't know!
    snapshot["cach"]         # Typo - no error until runtime!
    snapshot["unknown_key"]  # Also no error until runtime

WHAT TypedDict DOES:
--------------------
TypedDict defines dictionaries with a specific structure and types:

    from typing import TypedDict
    
    class PortfolioSnapshot(TypedDict):
        cash: Decimal
        total_value: Decimal
        positions: list[dict]
    
    def get_portfolio() -> PortfolioSnapshot:
        return {"cash": Decimal("85000"), "total_value": Decimal("100000"), "positions": []}
    
    snapshot = get_portfolio()
    snapshot["cash"]         # ✅ IDE knows this is Decimal
    snapshot["cach"]         # ❌ Type error! Key doesn't exist
    snapshot["total_value"]  # ✅ IDE autocompletes this!

KEY BENEFITS:
-------------
1. IDE Autocomplete:
       snapshot["    # IDE shows: cash, total_value, positions
   
2. Type Checking:
       value: str = snapshot["cash"]  # ❌ Type error! cash is Decimal, not str

3. Typo Detection:
       snapshot["positoins"]  # ❌ Type error! Did you mean "positions"?

4. Self-Documenting:
       The TypedDict definition IS the documentation of the data structure.

RUNTIME BEHAVIOR:
-----------------
At runtime, TypedDict is just a regular dict—no performance overhead:

    snapshot = PortfolioSnapshot(cash=Decimal("85000"), ...)
    type(snapshot)           # <class 'dict'> - it's just a dict!
    isinstance(snapshot, dict)  # True

TypedDict vs dataclass vs NamedTuple:
-------------------------------------
    # TypedDict - when you need a dict (JSON serialization, API responses)
    class PersonDict(TypedDict):
        name: str
        age: int
    p: PersonDict = {"name": "Alice", "age": 30}
    json.dumps(p)  # ✅ Works directly: {"name": "Alice", "age": 30}

    # dataclass - when you need methods and behavior
    @dataclass
    class PersonClass:
        name: str
        age: int
        def greet(self) -> str:
            return f"Hi, I'm {self.name}"
    p = PersonClass("Alice", 30)
    json.dumps(p)  # ❌ Doesn't work directly

    # NamedTuple - immutable, memory-efficient, tuple-like
    class PersonTuple(NamedTuple):
        name: str
        age: int
    p = PersonTuple("Alice", 30)
    p[0]  # "Alice" - can access by index
    json.dumps(p)  # ✅ Works, but becomes array: ["Alice", 30]

COMMON PATTERN - Nested TypedDicts:
-----------------------------------
    class PositionSnapshot(TypedDict):
        symbol: str
        quantity: int
        unrealized_pnl: Decimal
    
    class PortfolioSnapshot(TypedDict):
        cash: Decimal
        positions: list[PositionSnapshot]  # Nested TypedDict!
    
    # Now IDE knows the full structure:
    snapshot["positions"][0]["symbol"]  # ✅ IDE knows this is str

When to use TypedDict:
    ✅ API responses with known structure
    ✅ JSON-serializable data transfer objects
    ✅ Configuration dictionaries
    ✅ When you need dict methods (.keys(), .items(), etc.)
    ❌ When you need custom methods (use dataclass)
    ❌ Dynamic data with unknown keys
    ❌ When you need immutability guarantees (use NamedTuple)
═══════════════════════════════════════════════════════════════════════════════
"""

from datetime import datetime, timezone
from decimal import Decimal
from typing import TypedDict
from uuid import UUID, uuid4

from paper_trading_service.domain.position import Position


class PositionSnapshot(TypedDict):
    """Snapshot of a single position."""
    symbol: str
    quantity: int
    entry_price: Decimal
    current_price: Decimal
    market_value: Decimal
    unrealized_pnl: Decimal


class PortfolioSnapshot(TypedDict):
    """Complete portfolio state at a point in time."""
    portfolio_id: str
    timestamp: str
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    unrealized_pnl: Decimal
    realized_pnl: Decimal
    total_pnl: Decimal
    return_percent: Decimal
    positions: list[PositionSnapshot]


class VirtualPortfolio:
    """
    Virtual portfolio for paper trading.
    
    This is the Aggregate Root—all modifications to positions
    must go through the portfolio to maintain invariants:
    
    • Cash cannot go negative
    • Positions must have positive quantity
    • All trades are recorded
    """
    
    def __init__(
        self,
        initial_cash: Decimal,
        portfolio_id: UUID | None = None,
    ) -> None:
        """Create a new virtual portfolio."""
        self._id = portfolio_id or uuid4()
        self._initial_cash = Decimal(str(initial_cash))
        self._cash = self._initial_cash
        self._positions: dict[str, Position] = {}
        self._realized_pnl = Decimal("0")
        self._created_at = datetime.now(timezone.utc)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Properties
    # ═══════════════════════════════════════════════════════════════════════
    
    @property
    def id(self) -> UUID:
        return self._id
    
    @property
    def cash(self) -> Decimal:
        return self._cash
    
    @property
    def initial_cash(self) -> Decimal:
        return self._initial_cash
    
    @property
    def position_count(self) -> int:
        return len(self._positions)
    
    @property
    def realized_pnl(self) -> Decimal:
        return self._realized_pnl
    
    @property
    def symbols(self) -> list[str]:
        return list(self._positions.keys())
    
    # ═══════════════════════════════════════════════════════════════════════
    # Position Access
    # ═══════════════════════════════════════════════════════════════════════
    
    def has_position(self, symbol: str) -> bool:
        """Check if holding a position in symbol."""
        return symbol.upper() in self._positions
    
    def get_position(self, symbol: str) -> Position | None:
        """Get position by symbol, or None."""
        return self._positions.get(symbol.upper())
    
    # ═══════════════════════════════════════════════════════════════════════
    # Trading Operations
    # ═══════════════════════════════════════════════════════════════════════
    
    def buy(self, symbol: str, quantity: int, price: Decimal) -> Position:
        """
        Buy shares.
        
        Args:
            symbol: Trading symbol
            quantity: Number of shares
            price: Price per share
            
        Returns:
            The position (new or updated)
            
        Raises:
            ValueError: If insufficient funds
        """
        symbol = symbol.upper()
        price = Decimal(str(price))
        cost = price * quantity
        
        if cost > self._cash:
            raise ValueError(
                f"Insufficient funds: need ${cost:,.2f}, have ${self._cash:,.2f}"
            )
        
        self._cash -= cost
        
        if symbol in self._positions:
            self._positions[symbol].add_shares(quantity, price)
        else:
            self._positions[symbol] = Position(symbol, quantity, price)
        
        return self._positions[symbol]
    
    def sell(self, symbol: str, quantity: int, price: Decimal) -> Decimal:
        """
        Sell shares.
        
        Args:
            symbol: Trading symbol
            quantity: Number of shares
            price: Price per share
            
        Returns:
            Realized P&L from this sale
            
        Raises:
            ValueError: If no position or insufficient shares
        """
        symbol = symbol.upper()
        position = self._positions.get(symbol)
        
        if position is None:
            raise ValueError(f"No position in {symbol}")
        
        price = Decimal(str(price))
        proceeds = price * quantity
        realized = position.remove_shares(quantity, price)
        
        self._cash += proceeds
        self._realized_pnl += realized
        
        # Remove closed positions
        if position.is_closed:
            del self._positions[symbol]
        
        return realized
    
    # ═══════════════════════════════════════════════════════════════════════
    # Valuation
    # ═══════════════════════════════════════════════════════════════════════
    
    def positions_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Total market value of all positions."""
        total = Decimal("0")
        for symbol, position in self._positions.items():
            price = prices.get(symbol, position.entry_price)
            total += position.market_value(price)
        return total
    
    def total_value(self, prices: dict[str, Decimal]) -> Decimal:
        """Total portfolio value (cash + positions)."""
        return self._cash + self.positions_value(prices)
    
    def unrealized_pnl(self, prices: dict[str, Decimal]) -> Decimal:
        """Sum of unrealized P&L across all positions."""
        total = Decimal("0")
        for symbol, position in self._positions.items():
            if symbol in prices:
                total += position.unrealized_pnl(prices[symbol])
        return total
    
    def total_pnl(self, prices: dict[str, Decimal]) -> Decimal:
        """Total P&L (realized + unrealized)."""
        return self._realized_pnl + self.unrealized_pnl(prices)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Snapshot
    # ═══════════════════════════════════════════════════════════════════════
    
    def snapshot(self, prices: dict[str, Decimal]) -> PortfolioSnapshot:
        """
        Create point-in-time snapshot.
        
        Args:
            prices: Current prices by symbol
            
        Returns:
            Complete state as TypedDict
        """
        position_snapshots: list[PositionSnapshot] = []
        
        for symbol, pos in self._positions.items():
            current_price = prices.get(symbol, pos.entry_price)
            position_snapshots.append(PositionSnapshot(
                symbol=symbol,
                quantity=pos.quantity,
                entry_price=pos.entry_price,
                current_price=current_price,
                market_value=pos.market_value(current_price),
                unrealized_pnl=pos.unrealized_pnl(current_price),
            ))
        
        pos_value = self.positions_value(prices)
        total = self._cash + pos_value
        unrealized = self.unrealized_pnl(prices)
        total_pnl = self._realized_pnl + unrealized
        
        return_pct = Decimal("0")
        if self._initial_cash > 0:
            return_pct = (total_pnl / self._initial_cash * 100).quantize(Decimal("0.01"))
        
        return PortfolioSnapshot(
            portfolio_id=str(self._id),
            timestamp=datetime.now(timezone.utc).isoformat(),
            cash=self._cash,
            positions_value=pos_value,
            total_value=total,
            unrealized_pnl=unrealized,
            realized_pnl=self._realized_pnl,
            total_pnl=total_pnl,
            return_percent=return_pct,
            positions=position_snapshots,
        )
    
    def __repr__(self) -> str:
        return f"VirtualPortfolio(cash=${self._cash:,.2f}, positions={self.position_count})"