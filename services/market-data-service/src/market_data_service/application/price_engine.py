"""
Price Engine - Core Application Service.

The heart of the Market Data Service:
1. Coordinates data sources
2. Validates prices
3. Publishes price updates to SQS
"""

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable
import structlog

from market_data_service.domain.entities import Quote, Price, PriceSource, PriceHistory
from market_data_service.domain.events import (
    PriceUpdatedEvent,
    QuoteReceivedEvent,
    DataSourceConnectedEvent,
    DataSourceDisconnectedEvent
)
from market_data_service.config import Settings

logger = structlog.get_logger()

# ──────────────────────────────────────────────────────────────────────────────
# PORT DEFINITIONS (Interfaces)
# ──────────────────────────────────────────────────────────────────────────────
#
# These Protocols define WHAT the Price Engine needs, not HOW it's implemented.
# Any class with matching methods satisfies the Protocol - no inheritance needed!
#

@runtime_checkable
class DataSource(Protocol):
    """
    Interface for price data sources.
    
    PYTHON FEATURE: Protocol + @runtime_checkable
    Unlike ABC, Protocol uses structural typing ("duck typing with type hints").
    Any class with these methods works - no inheritance required!
    
    See DEEP DIVE at end of file for ABC vs Protocol comparison.
    """
    
    async def connect(self) -> None:
        """Establish connection to data source."""
        ...
    
    async def disconnect(self) -> None:
        """Close connection to data source."""
        ...
    
    async def get_quote(self, symbol: str) -> Quote:
        """Get current quote for a symbol."""
        ...
    
    def is_connected(self) -> bool:
        """Check if connected to data source."""
        ...
    
    @property
    def source_name(self) -> str:
        """Name of the data source for logging."""
        ...


@runtime_checkable
class EventPublisher(Protocol):
    """
    Interface for publishing domain events.
    
    Implementations: SQSPublisher, KafkaPublisher (future), MockPublisher (tests)
    """
    
    async def publish(self, event: PriceUpdatedEvent) -> None:
        """Publish a price update event."""
        ...
    
    async def connect(self) -> None:
        """Connect to message broker."""
        ...
    
    async def disconnect(self) -> None:
        """Disconnect from message broker."""
        ...

