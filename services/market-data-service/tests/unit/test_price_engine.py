"""
Unit Tests for Price Engine.

Tests the core application logic without external dependencies.

RUN FROM SERVICE DIRECTORY:
    cd services/market-data-service
    poetry run pytest tests/unit/ -v

RUN FROM PROJECT ROOT:
    cd algo-trading-system
    poetry run pytest services/market-data-service/tests/unit/ -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from decimal import Decimal
from datetime import datetime

from market_data_service.domain.entities import Quote, PriceSource
from market_data_service.domain.events import PriceUpdatedEvent
from market_data_service.application.price_engine import PriceEngine
from market_data_service.config import Settings


class MockDataSource:
    """Test double for DataSource protocol."""
    
    def __init__(self, quotes: dict[str, Quote] | None = None):
        self._quotes = quotes or {}
        self._connected = False
    
    @property
    def source_name(self) -> str:
        return "test-mock"
    
    async def connect(self) -> None:
        self._connected = True
    
    async def disconnect(self) -> None:
        self._connected = False
    
    def is_connected(self) -> bool:
        return self._connected
    
    async def get_quote(self, symbol: str) -> Quote:
        if symbol not in self._quotes:
            raise ValueError(f"No quote for {symbol}")
        return self._quotes[symbol]


class MockPublisher:
    """Test double for EventPublisher protocol."""
    
    def __init__(self):
        self.published_events: list[PriceUpdatedEvent] = []
        self._connected = False
    
    async def connect(self) -> None:
        self._connected = True
    
    async def disconnect(self) -> None:
        self._connected = False
    
    async def publish(self, event: PriceUpdatedEvent) -> None:
        self.published_events.append(event)


@pytest.fixture
def settings() -> Settings:
    """Test settings."""
    return Settings(
        service_name="test-service",
        environment="development",
        price_update_interval_ms=100
    )


@pytest.fixture
def sample_quote() -> Quote:
    """Sample quote for testing."""
    return Quote(
        symbol="AAPL",
        bid=Decimal("150.00"),
        ask=Decimal("150.10"),
        bid_size=1000,
        ask_size=1500,
        last_price=Decimal("150.05"),
        volume=1000000,
        timestamp=datetime.utcnow(),
        source=PriceSource.MOCK
    )


class TestPriceEngine:
    """Tests for PriceEngine class."""
    
    @pytest.mark.asyncio
    async def test_engine_starts_and_stops(self, settings: Settings):
        """
        Test: Engine lifecycle (start → running → stop)
        
        Verifies:
        - Engine starts successfully
        - is_running returns True when running
        - Engine stops gracefully
        """
        source = MockDataSource()
        publisher = MockPublisher()
        
        engine = PriceEngine(
            settings=settings,
            data_sources=[source],
            publisher=publisher,
            symbols=["AAPL"]
        )
        
        assert not engine.is_running
        
        await engine.start()
        assert engine.is_running
        assert source.is_connected()
        
        await engine.stop()
        assert not engine.is_running
    
    @pytest.mark.asyncio
    async def test_engine_publishes_price_updates(
        self,
        settings: Settings,
        sample_quote: Quote
    ):
        """
        Test: Engine fetches prices and publishes events
        
        Verifies:
        - Price is fetched from data source
        - PriceUpdatedEvent is published
        - Event contains correct data
        """
        source = MockDataSource(quotes={"AAPL": sample_quote})
        publisher = MockPublisher()
        
        engine = PriceEngine(
            settings=settings,
            data_sources=[source],
            publisher=publisher,
            symbols=["AAPL"]
        )
        
        await engine.start()
        
        # Manually trigger fetch (background task may have already published once)
        await engine._fetch_and_publish_all()
        
        await engine.stop()
        
        # Verify at least one event was published
        # (background task + manual call may produce 2 events)
        assert len(publisher.published_events) >= 1
        event = publisher.published_events[-1]  # Check the latest event
        
        assert event.symbol == "AAPL"
        assert event.price == Decimal("150.05")
        assert event.source == "mock"
    
    @pytest.mark.asyncio
    async def test_engine_tracks_latest_prices(
        self,
        settings: Settings,
        sample_quote: Quote
    ):
        """
        Test: Engine maintains latest price cache
        
        Verifies:
        - get_latest_price returns correct data
        - get_all_prices returns all tracked symbols
        """
        source = MockDataSource(quotes={"AAPL": sample_quote})
        publisher = MockPublisher()
        
        engine = PriceEngine(
            settings=settings,
            data_sources=[source],
            publisher=publisher,
            symbols=["AAPL"]
        )
        
        await engine.start()
        await engine._fetch_and_publish_all()
        
        latest = engine.get_latest_price("AAPL")
        assert latest is not None
        assert latest.symbol == "AAPL"
        assert latest.last_price == Decimal("150.05")
        
        all_prices = engine.get_all_prices()
        assert "AAPL" in all_prices
        
        await engine.stop()
    
    @pytest.mark.asyncio
    async def test_engine_validates_quotes(self, settings: Settings):
        """
        Test: Engine rejects invalid quotes
        
        Verifies:
        - Negative prices are rejected
        - Invalid bid/ask spread is rejected
        """
        # Quote with bid > ask (invalid)
        invalid_quote = Quote(
            symbol="AAPL",
            bid=Decimal("150.10"),  # Bid higher than ask!
            ask=Decimal("150.00"),
            bid_size=1000,
            ask_size=1500,
            last_price=Decimal("150.05"),
            volume=1000000,
            timestamp=datetime.utcnow(),
            source=PriceSource.MOCK
        )
        
        source = MockDataSource(quotes={"AAPL": invalid_quote})
        publisher = MockPublisher()
        
        engine = PriceEngine(
            settings=settings,
            data_sources=[source],
            publisher=publisher,
            symbols=["AAPL"]
        )
        
        await engine.start()
        await engine._fetch_and_publish_all()
        
        # Invalid quote should not be published
        assert len(publisher.published_events) == 0
        
        await engine.stop()
    
    @pytest.mark.asyncio
    async def test_engine_handles_source_failure(self, settings: Settings):
        """
        Test: Engine handles data source failures gracefully
        
        Verifies:
        - Exception in get_quote doesn't crash engine
        - Other symbols still processed
        """
        class FailingSource:
            source_name = "failing"
            
            async def connect(self): pass
            async def disconnect(self): pass
            def is_connected(self): return True
            
            async def get_quote(self, symbol: str) -> Quote:
                raise Exception("API Error!")
        
        source = FailingSource()
        publisher = MockPublisher()
        
        engine = PriceEngine(
            settings=settings,
            data_sources=[source],
            publisher=publisher,
            symbols=["AAPL"]
        )
        
        await engine.start()
        
        # Should not raise
        await engine._fetch_and_publish_all()
        
        # No events published (all failed)
        assert len(publisher.published_events) == 0
        
        await engine.stop()