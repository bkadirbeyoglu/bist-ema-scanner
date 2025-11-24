"""
Strategy Performance API Router.

Exposes trading strategy metrics via REST endpoints.
Integrates with StrategyQueryService from Day 7 Session 2.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
import logging

# Day 7 imports - CQRS query service and read models
from trading_system.queries.strategy_queries import StrategyQueryService
from trading_system.read_models.schemas import StrategyPerformance
from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool

# Day 8 imports - API response models
from trading_system.api.schemas.responses import (
    StrategyPerformanceResponse,
    StrategyListResponse,
    SignalResponse,
    ErrorResponse
)

logger = logging.getLogger(__name__)

# Create router
# FASTAPI PATTERN: Router groups related endpoints
router = APIRouter()

# Dependency injection for database connection
# DESIGN PATTERN: Dependency Injection
# - Provides database connection to endpoints
# - Enables testing with mock connections
# - Manages connection lifecycle automatically
async def get_db_pool() -> PostgresConnectionPool:
    """
    Get PostgreSQL connection pool.
    
    PRODUCTION NOTE: In a real application, this would be initialized
    once at startup and reused. For this course, we create it on demand.
    
    FASTAPI FEATURE: Dependencies can be async functions
    """
    # TODO: Initialize once at startup and store in app.state
    pool = PostgresConnectionPool(
        host="localhost",  # When running in Docker: "postgres"
        port=5432,
        database="trading_db",
        user="trading",
        password="password"
    )
    await pool.connect()
    return pool


# Dependency for StrategyQueryService
async def get_query_service(
    pool: PostgresConnectionPool = Depends(get_db_pool)
) -> StrategyQueryService:
    """
    Get Strategy Query Service.
    
    DEPENDENCY INJECTION: FastAPI automatically:
    1. Calls get_db_pool() to get connection
    2. Passes connection to this function
    3. Returns StrategyQueryService to endpoint
    
    This enables clean, testable code!
    """
    return StrategyQueryService(pool)


@router.get(
    "/",
    response_model=StrategyListResponse,
    summary="List all strategies",
    description="Get a list of all trading strategies with performance metrics",
    responses={
        200: {"description": "List of strategies"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def list_strategies(
    limit: int = Query(10, ge=1, le=100, description="Maximum number of strategies to return"),
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    List all trading strategies with performance metrics.
    
    **Performance:** Sub-10ms response time (CQRS read model!)
    
    **Query Parameters:**
    - `limit`: Maximum strategies to return (default: 100, max: 1000)
    - `offset`: Pagination offset (default: 0)
    
    **Returns:** List of strategies with performance metrics
    
    **Example:** GET /api/v1/strategies?limit=10&offset=0
    """
    try:
        # Query Day 7 CQRS read models
        # This hits pre-calculated projections - super fast!
        strategies = await query_service.get_top_strategies(limit=limit)
        
        # Convert read models to API responses
        response_list = [
            StrategyPerformanceResponse.from_read_model(strategy)
            for strategy in strategies
        ]
        
        return StrategyListResponse(
            strategies=response_list,
            total=len(response_list)
        )
    
    except Exception as e:
        logger.error(f"Error listing strategies: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve strategies"
        )


@router.get(
    "/{strategy_id}/performance",
    response_model=StrategyPerformanceResponse,
    summary="Get strategy performance",
    description="Get aggregated performance metrics for a specific strategy",
    responses={
        200: {"description": "Strategy performance metrics"},
        404: {"model": ErrorResponse, "description": "Strategy not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_strategy_performance(
    strategy_id: str,
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    Get performance metrics for a specific strategy.
    
    **Performance:** Sub-10ms response (CQRS optimization!)
    
    **Path Parameters:**
    - `strategy_id`: Unique strategy identifier (e.g., "strategy-ma-001")
    
    **Returns:** Complete performance metrics including:
    - Total signals generated
    - Win rate and profit metrics
    - Sharpe ratio
    - Last signal timestamp
    
    **Example:** GET /api/v1/strategies/strategy-ma-001/performance
    
    **Why So Fast?**
    Day 7's CQRS projections pre-calculate all metrics!
    No expensive computation at query time.
    """
    try:
        # Query CQRS read model (Day 7 Session 2)
        performance = await query_service.get_strategy_performance(strategy_id)
        
        if not performance:
            raise HTTPException(
                status_code=404,
                detail=f"Strategy '{strategy_id}' not found"
            )
        
        # Convert to API response
        return StrategyPerformanceResponse.from_read_model(performance)
    
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        logger.error(f"Error getting strategy performance: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve strategy performance"
        )


@router.get(
    "/{strategy_id}/signals",
    response_model=List[SignalResponse],
    summary="Get strategy signals",
    description="Get historical signals generated by a strategy",
    responses={
        200: {"description": "List of signals"},
        404: {"model": ErrorResponse, "description": "Strategy not found"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_strategy_signals(
    strategy_id: str,
    limit: int = Query(100, ge=1, le=1000, description="Maximum signals to return"),
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    Get historical signals generated by a strategy.
    
    **Path Parameters:**
    - `strategy_id`: Strategy identifier
    
    **Query Parameters:**
    - `limit`: Maximum signals to return (default: 100)
    
    **Returns:** List of signals with:
    - Signal type (BUY/SELL/HOLD)
    - Price and timestamp
    - Signal strength
    - Indicator values
    - Reasoning
    
    **Example:** GET /api/v1/strategies/strategy-ma-001/signals?limit=50
    """
    try:
        # Get signals from CQRS read model
        signals = await query_service.get_signal_analytics(
            strategy_id=strategy_id,
            limit=limit
        )
        
        if not signals:
            raise HTTPException(
                status_code=404,
                detail=f"No signals found for strategy '{strategy_id}'"
            )
        
        # Convert to API responses
        # Note: This assumes SignalAnalytics has the right structure
        # You may need to adjust based on actual Day 7 implementation
        return [
            SignalResponse.from_attributes(signal)
            for signal in signals
        ]
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting strategy signals: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve strategy signals"
        )


@router.get(
    "/top",
    response_model=StrategyListResponse,
    summary="Get top strategies",
    description="Get top performing strategies ranked by profitability",
    responses={
        200: {"description": "Top strategies"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
async def get_top_strategies(
    limit: int = Query(10, ge=1, le=100, description="Number of top strategies to return"),
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    Get top performing strategies.
    
    **Query Parameters:**
    - `limit`: Number of strategies to return (default: 10, max: 100)
    - `metric`: Ranking metric (default: total_profit)
      - `total_profit`: Highest total profit
      - `sharpe_ratio`: Best risk-adjusted returns
      - `win_rate`: Highest win percentage
    
    **Returns:** Ranked list of top strategies
    
    **Example:** GET /api/v1/strategies/top?limit=5&metric=sharpe_ratio
    
    **Use Case:** Dashboard "Top Performers" widget
    """
    try:
        # Get top strategies from CQRS read models
        strategies = await query_service.get_top_strategies(limit=limit)
        
        response_list = [
            StrategyPerformanceResponse.from_read_model(strategy)
            for strategy in strategies
        ]
        
        return StrategyListResponse(
            strategies=response_list,
            total=len(response_list)
        )
    
    except Exception as e:
        logger.error(f"Error getting top strategies: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve top strategies"
        )