class PriceEngine:
    """
    Orchestrates price data collection and publishing.
    
    Responsibilities:
    - Manage data source connections
    - Fetch and validate prices
    - Publish price updates to SQS
    - Maintain price history cache
    
    Usage:
        engine = PriceEngine(settings, [MockDataSource()], sqs_publisher)
        await engine.start()   # Begins streaming prices
        # ... later ...
        await engine.stop()    # Graceful shutdown
    """
    
    def __init__(
        self,
        settings: Settings,
        data_sources: list[DataSource],
        publisher: EventPublisher,
        symbols: list[str] | None = None
    ):
        self._settings = settings
        self._data_sources = data_sources
        self._publisher = publisher
        self._symbols = symbols or ["AAPL", "GOOGL", "MSFT", "AMZN", "TSLA"]
        
        # State
        self._running = False
        self._stream_task: asyncio.Task | None = None
        
        # Cache: symbol → latest Quote
        self._latest_prices: dict[str, Quote] = {}
        
        # History: symbol → PriceHistory
        self._price_history: dict[str, PriceHistory] = {
            symbol: PriceHistory(symbol=symbol)
            for symbol in self._symbols
        }
        
        self._logger = logger.bind(component="price_engine")
    
    @property
    def is_running(self) -> bool:
        """Check if engine is currently streaming prices."""
        return self._running
    
    @property
    def tracked_symbols(self) -> list[str]:
        """List of symbols being tracked."""
        return list(self._symbols)
    
    async def start(self) -> None:
        """
        Start the price engine.
        
        1. Connect to all data sources
        2. Connect to event publisher
        3. Start background price streaming task
        """
        if self._running:
            self._logger.warning("Engine already running")
            return
        
        self._logger.info("Starting price engine", symbols=self._symbols)
        
        # Connect to data sources
        for source in self._data_sources:
            await source.connect()
            self._logger.info("Connected to data source", source=source.source_name)
        
        # Connect to publisher
        await self._publisher.connect()
        self._logger.info("Connected to event publisher")
        
        # Start streaming task
        self._running = True
        self._stream_task = asyncio.create_task(self._stream_prices())
        
        self._logger.info("Price engine started")
    
    async def stop(self) -> None:
        """
        Stop the price engine gracefully.
        
        1. Cancel streaming task
        2. Disconnect from data sources
        3. Disconnect from publisher
        """
        if not self._running:
            return
        
        self._logger.info("Stopping price engine")
        self._running = False
        
        # Cancel streaming task
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
        
        # Disconnect from data sources
        for source in self._data_sources:
            await source.disconnect()
        
        # Disconnect from publisher
        await self._publisher.disconnect()
        
        self._logger.info("Price engine stopped")
    
    async def _stream_prices(self) -> None:
        """
        Background task: fetch and publish prices at configured interval.
        """
        interval_sec = self._settings.price_update_interval_ms / 1000
        
        while self._running:
            try:
                await self._fetch_and_publish_all()
                await asyncio.sleep(interval_sec)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error("Error in price stream", error=str(e))
                await asyncio.sleep(1)  # Back off on error
    
    async def _fetch_and_publish_all(self) -> None:
        """Fetch prices for all symbols and publish events."""
        # Fan-out: fetch all symbols concurrently
        tasks = [
            self._fetch_and_publish_symbol(symbol)
            for symbol in self._symbols
        ]
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _fetch_and_publish_symbol(self, symbol: str) -> None:
        """Fetch price for one symbol and publish event."""
        try:
            quote = await self._fetch_quote(symbol)
            
            if quote and self._validate_quote(quote):
                # Update cache
                self._latest_prices[symbol] = quote
                
                # Update history
                price = quote.to_price()
                self._price_history[symbol].add(price)
                
                # Publish event
                event = PriceUpdatedEvent(
                    symbol=quote.symbol,
                    price=quote.last_price,
                    bid=quote.bid,
                    ask=quote.ask,
                    volume=quote.volume,
                    source=quote.source.value
                )
                await self._publisher.publish(event)
                
        except Exception as e:
            self._logger.error(
                "Failed to fetch/publish price",
                symbol=symbol,
                error=str(e)
            )
    
    async def _fetch_quote(self, symbol: str) -> Quote | None:
        """
        Fetch quote from first available data source.
        
        Tries each source in order until one succeeds (failover pattern).
        """
        for source in self._data_sources:
            if not source.is_connected():
                continue
            try:
                return await source.get_quote(symbol)
            except Exception as e:
                self._logger.warning(
                    "Data source failed",
                    source=source.source_name,
                    symbol=symbol,
                    error=str(e)
                )
        return None
    
    def _validate_quote(self, quote: Quote) -> bool:
        """
        Validate quote data.
        
        Checks:
        - Price is positive
        - Bid < Ask (crossed quotes are invalid)
        - Volume is non-negative
        """
        if quote.last_price <= 0:
            self._logger.warning("Invalid price", symbol=quote.symbol, price=quote.last_price)
            return False
        
        if quote.bid >= quote.ask:
            self._logger.warning(
                "Crossed quote (bid >= ask)",
                symbol=quote.symbol,
                bid=quote.bid,
                ask=quote.ask
            )
            return False
        
        if quote.volume < 0:
            self._logger.warning("Negative volume", symbol=quote.symbol, volume=quote.volume)
            return False
        
        return True
    
    # ─────────────────────────────────────────────────────────────────────────
    # Query Methods (for API endpoints)
    # ─────────────────────────────────────────────────────────────────────────
    
    def get_latest_price(self, symbol: str) -> Quote | None:
        """Get most recent quote for a symbol."""
        return self._latest_prices.get(symbol)
    
    def get_all_prices(self) -> dict[str, Quote]:
        """Get all current prices."""
        return dict(self._latest_prices)
    
    def get_price_history(self, symbol: str) -> PriceHistory | None:
        """Get price history for a symbol."""
        return self._price_history.get(symbol)
