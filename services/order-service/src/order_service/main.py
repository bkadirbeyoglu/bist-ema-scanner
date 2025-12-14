"""
Order Service Main Application.

FastAPI application with REST endpoints for order management.
"""

from contextlib import asynccontextmanager
from decimal import Decimal
import logging
import sys
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from order_service.config import get_settings
from order_service.domain.entities import Order, OrderSide, OrderType
from order_service.domain.saga_state import SagaState
from order_service.application.saga_orchestrator import get_orchestrator
from order_service.infrastructure.sqs_consumer import MarketDataConsumer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Global market data consumer
market_data_consumer: Optional[MarketDataConsumer] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global market_data_consumer
    
    settings = get_settings()
    logger.info(f"Starting {settings.service_name} v{settings.version}")
    
    # Start market data consumer
    market_data_consumer = MarketDataConsumer()
    try:
        await market_data_consumer.start()
    except Exception as e:
        logger.warning(f"Could not start market data consumer: {e}")
    
    # Register saga callbacks
    orchestrator = get_orchestrator()
    
    async def log_completion(order, execution):
        logger.info(f"Order {order.id} completed: status={order.status.value}")
    
    async def log_failure(order, execution):
        logger.warning(f"Order {order.id} failed: {execution.error_message}")
    
    orchestrator.on_complete(log_completion)
    orchestrator.on_failed(log_failure)
    
    yield  # Application runs
    
    # Shutdown
    if market_data_consumer:
        await market_data_consumer.stop()
    logger.info("Shutdown complete")


settings = get_settings()
app = FastAPI(
    title="Order Service",
    description="Order Management Service with Saga orchestration",
    version=settings.version,
    lifespan=lifespan
)


# Request/Response Models
class CreateOrderRequest(BaseModel):
    """Request to create a new order."""
    symbol: str = Field(..., min_length=1, max_length=10)
    side: str = Field(..., pattern="^(BUY|SELL)$")
    order_type: str = Field(default="MARKET", pattern="^(MARKET|LIMIT)$")
    quantity: str = Field(..., pattern=r"^\d+\.?\d*$")
    limit_price: Optional[str] = Field(default=None, pattern=r"^\d+\.?\d*$")
    account_id: str = Field(..., min_length=1)


class OrderResponse(BaseModel):
    """Order details response."""
    id: str
    symbol: str
    side: str
    order_type: str
    quantity: str
    status: str
    filled_quantity: str
    average_fill_price: Optional[str]
    estimated_value: Optional[str]
    rejection_reason: Optional[str]
    saga_id: Optional[str]


class SagaStatusResponse(BaseModel):
    """Saga execution status."""
    saga_id: str
    state: str
    completed_steps: list[str]
    failed_step: Optional[str]
    error_message: Optional[str]


# Health Endpoints
@app.get("/health", tags=["Health"])
async def health():
    """Basic health check."""
    return {"status": "healthy", "service": settings.service_name}


@app.get("/ready", tags=["Health"])
async def ready():
    """Readiness check."""
    return {
        "status": "ready",
        "saga_stats": get_orchestrator().stats()
    }


# Order Endpoints
@app.post(
    "/orders",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Orders"]
)
async def create_order(request: CreateOrderRequest):
    """
    Create a new order.
    
    Starts an Order Placement Saga that processes the order through
    validation, risk check, fund reservation, and execution.
    """
    logger.info(f"Creating order: {request.symbol} {request.side} {request.quantity}")
    
    order = Order(
        symbol=request.symbol.upper(),
        side=OrderSide(request.side),
        order_type=OrderType(request.order_type),
        quantity=Decimal(request.quantity),
        limit_price=Decimal(request.limit_price) if request.limit_price else None,
        account_id=request.account_id
    )
    
    orchestrator = get_orchestrator()
    
    try:
        execution = await orchestrator.start_order_saga(order)
        
        if execution.state != SagaState.COMPLETED:
            logger.warning(f"Order {order.id} ended in state {execution.state.name}")
        
    except Exception as e:
        logger.error(f"Failed to process order: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    
    return OrderResponse(
        id=order.id,
        symbol=order.symbol,
        side=order.side.value,
        order_type=order.order_type.value,
        quantity=str(order.quantity),
        status=order.status.value,
        filled_quantity=str(order.filled_quantity),
        average_fill_price=str(order.average_fill_price) if order.average_fill_price else None,
        estimated_value=str(order.estimated_value) if order.estimated_value else None,
        rejection_reason=order.rejection_reason,
        saga_id=order.saga_id
    )


@app.get("/orders/{order_id}", response_model=OrderResponse, tags=["Orders"])
async def get_order(order_id: str):
    """Get order details by ID."""
    order = await get_orchestrator().get_order(order_id)
    
    if not order:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found")
    
    return OrderResponse(
        id=order.id,
        symbol=order.symbol,
        side=order.side.value,
        order_type=order.order_type.value,
        quantity=str(order.quantity),
        status=order.status.value,
        filled_quantity=str(order.filled_quantity),
        average_fill_price=str(order.average_fill_price) if order.average_fill_price else None,
        estimated_value=str(order.estimated_value) if order.estimated_value else None,
        rejection_reason=order.rejection_reason,
        saga_id=order.saga_id
    )


@app.get("/orders/{order_id}/saga", response_model=SagaStatusResponse, tags=["Orders"])
async def get_saga_status(order_id: str):
    """Get saga execution status for an order."""
    execution = await get_orchestrator().get_saga_status(order_id)
    
    if not execution:
        raise HTTPException(status_code=404, detail=f"Saga not found for {order_id}")
    
    return SagaStatusResponse(
        saga_id=execution.saga_id,
        state=execution.state.name,
        completed_steps=execution.completed_steps,
        failed_step=execution.failed_step,
        error_message=execution.error_message
    )


# Market Data Cache Endpoints
@app.get("/prices", tags=["Market Data"])
async def get_cached_prices():
    """Get all cached market data prices."""
    if not market_data_consumer:
        return {"prices": {}, "status": "consumer_not_running"}
    
    prices = market_data_consumer.get_all_prices()
    
    return {
        "prices": {
            symbol: {"price": str(p.price), "timestamp": p.timestamp.isoformat()}
            for symbol, p in prices.items()
        },
        "count": len(prices)
    }


@app.get("/stats", tags=["Monitoring"])
async def get_stats():
    """Get service statistics."""
    return {
        "service": settings.service_name,
        "version": settings.version,
        "sagas": get_orchestrator().stats()
    }