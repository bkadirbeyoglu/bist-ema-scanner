"""
Paper Trading Session.

Orchestrates portfolio, simulator, and journal into a cohesive experience.

═══════════════════════════════════════════════════════════════════════════════
PYTHON FEATURE: enum.auto()
═══════════════════════════════════════════════════════════════════════════════

auto() automatically generates unique values for enum members:

    from enum import Enum, auto
    
    class Color(Enum):
        RED = auto()    # 1
        GREEN = auto()  # 2
        BLUE = auto()   # 3

Benefits:
    • No need to manually assign values
    • Guaranteed unique values
    • Values increment automatically

When to use:
    ✅ When you only care about identity, not specific values
    ✅ State machines where states are compared by identity
    ❌ When you need specific values (e.g., for database storage)
    ❌ When values have meaning (e.g., HTTP status codes)
═══════════════════════════════════════════════════════════════════════════════
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, auto
from uuid import UUID, uuid4

from paper_trading_service.domain.portfolio import VirtualPortfolio, PortfolioSnapshot
from paper_trading_service.domain.order_simulator import (
    OrderSimulator,
    OrderRequest,
    OrderResult,
    OrderSide,
    OrderType,
)
from paper_trading_service.domain.trade_journal import TradeJournal, TradeRecord


class SessionState(Enum):
    """Session lifecycle states."""
    IDLE = auto()      # Created, not yet started
    RUNNING = auto()   # Actively accepting trades
    PAUSED = auto()    # Temporarily halted
    STOPPED = auto()   # Permanently terminated


@dataclass
class SessionConfig:
    """Configuration for paper trading session."""
    initial_cash: Decimal = Decimal("100000.00")
    slippage_bps: int = 5
    commission_per_share: Decimal = Decimal("0.005")
    min_commission: Decimal = Decimal("1.00")
    max_journal_entries: int = 10000


class PaperTradingSession:
    """
    A paper trading session.
    
    Orchestrates:
    • Portfolio - cash and positions
    • OrderSimulator - execution with slippage
    • TradeJournal - audit trail
    
    State machine:
        IDLE → RUNNING → PAUSED → RUNNING → STOPPED
                    ↓                   ↓
                 STOPPED            STOPPED
    """
    
    def __init__(
        self,
        initial_cash: Decimal,
        config: SessionConfig | None = None,
        session_id: UUID | None = None,
    ) -> None:
        """Create paper trading session."""
        config = config or SessionConfig(initial_cash=initial_cash)
        
        self._id = session_id or uuid4()
        self._state = SessionState.IDLE
        self._started_at: datetime | None = None
        self._stopped_at: datetime | None = None
        
        self._portfolio = VirtualPortfolio(initial_cash=initial_cash)
        self._simulator = OrderSimulator(
            slippage_bps=config.slippage_bps,
            commission_per_share=config.commission_per_share,
            min_commission=config.min_commission,
        )
        self._journal = TradeJournal(max_entries=config.max_journal_entries)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Properties
    # ═══════════════════════════════════════════════════════════════════════
    
    @property
    def id(self) -> UUID:
        return self._id
    
    @property
    def state(self) -> SessionState:
        return self._state
    
    @property
    def portfolio(self) -> VirtualPortfolio:
        return self._portfolio
    
    @property
    def journal(self) -> TradeJournal:
        return self._journal
    
    @property
    def is_running(self) -> bool:
        return self._state == SessionState.RUNNING
    
    # ═══════════════════════════════════════════════════════════════════════
    # Lifecycle
    # ═══════════════════════════════════════════════════════════════════════
    
    def start(self) -> None:
        """Start trading session."""
        if self._state != SessionState.IDLE:
            raise ValueError(f"Cannot start session in {self._state.name} state")
        
        self._state = SessionState.RUNNING
        self._started_at = datetime.now(timezone.utc)
    
    def pause(self) -> None:
        """Pause trading session."""
        if self._state != SessionState.RUNNING:
            raise ValueError(f"Cannot pause session in {self._state.name} state")
        
        self._state = SessionState.PAUSED
    
    def resume(self) -> None:
        """Resume paused session."""
        if self._state != SessionState.PAUSED:
            raise ValueError(f"Cannot resume session in {self._state.name} state")
        
        self._state = SessionState.RUNNING
    
    def stop(self) -> None:
        """Stop trading session (permanent)."""
        self._state = SessionState.STOPPED
        self._stopped_at = datetime.now(timezone.utc)
    
    # ═══════════════════════════════════════════════════════════════════════
    # Trading
    # ═══════════════════════════════════════════════════════════════════════
    
    def process_signal(
        self,
        symbol: str,
        side: OrderSide,
        quantity: int,
        price: Decimal,
    ) -> OrderResult:
        """
        Process a trading signal.
        
        Args:
            symbol: Symbol to trade
            side: BUY or SELL
            quantity: Number of shares
            price: Current market price
            
        Returns:
            Execution result
            
        Raises:
            ValueError: If session not running
        """
        if not self.is_running:
            raise ValueError(f"Session not running (state={self._state.name})")
        
        # Create and execute order
        request = OrderRequest(
            symbol=symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=quantity,
        )
        
        result = self._simulator.execute(request, market_price=price)
        
        # Update portfolio and journal if filled
        if result.filled and result.fill_price is not None:
            realized_pnl = Decimal("0")
            
            if side == OrderSide.BUY:
                self._portfolio.buy(symbol, quantity, result.fill_price)
            else:
                realized_pnl = self._portfolio.sell(symbol, quantity, result.fill_price)
            
            self._journal.record(TradeRecord(
                symbol=symbol,
                side=side,
                quantity=quantity,
                price=result.fill_price,
                commission=result.commission,
                slippage=result.slippage,
                realized_pnl=realized_pnl,
            ))
        
        return result
    
    def snapshot(self, prices: dict[str, Decimal]) -> PortfolioSnapshot:
        """Get portfolio snapshot at current prices."""
        return self._portfolio.snapshot(prices)
    
    def __repr__(self) -> str:
        return f"PaperTradingSession(id={self._id}, state={self._state.name})"