"""
Market Data Domain Entities.

Core business objects for the Market Data Service.
Pure domain objects with no infrastructure dependencies.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional
from enum import Enum


class PriceSource(str, Enum):
    """
    Enumeration of price data sources.
    
    PYTHON FEATURE: str, Enum dual inheritance
    ──────────────────────────────────────────
    Inheriting from BOTH str and Enum makes the enum value behave as a string:
    
    - String comparison works:  PriceSource.MOCK == "mock"  → True
    - JSON serialization works: json.dumps({"source": PriceSource.MOCK})
                                → '{"source": "mock"}'
    
    Without str inheritance (plain Enum):
    - PriceSource.MOCK == "mock"  → False (must use PriceSource.MOCK.value to get "mock")
    - json.dumps() raises TypeError (not serializable)
    
    See DEEP DIVE section below for more details.
    """
    MOCK = "mock"
    ALPHA_VANTAGE = "alpha_vantage"
    YAHOO = "yahoo"
    WEBSOCKET = "websocket"


@dataclass(frozen=True)
class Price:
    """
    A single price point for a security.
    
    frozen=True makes it immutable (like a Value Object in DDD).
    """
    symbol: str
    price: Decimal          # Always use Decimal for money!
    timestamp: datetime
    source: PriceSource
    
    def __post_init__(self):
        """Validate after creation."""
        if not self.symbol or not self.symbol.strip():
            raise ValueError("Symbol cannot be empty")
        if self.price <= 0:
            raise ValueError(f"Price must be positive, got {self.price}")


@dataclass(frozen=True)
class Quote:
    """
    Full quote with bid/ask spread and volume.
    
    TRADING CONCEPTS:
    - Bid: Price buyers will pay (you SELL at this price)
    - Ask: Price sellers want (you BUY at this price)
    - Spread: ask - bid (market maker profit, liquidity indicator)
    """
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: int           # Number of shares at bid
    ask_size: int           # Number of shares at ask
    last_price: Decimal     # Most recent trade price
    volume: int             # Total shares traded today
    timestamp: datetime
    source: PriceSource
    
    @property
    def spread(self) -> Decimal:
        """Bid-ask spread. Narrow = liquid, wide = illiquid."""
        return self.ask - self.bid
    
    @property
    def mid_price(self) -> Decimal:
        """Midpoint between bid and ask. Often used as 'fair value'."""
        return (self.bid + self.ask) / 2
    
    @property
    def spread_percentage(self) -> Decimal:
        """Spread as % of mid price. More meaningful than absolute spread."""
        if self.mid_price == 0:
            return Decimal("0")
        return (self.spread / self.mid_price) * 100
    
    def to_price(self) -> Price:
        """Convert to simple Price (using last traded price)."""
        return Price(
            symbol=self.symbol,
            price=self.last_price,
            timestamp=self.timestamp,
            source=self.source
        )


@dataclass
class PriceHistory:
    """
    Collection of historical prices for a symbol.
    
    Note: NOT frozen because we need to add prices.
    """
    symbol: str
    prices: list[Price] = field(default_factory=list)
    max_length: int = 1000  # Prevent unbounded memory growth
    
    def add(self, price: Price) -> None:
        """Add price, maintaining max length (FIFO)."""
        if price.symbol != self.symbol:
            raise ValueError(
                f"Price symbol {price.symbol} doesn't match history {self.symbol}"
            )
        self.prices.append(price)
        if len(self.prices) > self.max_length:
            self.prices = self.prices[-self.max_length:]
    
    @property
    def latest(self) -> Optional[Price]:
        """Most recent price, or None if empty."""
        return self.prices[-1] if self.prices else None
    
    @property
    def price_count(self) -> int:
        """Number of prices in history."""
        return len(self.prices)
    
    def prices_since(self, since: datetime) -> list[Price]:
        """Get all prices after a given timestamp."""
        return [p for p in self.prices if p.timestamp > since]