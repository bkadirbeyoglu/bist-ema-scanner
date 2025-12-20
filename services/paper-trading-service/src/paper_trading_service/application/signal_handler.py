"""
Signal Handler for Paper Trading.

Processes trading signals from the event bus and executes
orders on all running paper trading sessions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

from paper_trading_service.api.websocket import notify_trade_executed
from paper_trading_service.application.session_manager import SessionManager
from paper_trading_service.domain.session import SessionState


logger = logging.getLogger(__name__)


# ============================================================================
# SIGNAL DATA
# ============================================================================

@dataclass(frozen=True)
class TradingSignal:
    """
    Represents a trading signal from a strategy.
    
    Using frozen=True makes this immutable and hashable.
    """
    
    symbol: str
    signal_type: str  # "BUY", "SELL", "HOLD"
    price: Decimal
    strategy_name: str
    confidence: float = 1.0
    
    @classmethod
    def from_event(cls, event: dict) -> TradingSignal:
        """Create a TradingSignal from an event dictionary."""
        return cls(
            symbol=event.get("symbol", "").upper(),
            signal_type=event.get("signal_type", "HOLD").upper(),
            price=Decimal(str(event.get("price", 0))),
            strategy_name=event.get("strategy_name", "unknown"),
            confidence=float(event.get("confidence", 1.0)),
        )


# ============================================================================
# SIGNAL HANDLER
# ============================================================================

class SignalHandler:
    """
    Handles trading signals and executes orders.
    
    Configuration:
    - auto_trade: If True, automatically execute signals on all running sessions
    - position_size: Number of shares per trade
    - signal_filter: Optional list of strategy names to accept
    """
    
    def __init__(
        self,
        session_manager: SessionManager,
        auto_trade: bool = True,
        position_size: int = 100,
        signal_filter: list[str] | None = None,
    ) -> None:
        """
        Initialize the signal handler.
        
        Args:
            session_manager: Manager for paper trading sessions
            auto_trade: Whether to automatically execute signals
            position_size: Default number of shares per trade
            signal_filter: Optional list of strategy names to accept
        """
        self._session_manager = session_manager
        self._auto_trade = auto_trade
        self._position_size = position_size
        self._signal_filter: set[str] | None = set(signal_filter) if signal_filter else None
        self._signal_count = 0
    
    @property
    def signal_count(self) -> int:
        """Number of signals processed."""
        return self._signal_count
    
    async def handle_signal(self, signal: TradingSignal) -> list[dict]:
        """
        Handle a trading signal.
        
        Returns a list of execution results (one per session).
        """
        self._signal_count += 1
        
        # Filter by strategy name if configured
        if (
            self._signal_filter is not None
            and signal.strategy_name not in self._signal_filter  # pylint: disable=unsupported-membership-test
        ):
            logger.debug(
                "Ignoring signal from %s (not in filter)",
                signal.strategy_name,
            )
            return []
        
        # Ignore HOLD signals
        if signal.signal_type == "HOLD":
            logger.debug("Ignoring HOLD signal for %s", signal.symbol)
            return []
        
        # Check auto-trade setting
        if not self._auto_trade:
            logger.info(
                "Signal received (auto_trade=False): %s %s @ %s",
                signal.signal_type,
                signal.symbol,
                signal.price,
            )
            return []
        
        # Execute on all running sessions
        results = []
        
        for session_id in self._session_manager.list_session_ids():
            session = self._session_manager.get_session(session_id)
            if session and session.state == SessionState.RUNNING:
                result = await self._execute_on_session(session_id, signal)
                results.append(result)
        
        return results
    
    async def _execute_on_session(
        self,
        session_id: str,
        signal: TradingSignal,
    ) -> dict:
        """Execute a signal on a specific session."""
        try:
            result = self._session_manager.execute_order(
                session_id=session_id,
                symbol=signal.symbol,
                side=signal.signal_type,
                quantity=self._position_size,
                market_price=signal.price,
            )
            
            logger.info(
                "Executed %s %d %s @ %s on session %s",
                signal.signal_type,
                self._position_size,
                signal.symbol,
                signal.price,
                session_id,
            )
            
            # Notify WebSocket clients
            if result.get("success"):
                await notify_trade_executed(session_id, result)
            
            return {
                "session_id": session_id,
                "success": result.get("success", False),
                "result": result,
            }
        
        except Exception as e:
            logger.error(
                "Failed to execute signal on session %s: %s",
                session_id,
                str(e),
            )
            return {
                "session_id": session_id,
                "success": False,
                "error": str(e),
            }
    
    async def handle_event(self, event: dict) -> list[dict]:
        """
        Handle an event from the event bus.
        
        Only processes SignalGenerated events.
        """
        event_type = event.get("event_type", event.get("type", ""))
        
        if event_type not in ("SignalGenerated", "signal_generated"):
            return []
        
        signal = TradingSignal.from_event(event)
        return await self.handle_signal(signal)