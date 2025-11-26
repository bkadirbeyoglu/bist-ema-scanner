from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

# REST routers (Session 1)
from trading_system.api.routers import strategies, backtests, auth

# WebSocket router (Session 2)
from trading_system.api.websocket.router import router as websocket_router

# SQS Bridge (Session 2)
from trading_system.api.websocket.sqs_bridge import sqs_bridge

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# @asynccontextmanager: Makes this an async context manager (async with ...)
# FastAPI calls this when the app starts and stops
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager.
    
    Flow:
    1. FastAPI starts
    2. Everything BEFORE 'yield' runs (startup)
    3. 'yield' - application serves requests
    4. FastAPI receives shutdown signal (Ctrl+C, etc.)
    5. Everything AFTER 'yield' runs (shutdown)
    """
    # ==================== STARTUP ====================
    # This code runs ONCE when the server starts
    logger.info("🚀 Trading API starting up...")
    logger.info("📊 REST: /api/v1/strategies, /api/v1/backtests")
    logger.info("🔌 WebSocket: /ws/signals, /ws/market-data")
    
    # Start SQS bridge background task
    # In demo mode: just logs, no SQS polling
    # In production: starts polling SQS queue
    await sqs_bridge.start()
    logger.info("✅ SQS-WebSocket bridge started")
    
    # ==================== YIELD ====================
    # Application runs and serves requests here
    # This "pauses" until shutdown signal received
    yield
    
    # ==================== SHUTDOWN ====================
    # This code runs when server is stopping (Ctrl+C, etc.)
    # Important: Clean up background tasks to avoid hanging
    await sqs_bridge.stop()
    logger.info("👋 Trading API shut down")


app = FastAPI(
    title="Algorithmic Trading System API",
    description="REST and WebSocket APIs for trading",
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# REST routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(strategies.router, prefix="/api/v1/strategies", tags=["strategies"])
app.include_router(backtests.router, prefix="/api/v1/backtests", tags=["backtests"])

# WebSocket router
app.include_router(websocket_router)


@app.get("/")
async def root():
    return {
        "name": "Trading System API",
        "version": "1.0.0",
        "rest": "/api/v1",
        "websocket": "/ws",
        "docs": "/api/docs"
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "trading-api"}