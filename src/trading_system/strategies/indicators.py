"""Technical indicator calculations using ta library"""

import pandas as pd
import numpy as np
from ta.trend import SMAIndicator, EMAIndicator, MACD
from ta.momentum import RSIIndicator
from ta.volatility import BollingerBands
from ta.volume import OnBalanceVolumeIndicator, VolumeWeightedAveragePrice
from typing import Optional, Dict, Any
from decimal import Decimal


class TechnicalIndicators:
    """
    Wrapper for technical indicator calculations.
    
    Uses 'ta' library for efficient vectorized calculations.
    All methods are pure functions (no side effects).
    """

    @staticmethod
    def add_sma(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
        """
        Add Simple Moving Average.
        
        SMA = (P1 + P2 + ... + Pn) / n
        """
        indicator = SMAIndicator(close=df[column], window=period)
        return indicator.sma_indicator()
    
    @staticmethod
    def add_ema(df: pd.DataFrame, period: int = 20, column: str = "close") -> pd.Series:
        """
        Add Exponential Moving Average.
        
        EMA gives more weight to recent prices.
        """
        indicator = EMAIndicator(close=df[column], window=period)
        return indicator.ema_indicator()
    
    @staticmethod
    def add_rsi(df: pd.DataFrame, period: int = 14, column: str = "close") -> pd.Series:
        """
        Add Relative Strength Index.
        
        RSI = 100 - (100 / (1 + RS))
        RS = Average Gain / Average Loss
        
        Values:
        - > 70: Overbought (potential sell)
        - < 30: Oversold (potential buy)
        - 30-70: Neutral
        """
        indicator = RSIIndicator(close=df[column], window=period)
        return indicator.rsi()
    
    @staticmethod
    def add_macd(df: pd.DataFrame, 
                 fast: int = 12, 
                 slow: int = 26, 
                 signal: int = 9,
                 column: str = "close") -> pd.DataFrame:
        """
        Add MACD (Moving Average Convergence Divergence).
        
        MACD Line = 12-day EMA - 26-day EMA
        Signal Line = 9-day EMA of MACD
        Histogram = MACD - Signal
        
        Signals:
        - MACD crosses above Signal: Bullish
        - MACD crosses below Signal: Bearish
        """
        indicator = MACD(close=df[column], 
                        window_slow=slow,
                        window_fast=fast, 
                        window_sign=signal)
        
        return pd.DataFrame({
            'MACD': indicator.macd(),
            'Signal': indicator.macd_signal(),
            'Histogram': indicator.macd_diff()
        })
    
    @staticmethod
    def add_bollinger_bands(df: pd.DataFrame, 
                           period: int = 20,
                           std_dev: float = 2.0,
                           column: str = "close") -> pd.DataFrame:
        """
        Add Bollinger Bands.
        
        Middle Band = SMA(period)
        Upper Band = Middle + (std_dev * σ)
        Lower Band = Middle - (std_dev * σ)
        
        Signals:
        - Price touches lower band: Potential buy
        - Price touches upper band: Potential sell
        """
        indicator = BollingerBands(close=df[column], 
                                  window=period, 
                                  window_dev=std_dev)
        
        return pd.DataFrame({
            'BB_Upper': indicator.bollinger_hband(),
            'BB_Middle': indicator.bollinger_mavg(),
            'BB_Lower': indicator.bollinger_lband(),
            'BB_Width': indicator.bollinger_wband(),
            'BB_Percent': indicator.bollinger_pband()
        })
    
    @staticmethod
    def add_volume_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Add volume-based indicators.
        
        - OBV: On-Balance Volume (volume trend)
        - VWAP: Volume Weighted Average Price
        """
        result = pd.DataFrame(index=df.index)
        
        # On-Balance Volume
        if 'volume' in df.columns:
            obv = OnBalanceVolumeIndicator(close=df['close'], volume=df['volume'])
            result['obv'] = obv.on_balance_volume()
        
        # VWAP (if high/low/close/volume available)
        if all(col in df.columns for col in ['high', 'low', 'close', 'volume']):
            vwap = VolumeWeightedAveragePrice(
                high=df['high'],
                low=df['low'], 
                close=df['close'],
                volume=df['volume']
            )
            result['vwap'] = vwap.volume_weighted_average_price()
        
        return result
    
    @staticmethod
    def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate all major indicators at once.
        
        Returns new DataFrame with original data plus indicators.
        """
        # Create copy to avoid modifying original
        result = df.copy()
        
        # Trend indicators
        result['sma_20'] = TechnicalIndicators.add_sma(df, 20)
        result['sma_50'] = TechnicalIndicators.add_sma(df, 50)
        result['ema_12'] = TechnicalIndicators.add_ema(df, 12)
        result['ema_26'] = TechnicalIndicators.add_ema(df, 26)
        
        # Momentum indicators
        result['rsi'] = TechnicalIndicators.add_rsi(df)
        
        # MACD
        macd_df = TechnicalIndicators.add_macd(df)
        for col in macd_df.columns:
            result[col] = macd_df[col]
        
        # Bollinger Bands
        bb_df = TechnicalIndicators.add_bollinger_bands(df)
        for col in bb_df.columns:
            result[col] = bb_df[col]
        
        # Volume indicators (if volume data exists)
        if 'volume' in df.columns:
            vol_df = TechnicalIndicators.add_volume_indicators(df)
            for col in vol_df.columns:
                result[col] = vol_df[col]
        
        return result