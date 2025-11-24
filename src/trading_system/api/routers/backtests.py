"""
Backtest Results API Router.

Exposes backtest run results via REST endpoints.
Integrates with backtest read models from Day 7 Session 2.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from uuid import UUID
import logging

# Day 7 imports
from trading_system.queries.strategy_queries import StrategyQueryService
from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool

# Day 8 imports
from trading_system.api.schemas.responses import (
    BacktestResponse,
    BacktestListResponse,
    ErrorResponse
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Reuse dependency from strategies router
async def get_db_pool() -> PostgresConnectionPool:
    """Get PostgreSQL connection pool."""
    pool = PostgresConnectionPool(
        host="localhost",
        port=5432,
        database="trading_db",
        user="trading",
        password="password"  # Must match docker-compose.yml
    )
    await pool.connect()
    return pool


async def get_query_service(
    pool: PostgresConnectionPool = Depends(get_db_pool)
) -> StrategyQueryService:
    """Get Strategy Query Service."""
    return StrategyQueryService(pool)


@router.get(
    "/",
    response_model=BacktestListResponse,
    summary="List backtest runs",
    description="Get a list of all backtest runs with results",
    responses={
        200: {"description": "List of backtests"},
        500: {"model": ErrorResponse}
    }
)
async def list_backtests(
    strategy_name: Optional[str] = Query(None, description="Filter by strategy name"),
    limit: int = Query(100, ge=1, le=1000),
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    List backtest runs with optional filters.
    
    **Query Parameters:**
    - `strategy_name`: Filter by strategy (e.g., "MovingAverageCrossover")
    - `symbol`: Filter by traded symbol (e.g., "AAPL")
    - `limit`: Maximum results to return
    - `offset`: Pagination offset
    
    **Returns:** List of backtest runs with complete metrics
    
    **Example:** GET /api/v1/backtests?strategy_name=MovingAverageCrossover&limit=20
    """
    try:
        backtests = await query_service.get_backtest_summaries(
            strategy_name=strategy_name,  # None = get all
            limit=limit
        )
        
        response_list = [
            BacktestResponse.from_read_model(backtest)
            for backtest in backtests
        ]
        
        return BacktestListResponse(
            backtests=response_list,
            total=len(response_list)
        )
    
    except Exception as e:
        logger.error(f"Error listing backtests: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve backtests"
        )


@router.get(
    "/{backtest_id}",
    response_model=BacktestResponse,
    summary="Get backtest details",
    description="Get complete details for a specific backtest run",
    responses={
        200: {"description": "Backtest details"},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse}
    }
)
async def get_backtest(
    backtest_id: UUID,
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    Get detailed results for a specific backtest run.
    
    **Path Parameters:**
    - `backtest_id`: UUID of the backtest run
    
    **Returns:** Complete backtest results including:
    - Strategy name and parameters
    - Performance metrics (returns, Sharpe, drawdown)
    - Test period (start/end dates)
    - Trade statistics
    
    **Example:** GET /api/v1/backtests/e4c7a3b2-9f1d-4e8a-b6c3-2d1f8e9a7c5b
    
    **Use Case:**
    - Deep dive into specific backtest
    - Verify strategy parameters used
    - Compare with other backtest runs
    """
    try:
        # Get from read model (Day 7)
        backtest = await query_service.get_backtest_by_id(str(backtest_id))
        
        if not backtest:
            raise HTTPException(
                status_code=404,
                detail=f"Backtest '{backtest_id}' not found"
            )
        
        return BacktestResponse.from_read_model(backtest)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting backtest: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve backtest"
        )


@router.get(
    "/strategy/{strategy_name}",
    response_model=BacktestListResponse,
    summary="Get backtests for strategy",
    description="Get all backtest runs for a specific strategy",
    responses={
        200: {"description": "Strategy backtests"},
        500: {"model": ErrorResponse}
    }
)
async def get_strategy_backtests(
    strategy_name: str,
    limit: int = Query(100, ge=1, le=1000),
    query_service: StrategyQueryService = Depends(get_query_service)
):
    """
    Get all backtest runs for a specific strategy.
    
    **Path Parameters:**
    - `strategy_name`: Name of the strategy
    
    **Query Parameters:**
    - `limit`: Maximum backtests to return
    
    **Returns:** All backtest runs for the strategy
    
    **Example:** GET /api/v1/backtests/strategy/MovingAverageCrossover?limit=50
    
    **Use Case:**
    - Track strategy evolution over time
    - Compare parameter tuning attempts
    - Identify best performing configurations
    """
    try:
        backtests = await query_service.get_backtest_summaries(
            strategy_name=strategy_name,
            limit=limit
        )
        
        response_list = [
            BacktestResponse.from_read_model(backtest)
            for backtest in backtests
        ]
        
        return BacktestListResponse(
            backtests=response_list,
            total=len(response_list)
        )
    
    except Exception as e:
        logger.error(f"Error getting strategy backtests: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backtests for strategy '{strategy_name}'"
        )