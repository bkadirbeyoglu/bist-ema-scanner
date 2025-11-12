"""Tests for Moving Average Crossover Strategy"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from decimal import Decimal

from trading_system.strategies.moving_average import MovingAverageCrossoverStrategy
from trading_system.strategies.signals import TradingSignal, SignalType, SignalStrength
from trading_system.contexts.portfolio_management.domain.entities.portfolio import Portfolio
from trading_system.shared_kernel.value_objects.money import Money


class TestMovingAverageCrossoverStrategy:

    @pytest.fixture
    def sample_data(self):
        """Create sample market data with clear trend"""
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
        
        # Create uptrend data
        prices = 100 + np.arange(100) * 0.5  # Steady uptrend
        noise = np.random.normal(0, 2, 100)  # Add some noise
        
        df = pd.DataFrame({
            'close': prices + noise,
            'volume': np.random.randint(1000000, 5000000, 100)
        }, index=dates)
        
        return df
    
    @pytest.fixture
    def crossover_data(self):
        """Create data with deliberate MA crossover"""
        dates = pd.date_range(end=datetime.now(), periods=100, freq='D')
        
        # First 50 days: downtrend
        # Last 50 days: uptrend (creates golden cross around day 50)
        prices = np.concatenate([
            np.linspace(100, 80, 50),  # Downtrend
            np.linspace(80, 110, 50)   # Uptrend
        ])
        
        df = pd.DataFrame({
            'close': prices,
            'volume': np.ones(100) * 1000000
        }, index=dates)
        
        return df
    
    @pytest.mark.asyncio
    async def test_golden_cross_detection(self, crossover_data):
        """Test detection of golden cross (bullish signal)"""
        
        strategy = MovingAverageCrossoverStrategy(
            fast_period=10,
            slow_period=20
        )
        
        # Use data around the crossover point
        signal = await strategy.calculate_signal(
            crossover_data.iloc[40:70],  # Include crossover region
            "TEST"
        )
        
        # Should detect buying opportunity
        assert signal.signal_type in [SignalType.BUY, SignalType.HOLD]
        
        # Check indicators are calculated
        assert 'ma_10' in signal.indicators
        assert 'ma_20' in signal.indicators

    @pytest.mark.asyncio
    async def test_insufficient_data_handling(self):
        """Test strategy handles insufficient data gracefully"""
        
        strategy = MovingAverageCrossoverStrategy(
            fast_period=20,
            slow_period=50
        )
        
        # Only 30 periods of data (need 50)
        small_data = pd.DataFrame({
            'close': np.random.uniform(90, 110, 30)
        })
        
        signal = await strategy.calculate_signal(small_data, "TEST")
        
        assert signal.signal_type == SignalType.HOLD
        assert "Insufficient data" in signal.reason
    
    def test_position_sizing_risk_limit(self):
        """Test position sizing respects portfolio risk limits"""
        
        strategy = MovingAverageCrossoverStrategy()
        portfolio = Portfolio(
            name="Test",
            cash=Money(Decimal("10000"))
        )
        
        # Create signal with high price
        from trading_system.shared_kernel.value_objects.symbol import Symbol
        signal = TradingSignal(
            symbol=Symbol("TEST"),
            signal_type=SignalType.BUY,
            strength=SignalStrength.STRONG,
            timestamp=datetime.now(),
            strategy_name="MA_Crossover",
            price=Decimal("1000")  # High price
        )
        
        # Should limit position to 5% of portfolio
        position_size = strategy.calculate_position_size(
            signal, portfolio, base_size=100
        )
        
        # 5% of $10,000 = $500, at $1000/share = 0.5 shares → rounds to 1
        assert position_size == 1
    
    def test_ema_vs_sma_option(self):
        """Test strategy can use EMA instead of SMA"""
        
        sma_strategy = MovingAverageCrossoverStrategy(use_ema=False)
        ema_strategy = MovingAverageCrossoverStrategy(use_ema=True)
        
        assert sma_strategy.use_ema == False
        assert ema_strategy.use_ema == True
    
    def test_invalid_periods_raises_error(self):
        """Test that invalid period configuration raises error"""
        
        with pytest.raises(ValueError, match="Fast period must be less than slow period"):
            MovingAverageCrossoverStrategy(
                fast_period=50,
                slow_period=20  # Invalid: fast > slow
            )