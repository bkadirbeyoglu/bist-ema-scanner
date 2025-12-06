"""
Mock Data Source for Development and Testing.

Generates realistic-looking price data without external dependencies.
Essential for:
- Local development (no API keys needed)
- Unit testing (deterministic data)
- Integration testing (fast, no rate limits)

DESIGN PATTERN: Adapter
- Implements DataSource protocol
- Provides mock data instead of real API calls
"""

import asyncio
import random
from datetime import datetime
from decimal import Decimal
from typing import Dict

from market_data_service.domain.entities import Quote, PriceSource


class MockDataSource:
    """
    Mock data source that generates realistic price movements.
    
    IMPLEMENTATION:
    - Starts with base prices for each symbol
    - Each call generates small random price changes
    - Simulates bid/ask spread and volume
    
    Usage:
        >>> source = MockDataSource()
        >>> await source.connect()
        >>> quote = await source.get_quote("AAPL")
        >>> quote.last_price
        Decimal('150.25')
    """
    
    def __init__(self):
        """Initialize mock data source with base prices."""
        self._connected = False
        
        # Base prices for common symbols
        # TRADING CONCEPT: These are approximate real prices as starting points
        self._base_prices: Dict[str, Decimal] = {
            "AAPL": Decimal("175.00"),
            "GOOGL": Decimal("140.00"),
            "MSFT": Decimal("375.00"),
            "AMZN": Decimal("175.00"),
            "TSLA": Decimal("250.00"),
            "META": Decimal("500.00"),
            "NVDA": Decimal("450.00"),
            "SPY": Decimal("450.00"),  # S&P 500 ETF
        }
        
        # Current prices (will fluctuate)
        self._current_prices: Dict[str, Decimal] = {}
    
    @property
    def source_name(self) -> str:
        """Data source identifier."""
        return "mock"
    
    async def connect(self) -> None:
        """
        Simulate connection to data source.
        
        In mock, this just initializes current prices from base prices.
        """
        # Initialize current prices from base
        self._current_prices = dict(self._base_prices)
        self._connected = True
    
    async def disconnect(self) -> None:
        """Simulate disconnection."""
        self._connected = False
        self._current_prices.clear()
    
    def is_connected(self) -> bool:
        """Check if connected."""
        return self._connected
    
    async def get_quote(self, symbol: str) -> Quote:
        """
        Generate a mock quote with realistic price movement.
        
        SIMULATION:
        - Price moves randomly within ±0.5% of current price
        - Bid/ask spread is 0.01-0.05% of price
        - Volume is randomized
        
        Args:
            symbol: Stock symbol (e.g., "AAPL")
            
        Returns:
            Quote with simulated market data
            
        Raises:
            ValueError: If symbol not in our mock data
        """
        if not self._connected:
            raise RuntimeError("Data source not connected")
        
        # Get current price (or use default for unknown symbols)
        if symbol not in self._current_prices:
            # Unknown symbol, generate random starting price
            self._current_prices[symbol] = Decimal(str(random.uniform(50, 500)))
        
        current_price = self._current_prices[symbol]
        
        # Simulate price movement (±0.5%)
        # PYTHON FEATURE: Decimal arithmetic for financial precision
        change_percent = Decimal(str(random.uniform(-0.005, 0.005)))
        price_change = current_price * change_percent
        new_price = current_price + price_change
        
        # Update stored price for next call
        self._current_prices[symbol] = new_price
        
        # Calculate bid/ask spread (0.01-0.05% of price)
        spread_percent = Decimal(str(random.uniform(0.0001, 0.0005)))
        half_spread = new_price * spread_percent / 2
        
        bid = new_price - half_spread
        ask = new_price + half_spread
        
        # Generate random volume
        volume = random.randint(100000, 10000000)
        
        # Generate random sizes at bid/ask
        bid_size = random.randint(100, 10000)
        ask_size = random.randint(100, 10000)
        
        return Quote(
            symbol=symbol,
            bid=bid.quantize(Decimal("0.01")),  # Round to cents
            ask=ask.quantize(Decimal("0.01")),
            bid_size=bid_size,
            ask_size=ask_size,
            last_price=new_price.quantize(Decimal("0.01")),
            volume=volume,
            timestamp=datetime.utcnow(),
            source=PriceSource.MOCK
        )
    
    def reset_prices(self) -> None:
        """Reset prices to base values (useful for testing)."""
        self._current_prices = dict(self._base_prices)
    
    def set_price(self, symbol: str, price: Decimal) -> None:
        """
        Manually set a price (for testing specific scenarios).
        
        Args:
            symbol: Stock symbol
            price: Exact price to set
        """
        self._current_prices[symbol] = price