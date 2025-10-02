# src/trading_system/infrastructure/market_data/alpha_vantage.py
"""
Alpha Vantage API client implementation.

API Documentation: https://www.alphavantage.co/documentation/
Free Tier: 500 calls/day, 5 calls/minute
"""

from typing import Dict, Any, Optional
from datetime import timedelta
from decimal import Decimal
import logging

from trading_system.infrastructure.market_data.base_client import AsyncMarketDataClient
from trading_system.domain.value_objects.price import Price

logger = logging.getLogger(__name__)


class AlphaVantageClient(AsyncMarketDataClient):
    """
    Async client for Alpha Vantage API.
    
    Inherits from AsyncMarketDataClient to get:
    - Rate limiting
    - Retry logic
    - Error handling
    - Connection pooling
    
    We just implement the API-specific parts.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize Alpha Vantage client.
        
        Alpha Vantage limits:
        - Free tier: 5 calls/minute, 500 calls/day
        - Premium: Higher limits
        
        We set conservative rate limits to stay within free tier.
        """
        super().__init__(
            base_url="https://www.alphavantage.co/query",
            api_key=api_key,
            rate_limit=5,  # 5 calls per minute (free tier)
            rate_window=timedelta(minutes=1),
            timeout=10,
            max_retries=3
        )
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """
        Get real-time quote for a symbol.
        
        API Endpoint: GLOBAL_QUOTE
        Response format:
        {
            "Global Quote": {
                "01. symbol": "AAPL",
                "05. price": "178.45",
                "06. volume": "52147300",
                "07. latest trading day": "2024-01-15",
                "08. previous close": "177.82",
                "09. change": "0.63",
                "10. change percent": "0.3544%"
            }
        }
        """
        params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol
        }
        
        # Make request using parent class method
        # (which handles rate limiting, retry, etc.)
        response = await self._make_request("", params)
        
        # Parse Alpha Vantage response format
        if "Global Quote" in response:
            quote = response["Global Quote"]
            
            # Return normalized format
            return {
                "symbol": quote.get("01. symbol"),
                "price": float(quote.get("05. price", 0)),
                "volume": int(quote.get("06. volume", 0)),
                "timestamp": quote.get("07. latest trading day"),
                "previous_close": float(quote.get("08. previous close", 0)),
                "change": float(quote.get("09. change", 0)),
                "change_percent": quote.get("10. change percent", "0%")
            }
        
        # Handle error responses
        if "Error Message" in response:
            raise ValueError(f"API Error: {response['Error Message']}")
        
        if "Note" in response:
            # Rate limit hit
            raise ValueError(f"Rate limit: {response['Note']}")
        
        # Unknown response format
        logger.warning(f"Unexpected response format: {response}")
        return {}
    
    async def get_price_object(self, symbol: str) -> Optional[Price]:
        """
        Get Price value object for a symbol.
        
        This integrates with our domain model from Day 1.
        Returns Price value object with Decimal precision.
        """
        quote = await self.get_quote(symbol)
        
        if quote and "price" in quote:
            # Convert to Decimal for financial precision
            # Always go through string to preserve precision
            return Price(Decimal(str(quote["price"])))
        
        return None