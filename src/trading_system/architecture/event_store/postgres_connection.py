"""
PostgreSQL Connection Pool Manager.

Manages database connections efficiently using asyncpg connection pooling.

PYTHON FEATURES:
- async with: Async context manager
- asyncpg.Pool: Connection pooling
- __aenter__ / __aexit__: Context manager protocol
"""

import logging
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


class PostgresConnectionPool:
    """
    Manages PostgreSQL connection pool.
    
    PATTERN: Resource Management
    Uses connection pooling to efficiently manage database connections.
    Similar to connection pools in Java/C# (e.g., HikariCP, ADO.NET).
    
    Why pooling?
    - Creating connections is expensive (network handshake, auth)
    - Reuse connections across requests
    - Limit total concurrent connections to database
    """
    
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "trading_db",    # â† Single database with schemas
        user: str = "trading",           # â† Your existing user
        password: str = "password",      # â† Your existing password
        min_size: int = 10,
        max_size: int = 20,
        search_path: str = "events,public",  # â† Schema search path
    ):
        """
        Initialize connection pool configuration.
        
        IMPORTANT: We use a single database (trading_db) with multiple schemas.
        The search_path parameter sets which schemas to search for unqualified table names.
        
        Args:
            host: PostgreSQL host (localhost or postgres for Docker)
            port: PostgreSQL port (default 5432)
            database: Database name (trading_db - same as your main DB)
            user: Database user (trading - same as your main DB)
            password: Database password (password - same as your main DB)
            min_size: Minimum connections to maintain
            max_size: Maximum connections allowed
            search_path: Schema search order (events,public)
        
        Schema Architecture:
            trading_db/
            â”œâ”€â”€ Schema: orders       (existing)
            â”œâ”€â”€ Schema: positions    (existing)
            â”œâ”€â”€ Schema: market_data  (existing)
            â”œâ”€â”€ Schema: risk         (existing)
            â”œâ”€â”€ Schema: events       (NEW - event store)
            â””â”€â”€ Schema: public       (health_check, etc.)
        """
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.min_size = min_size
        self.max_size = max_size
        self.search_path = search_path  # Schema search path
        
        self._pool: Optional[asyncpg.Pool] = None
    
    async def connect(self) -> None:
        """
        Create connection pool.
        
        PYTHON FEATURE: async/await
        This is an async function - it returns a coroutine that must be awaited.
        
        IMPORTANT: We set the search_path to look in 'events' schema first.
        This means queries like "SELECT * FROM events" will find "events.events".
        """
        try:
            self._pool = await asyncpg.create_pool(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
                min_size=self.min_size,
                max_size=self.max_size,
                server_settings={
                    'search_path': self.search_path  # Set schema search path
                }
            )
            logger.info(
                f"Connected to PostgreSQL pool "
                f"({self.min_size}-{self.max_size} connections)"
            )
        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}", exc_info=True)
            raise
    
    async def disconnect(self) -> None:
        """Close connection pool."""
        if self._pool:
            await self._pool.close()
            logger.info("Disconnected from PostgreSQL pool")
    
    @property
    def pool(self) -> asyncpg.Pool:
        """
        Get connection pool.
        
        PYTHON FEATURE: @property
        Makes a method look like an attribute:
            pool = manager.pool  # Looks like attribute
            # Instead of: pool = manager.get_pool()
        """
        if not self._pool:
            raise RuntimeError("Connection pool not initialized. Call connect() first.")
        return self._pool
    
    # ========================================================================
    # CONTEXT MANAGER PROTOCOL
    # ========================================================================
    
    async def __aenter__(self):
        """
        Async context manager entry.
        
        PYTHON FEATURE: async with
        Allows using this class with 'async with' statement:
        
            async with PostgresConnectionPool() as pool:
                # pool is connected
                await pool.fetch(...)
            # pool is automatically disconnected
        
        Similar to:
        - Java: try-with-resources
        - C#: using statement
        """
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.disconnect()
        return False  # Don't suppress exceptions
    
    # ========================================================================
    # CONVENIENCE METHODS
    # ========================================================================
    
    async def fetch(self, query: str, *args):
        """Execute query and fetch all results."""
        async with self.pool.acquire() as connection:
            return await connection.fetch(query, *args)
    
    async def fetchrow(self, query: str, *args):
        """Execute query and fetch one result."""
        async with self.pool.acquire() as connection:
            return await connection.fetchrow(query, *args)
    
    async def fetchval(self, query: str, *args):
        """Execute query and fetch single value."""
        async with self.pool.acquire() as connection:
            return await connection.fetchval(query, *args)
    
    async def execute(self, query: str, *args):
        """Execute query without returning results."""
        async with self.pool.acquire() as connection:
            return await connection.execute(query, *args)