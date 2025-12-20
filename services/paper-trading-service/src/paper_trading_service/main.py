"""
FastAPI application for Paper Trading Service.

Includes:
- REST API endpoints
- WebSocket streaming
- SQS consumer for strategy signals (optional)
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from paper_trading_service.api.router import get_session_manager
from paper_trading_service.api.router import reset_session_manager
from paper_trading_service.api.router import router as api_router
from paper_trading_service.api.websocket import ws_router
from paper_trading_service.application.signal_handler import SignalHandler
from paper_trading_service.config import Settings
from paper_trading_service.infrastructure.sqs_consumer import SQSConsumer


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


# Background task for SQS consumer
_consumer_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Starts/stops background services like the SQS consumer.
    """
    global _consumer_task
    settings = Settings()
    
    # === STARTUP ===
    logger.info("🚀 Paper Trading Service starting...")
    
    # Start SQS consumer if enabled
    if settings.sqs_enabled:
        try:
            handler = SignalHandler(get_session_manager())
            consumer = SQSConsumer(handler, settings)
            _consumer_task = asyncio.create_task(consumer.start())
            logger.info("📡 SQS Consumer started")
        except Exception as e:
            logger.warning("⚠️  SQS Consumer disabled: %s", e)
    else:
        logger.info("📡 SQS Consumer disabled by configuration")
    
    yield  # Application runs here
    
    # === SHUTDOWN ===
    logger.info("🛑 Paper Trading Service shutting down...")
    
    # Stop SQS consumer
    if _consumer_task is not None:
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
        logger.info("📡 SQS Consumer stopped")
    
    # Reset session manager
    reset_session_manager()


def create_app(settings: Settings | None = None) -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Args:
        settings: Optional settings override (useful for testing)
    
    Returns:
        Configured FastAPI application
    """
    if settings is None:
        settings = Settings()
    
    app = FastAPI(
        title="Paper Trading Service",
        description=(
            "A virtual trading service for testing strategies "
            "without risking real money.\n\n"
            "## Features\n"
            "- Create and manage paper trading sessions\n"
            "- Execute simulated trades with realistic slippage\n"
            "- Real-time portfolio updates via WebSocket\n"
            "- Automatic signal processing from strategies"
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(api_router)
    app.include_router(ws_router)
    
    # Root endpoint
    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {
            "service": "paper-trading-service",
            "version": "1.0.0",
            "docs": "/docs",
            "health": "/api/v1/health",
        }
    
    return app


# Create default application instance
app = create_app()


if __name__ == "__main__":
    import uvicorn
    
    settings = Settings()
    uvicorn.run(
        "paper_trading_service.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )