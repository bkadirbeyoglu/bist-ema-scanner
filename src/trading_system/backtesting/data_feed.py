"""Custom Backtrader data feed for trading system integration.

ARCHITECTURE: Adapter Pattern
This data feed serves as an adapter between:
- Backtrader's synchronous data model
- Our event-driven asynchronous architecture (when event bus is provided)

Note: Event publishing is optional. The data feed works with or without
an event bus, making it flexible for different use cases.
"""
import asyncio
from datetime import datetime

import backtrader as bt


class TradingSystemDataFeed(bt.feeds.PandasData):  # pylint: disable=no-member
    """Custom data feed for integration with trading system.
    
    ARCHITECTURE PATTERN: Adapter
    Adapts Backtrader's data feed interface to work with our system.
    
    PYTHON INHERITANCE: Extends Backtrader's PandasData
    We're adding optional event publishing on top of standard data feed.
    
    IMPORTANT - Pylint False Positives:
    You will see Pylint warnings like:
    - "Instance of 'TradingSystemDataFeed' has no 'close' member"
    - "Instance of 'TradingSystemDataFeed' has no 'open' member"
    
    These are FALSE POSITIVES. Backtrader uses metaclasses to dynamically
    create these attributes (open, high, low, close, volume) at runtime.
    Static analysis tools like Pylint cannot detect metaclass-created
    attributes. The code works correctly despite these warnings.
    
    The same applies to self.params.event_bus - Backtrader's metaclass
    converts the params tuple into attributes, which Pylint doesn't recognize.
    
    LINTER SUPPRESSION:
    The `# pylint: disable=no-member` comment above the class definition
    suppresses these false positive warnings for the entire class.
    """
    
    # BACKTRADER PARAMS: Configure the data feed
    # These can be overridden when creating the feed
    # 
    # PYTHON NOTE: This is a tuple, but Backtrader's metaclass converts it
    # to instance attributes. So self.params.event_bus works at runtime
    # even though Pylint may show warnings.
    params = (
        ('event_bus', None),  # Optional: async event bus for publishing
        ('symbol', 'UNKNOWN'),  # Trading symbol
    )
    
    def __init__(self):
        """Initialize data feed with event tracking."""
        super().__init__()
        self._bar_counter = 0
    
    def _load(self):
        """Load next bar.
        
        BACKTRADER HOOK: Called for each bar
        We override this to add bar counting and optional event publishing.
        
        Returns:
            bool: True if bar loaded successfully
        """
        # Call parent's _load to get the next bar
        result = super()._load()
        
        if result:
            self._bar_counter += 1
            # Note: Event publishing has been removed as PriceUpdatedEvent
            # is not defined in the current architecture. If needed in the
            # future, it should be added to shared_kernel.events first.
        
        return result


class BacktestDataLoader:
    """Utility to load historical data for backtesting.
    
    SEPARATION OF CONCERNS:
    Data loading is separate from data feeding.
    - BacktestDataLoader: Gets data from external source
    - TradingSystemDataFeed: Feeds data to Backtrader
    """
    
    @staticmethod
    def load_yahoo_finance(
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> 'pd.DataFrame':
        """Load historical data from Yahoo Finance.
        
        EXTERNAL API: Uses yfinance library
        Free, no API key required, good for learning!
        
        Args:
            symbol: Trading symbol (e.g., 'AAPL', 'GOOG')
            start_date: Start of data range
            end_date: End of data range
        
        Returns:
            DataFrame with OHLCV data
        
        Raises:
            ValueError: If data cannot be loaded
        """
        import yfinance as yf
        import pandas as pd
        
        print(f"Loading {symbol} data from {start_date.date()} to {end_date.date()}...")
        
        try:
            df = yf.download(
                symbol,
                start=start_date,
                end=end_date,
                progress=False,
                auto_adjust=False  # Don't auto-adjust prices - we want raw data
            )
            
            # FIX: yfinance now returns MultiIndex columns - flatten them
            # Backtrader expects simple column names like 'Open', 'High', etc.
            # PYTHON: isinstance() checks if object is instance of a class
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.droplevel(1)
            
            if df.empty:
                raise ValueError(f"No data returned for {symbol}")
            
            print(f"  Loaded {len(df)} bars")
            return df
            
        except Exception as e:
            raise ValueError(f"Failed to load data for {symbol}: {e}")