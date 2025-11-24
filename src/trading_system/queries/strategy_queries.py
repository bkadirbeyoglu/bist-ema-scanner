"""
Query Service for Strategy Read Models.

Provides high-level query methods for dashboards and reports.
"""

import logging
from typing import List, Optional
from datetime import datetime

from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.read_models.schemas import (
    StrategyPerformance, 
    SignalAnalytics, 
    BacktestSummary,
    StrategyStatus
)

logger = logging.getLogger(__name__)


class StrategyQueryService:
    """
    Query service for strategy read models.
    
    PERFORMANCE:
    All queries target indexed read models for sub-10ms response.
    """
    
    def __init__(self, pool: PostgresConnectionPool):
        self.pool = pool
    
    async def get_strategy_performance(
        self, 
        strategy_id: str
    ) -> Optional[StrategyPerformance]:
        """
        Get aggregated performance for a strategy.
        
        QUERY TIME: < 1ms (primary key lookup)
        
        Example:
            perf = await query_service.get_strategy_performance("strategy-ma-AAPL")
            print(f"Win Rate: {perf.win_rate}%")
        """
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM read_models.strategy_performance
                WHERE strategy_id = $1
            """, strategy_id)
            
            if not row:
                return None
            
            return StrategyPerformance(
                strategy_id=row['strategy_id'],
                strategy_name=row['strategy_name'],
                symbol=row['symbol'],
                status=StrategyStatus(row['status']),
                total_signals=row['total_signals'],
                buy_signals=row['buy_signals'],
                sell_signals=row['sell_signals'],
                hold_signals=row['hold_signals'],
                winning_signals=row['winning_signals'],
                losing_signals=row['losing_signals'],
                win_rate=row['win_rate'],
                avg_profit_per_signal=row['avg_profit_per_signal'],
                total_profit=row['total_profit'],
                max_profit=row['max_profit'],
                max_loss=row['max_loss'],
                avg_signal_strength=row['avg_signal_strength'],
                sharpe_ratio=row['sharpe_ratio'],
                first_signal_time=row['first_signal_time'],
                last_signal_time=row['last_signal_time'],
                last_updated=row['last_updated']
            )
    
    async def get_top_strategies(self, limit: int = 10) -> List[StrategyPerformance]:
        """
        Get top performing strategies by win rate.
        
        QUERY TIME: < 10ms (indexed + limit)
        
        Example:
            top = await query_service.get_top_strategies(5)
            for strategy in top:
                print(f"{strategy.strategy_name}: {strategy.win_rate}%")
        """
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM read_models.strategy_performance
                WHERE total_signals >= 10  -- Minimum sample size
                ORDER BY win_rate DESC
                LIMIT $1
            """, limit)
            
            return [self._row_to_performance(row) for row in rows]
    
    async def get_recent_signals(
        self,
        strategy_id: str,
        limit: int = 50
    ) -> List[SignalAnalytics]:
        """
        Get recent signals for a strategy.
        
        QUERY TIME: < 20ms (indexed query + limit)
        
        Example:
            signals = await query_service.get_recent_signals("strategy-ma-AAPL", 10)
            for signal in signals:
                print(f"{signal.signal_type} at ${signal.price_at_signal}")
        """
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM read_models.signal_analytics
                WHERE strategy_id = $1
                ORDER BY signal_time DESC
                LIMIT $2
            """, strategy_id, limit)
            
            return [self._row_to_signal(row) for row in rows]
    
    async def compare_backtests(
        self,
        strategy_name: str,
        symbol: str
    ) -> List[BacktestSummary]:
        """
        Compare all backtest runs for a strategy/symbol.
        
        QUERY TIME: < 15ms
        
        Example:
            results = await query_service.compare_backtests("MovingAverage", "AAPL")
            for result in results:
                print(f"Run {result.backtest_id}: {result.total_return}%")
        """
        async with self.pool.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM read_models.backtest_summaries
                WHERE strategy_name = $1 AND symbol = $2
                ORDER BY total_return DESC
            """, strategy_name, symbol)
            
            return [self._row_to_backtest(row) for row in rows]
    
    def _row_to_performance(self, row) -> StrategyPerformance:
        """Convert database row to StrategyPerformance."""
        return StrategyPerformance(
            strategy_id=row['strategy_id'],
            strategy_name=row['strategy_name'],
            symbol=row['symbol'],
            status=StrategyStatus(row['status']),
            total_signals=row['total_signals'],
            buy_signals=row['buy_signals'],
            sell_signals=row['sell_signals'],
            hold_signals=row['hold_signals'],
            winning_signals=row['winning_signals'],
            losing_signals=row['losing_signals'],
            win_rate=row['win_rate'],
            avg_profit_per_signal=row['avg_profit_per_signal'],
            total_profit=row['total_profit'],
            max_profit=row['max_profit'],
            max_loss=row['max_loss'],
            avg_signal_strength=row['avg_signal_strength'],
            sharpe_ratio=row['sharpe_ratio'],
            first_signal_time=row['first_signal_time'],
            last_signal_time=row['last_signal_time'],
            last_updated=row['last_updated']
        )
    
    def _row_to_signal(self, row) -> SignalAnalytics:
        """Convert database row to SignalAnalytics."""
        return SignalAnalytics(
            signal_id=row['signal_id'],
            strategy_id=row['strategy_id'],
            symbol=row['symbol'],
            signal_type=row['signal_type'],
            signal_strength=row['signal_strength'],
            price_at_signal=row['price_at_signal'],
            indicators=row['indicators'],
            reason=row['reason'],
            actual_profit=row['actual_profit'],
            was_profitable=row['was_profitable'],
            signal_time=row['signal_time'],
            last_updated=row['last_updated']
        )
    
    def _row_to_backtest(self, row) -> BacktestSummary:
        """Convert database row to BacktestSummary."""
        return BacktestSummary(
            backtest_id=row['backtest_id'],
            strategy_name=row['strategy_name'],
            symbol=row['symbol'],
            parameters=row['parameters'],
            total_return=row['total_return'],
            sharpe_ratio=row['sharpe_ratio'],
            max_drawdown=row['max_drawdown'],
            start_date=row['start_date'],
            end_date=row['end_date'],
            completed_at=row['completed_at'],
            last_updated=row['last_updated']
        )
    
    async def get_backtest_summaries(
        self,
        strategy_name: Optional[str] = None,
        limit: int = 100
    ) -> List[BacktestSummary]:
        """Get backtest summaries, optionally filtered by strategy."""
        async with self.pool.pool.acquire() as conn:
            if strategy_name:
                rows = await conn.fetch("""
                    SELECT * FROM read_models.backtest_summaries
                    WHERE strategy_name = $1
                    ORDER BY completed_at DESC
                    LIMIT $2
                """, strategy_name, limit)
            else:
                rows = await conn.fetch("""
                    SELECT * FROM read_models.backtest_summaries
                    ORDER BY completed_at DESC
                    LIMIT $1
                """, limit)
            
            return [self._row_to_backtest_summary(row) for row in rows]
    
    async def get_backtest_by_id(self, backtest_id: str) -> Optional[BacktestSummary]:
        """Get a specific backtest by ID."""
        async with self.pool.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM read_models.backtest_summaries
                WHERE backtest_id = $1
            """, backtest_id)
            
            if not row:
                return None
            
            return self._row_to_backtest_summary(row)
    
    def _row_to_backtest_summary(self, row) -> BacktestSummary:
        """Convert database row to BacktestSummary."""
        return BacktestSummary(
            backtest_id=row['backtest_id'],
            strategy_name=row['strategy_name'],
            symbol=row['symbol'],
            parameters=row['parameters'] if row['parameters'] else {},
            total_return=row['total_return'],
            sharpe_ratio=row['sharpe_ratio'],
            max_drawdown=row['max_drawdown'],
            start_date=row['start_date'],
            end_date=row['end_date'],
            completed_at=row['completed_at'],
            last_updated=row['last_updated']  # ← Don't forget this!
        )