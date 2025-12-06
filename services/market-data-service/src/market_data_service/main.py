"""
Market Data Service - FastAPI Application.

RUN: uvicorn market_data_service.main:app --host 0.0.0.0 --port 8001
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
import structlog

from market_data_service.config import Settings, get_settings
from market_data_service.application.price_engine import PriceEngine
from market_data_service.infrastructure.data_sources.mock import MockDataSource
from market_data_service.infrastructure.publishers.sqs_publisher import SQSPublisher

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Global price engine (initialized in lifespan)
price_engine: PriceEngine | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    PYTHON FEATURE: @asynccontextmanager
    - Code BEFORE yield runs at STARTUP
    - Code AFTER yield runs at SHUTDOWN
    - Replaces deprecated @app.on_event("startup") / @app.on_event("shutdown")
    
    See DEEP DIVE at end of file for full explanation.
    """
    global price_engine
    
    settings = get_settings()
    logger.info(
        "Starting Market Data Service",
        version=settings.service_version,
        environment=settings.environment
    )
    
    # ─────────────────────────────────────────────────────────────────────────
    # STARTUP: Create and connect all components
    # ─────────────────────────────────────────────────────────────────────────
    
    # Create data sources based on config
    data_sources = []
    if settings.data_source == "mock":
        data_sources.append(MockDataSource())
    # TODO: Add AlphaVantageSource, YahooSource when needed
    
    # Create SQS publisher
    publisher = SQSPublisher(settings)
    
    # Create and start price engine
    price_engine = PriceEngine(
        settings=settings,
        data_sources=data_sources,
        publisher=publisher
    )
    await price_engine.start()
    
    logger.info("Market Data Service started successfully")
    
    # ─────────────────────────────────────────────────────────────────────────
    # RUNNING: App handles requests here (yield pauses until shutdown)
    # ─────────────────────────────────────────────────────────────────────────
    
    yield
    
    # ─────────────────────────────────────────────────────────────────────────
    # SHUTDOWN: Clean up gracefully
    # ─────────────────────────────────────────────────────────────────────────
    
    logger.info("Shutting down Market Data Service")
    
    if price_engine:
        await price_engine.stop()
    
    logger.info("Market Data Service stopped")


# Create FastAPI application with lifespan
app = FastAPI(
    title="Market Data Service",
    description="Real-time market price feeds for the trading platform",
    version="1.0.0",
    lifespan=lifespan  # Pass lifespan context manager here
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# HEALTH ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check(settings: Settings = Depends(get_settings)):
    """
    Basic health check endpoint.
    
    Used by:
    - Docker HEALTHCHECK
    - Kubernetes liveness probe
    - Load balancer health checks
    """
    return {
        "status": "healthy",
        "service": settings.service_name,
        "version": settings.service_version
    }


@app.get("/ready")
async def readiness_check():
    """
    Readiness check - is the service ready to receive traffic?
    
    Checks:
    - Price engine is running
    - Has recent price data
    
    Used by:
    - Kubernetes readiness probe
    - Load balancer routing decisions
    """
    if price_engine is None or not price_engine.is_running:
        raise HTTPException(
            status_code=503,
            detail="Service not ready - price engine not running"
        )
    
    return {
        "ready": True,
        "engine_running": price_engine.is_running,
        "tracked_symbols": price_engine.tracked_symbols
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PRICE ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.get("/prices")
async def get_all_prices():
    """
    Get all current prices.
    
    Returns:
        Dictionary of symbol -> price data
    """
    if price_engine is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    prices = price_engine.get_all_prices()
    
    return {
        symbol: {
            "symbol": quote.symbol,
            "price": str(quote.last_price),
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "volume": quote.volume,
            "timestamp": quote.timestamp.isoformat(),
            "source": quote.source.value
        }
        for symbol, quote in prices.items()
    }


@app.get("/prices/{symbol}")
async def get_price(symbol: str):
    """
    Get current price for a specific symbol.
    
    Args:
        symbol: Stock symbol (e.g., AAPL)
        
    Returns:
        Current price data
        
    Raises:
        404: Symbol not found
    """
    if price_engine is None:
        raise HTTPException(status_code=503, detail="Service not ready")
    
    quote = price_engine.get_latest_price(symbol.upper())
    
    if quote is None:
        raise HTTPException(
            status_code=404,
            detail=f"Price not found for symbol: {symbol}"
        )
    
    return {
        "symbol": quote.symbol,
        "price": str(quote.last_price),
        "bid": str(quote.bid),
        "ask": str(quote.ask),
        "spread": str(quote.spread),
        "volume": quote.volume,
        "timestamp": quote.timestamp.isoformat(),
        "source": quote.source.value
    }


# ═══════════════════════════════════════════════════════════════════════════════
# WEBSOCKET ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════════

@app.websocket("/ws/prices")
async def price_stream(websocket: WebSocket):
    """
    WebSocket endpoint for real-time price streaming.
    
    Streams all price updates to connected clients.
    
    PROTOCOL:
    1. Client connects
    2. Server sends all current prices
    3. Server sends updates as they occur
    4. Client disconnects when done
    """
    await websocket.accept()
    
    logger.info("WebSocket client connected", endpoint="/ws/prices")
    
    try:
        while True:
            if price_engine is None:
                await websocket.send_json({"error": "Service not ready"})
                await asyncio.sleep(1)
                continue
            
            # Send all prices
            prices = price_engine.get_all_prices()
            
            await websocket.send_json({
                "type": "price_update",
                "data": {
                    symbol: {
                        "symbol": quote.symbol,
                        "price": str(quote.last_price),
                        "bid": str(quote.bid),
                        "ask": str(quote.ask),
                        "timestamp": quote.timestamp.isoformat()
                    }
                    for symbol, quote in prices.items()
                }
            })
            
            # Wait before next update
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected", endpoint="/ws/prices")


@app.websocket("/ws/prices/{symbol}")
async def symbol_price_stream(websocket: WebSocket, symbol: str):
    """
    WebSocket endpoint for single symbol price streaming.
    
    Args:
        symbol: Stock symbol to stream
    """
    await websocket.accept()
    symbol = symbol.upper()
    
    logger.info(
        "WebSocket client connected",
        endpoint=f"/ws/prices/{symbol}",
        symbol=symbol
    )
    
    try:
        while True:
            if price_engine is None:
                await websocket.send_json({"error": "Service not ready"})
                await asyncio.sleep(1)
                continue
            
            quote = price_engine.get_latest_price(symbol)
            
            if quote:
                await websocket.send_json({
                    "type": "price_update",
                    "symbol": quote.symbol,
                    "price": str(quote.last_price),
                    "bid": str(quote.bid),
                    "ask": str(quote.ask),
                    "spread": str(quote.spread),
                    "timestamp": quote.timestamp.isoformat()
                })
            
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected",
            endpoint=f"/ws/prices/{symbol}",
            symbol=symbol
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    
    uvicorn.run(
        "market_data_service.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.is_development()
    )