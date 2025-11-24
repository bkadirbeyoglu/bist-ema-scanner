"""
FastAPI Application Entry Point.

This is the main FastAPI application that exposes our trading system
via REST APIs. It integrates with the CQRS read models from Day 7 to
provide lightning-fast query responses.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# Import routers
from trading_system.api.routers import strategies, backtests, auth

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown events."""
    # Startup
    logger.info("🚀 Trading API starting up...")
    logger.info("📊 Integrating with Day 7 CQRS read models")
    logger.info("✅ API ready to serve requests")
    
    yield
    
    # Shutdown
    logger.info("👋 Trading API shutting down...")
    logger.info("✅ Cleanup complete")


app = FastAPI(
    title="Algorithmic Trading System API",
    description="Production-grade REST API for trading strategies and backtests",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Change in production!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(
    auth.router,
    prefix="/api/v1/auth",
    tags=["authentication"]
)
app.include_router(
    strategies.router,
    prefix="/api/v1/strategies",
    tags=["strategies"]
)
app.include_router(
    backtests.router,
    prefix="/api/v1/backtests",
    tags=["backtests"]
)

@app.get("/")
async def root():
    """Root endpoint - API information."""
    return {
        "name": "Algorithmic Trading System API",
        "version": "1.0.0",
        "docs": "/api/docs",
        "status": "operational"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {
        "status": "healthy",
        "service": "trading-api"
    }