"""
Base async client for market data API's.
"""

import asyncio
import aiohttp      # We need to add this dependency
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging

logger = logging.getLogger(__name__)

@dataclass
class RateLimiter:
    """
    Rate limiter for API calls.

    Essential for respecting exchange API limits.
    """
    max_calls: int
    time_window: timedelta
    calls: List[datetime] = field(default_factory=list)

    async def acquire(self):
        """ Wait if necessary to respect rate limit. """
        now = datetime.now()

        # Remove old calls outside time window
        cutoff = now - self.time_window
        self.calls = [t for t in self.calls if t > cutoff]

        # if at limit, wait
        if len(self.calls) >= self.max_calls:
            oldest = self.calls[0]
            wait_time = (oldest + self.time_window - now).total_seconds()
            if wait_time > 0:
                logger.debug(f"Rate limit reached, waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
                # Recursive call to recheck
                await self.acquire()

        # Record this call
        self.calls.append(now)

class AsyncMarketDataClient:
    """
    Base async client for fetching market data

    Key Features:
    - Async HTTP requests with aiohttp
    - Automatic rate limiting
    - Connection pooling
    - Retry logic
    - Timeout handling
    """

    def __init__(
            self,
            base_url: str,
            api_key: Optional[str] = None,
            rate_limit: int = 60,
            rate_window: timedelta = timedelta(minutes=1),
            timeout: int = 10,
            max_retries: int = 3
    ):
        """ Initialize async market data client. """
        self.base_url = base_url
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

        # Rate limiter
        self.rate_limiter = RateLimiter(rate_limit, rate_window)

        # Session will be created in async context
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """ Async context manager entry - create session. """
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_Val, exc_tb):
        """ Async context manager exit - cleanup session. """
        if self._session:
            await self._session.close()


    async def _make_request(
            self,
            endpoint: str,
            params: Optional[Dict[str, Any]] = None,
            retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make async HTTP request with retry logic.

        This is the core of async I/O - while waiting for response, 
        other coroutines can run.
        """
        # Respect rate_limit
        await self.rate_limiter.acquire()

        url = f"{self.base_url}{endpoint}"

        # Add API key if provided
        if self.api_key:
            if params is None:
                params = {}
            params['apikey'] = self.api_key

        try:
            async with self._session.get(url, params=params) as response:
                response.raise_for_status()
                return await response.json()
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching {url}")
            if retry_count < self.max_retries:
                await asyncio.sleep(2 ** retry_count)   # Exponential backoff
                return await self._make_request(endpoint, params, retry_count = 1)
            raise

        except aiohttp.ClientError as e:
            logger.error(f"Error fetching {url}: {e}")
            if retry_count < self.max_retries:
                await asyncio.sleep(2 ** retry_count) 
                return await self._make_request(endpoint, params, retry_count = 1)
            raise
    
    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """ Get current quote for symbol. """
        return await self._make_request(f"/quote/{symbol}")
    
    async def get_quotes(self, symbols: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Get quotes for multiple symbols cpncurretly.

        This is where async shines - all requests happen in parallel!
        """
        tasks = [self.get_quote(symbol) for symbol in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        quotes = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(f"Failed to get quote for {symbol}: {result}")
                quotes[symbol] = None
            else:
                quotes[symbol] = result
        
        return quotes