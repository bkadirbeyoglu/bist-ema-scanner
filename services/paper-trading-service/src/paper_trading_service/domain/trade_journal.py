"""
Trade Journal.

Memory-efficient audit trail of all paper trades.

═══════════════════════════════════════════════════════════════════════════════
PYTHON FEATURE: collections.deque
═══════════════════════════════════════════════════════════════════════════════

deque (double-ended queue) is optimized for fast appends and pops from
both ends, unlike list which is O(n) for left-side operations.

Key feature: maxlen parameter for automatic size limiting:

    from collections import deque
    
    d = deque(maxlen=3)
    d.append(1)  # [1]
    d.append(2)  # [1, 2]
    d.append(3)  # [1, 2, 3]
    d.append(4)  # [2, 3, 4] ← oldest item (1) auto-removed!

Benefits:
    • O(1) append/pop from both ends
    • Automatic eviction of old items (with maxlen)
    • Thread-safe for single operations
    • Memory-bounded by design

When to use:
    ✅ Rolling windows (last N items)
    ✅ FIFO queues
    ✅ Memory-constrained histories
    ❌ Random access by index (O(n) for middle elements)
═══════════════════════════════════════════════════════════════════════════════
"""

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterator
from uuid import UUID, uuid4

from paper_trading_service.domain.order_simulator import OrderSide


@dataclass
class TradeRecord:
    """Immutable record of an executed trade."""
    symbol: str
    side: OrderSide
    quantity: int
    price: Decimal
    commission: Decimal
    trade_id: UUID = field(default_factory=uuid4)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    slippage: Decimal = Decimal("0")
    realized_pnl: Decimal = Decimal("0")
    
    @property
    def value(self) -> Decimal:
        """Trade value (quantity × price)."""
        return self.quantity * self.price


class TradeJournal:
    """
    Memory-bounded trade history.
    
    Uses deque with maxlen to automatically discard old trades
    when the journal exceeds capacity. This prevents unbounded
    memory growth in long-running sessions.
    """
    
    def __init__(self, max_entries: int = 10000) -> None:
        """
        Create trade journal.
        
        Args:
            max_entries: Maximum trades to keep (oldest auto-removed)
        """
        # deque with maxlen automatically evicts oldest when full
        self._trades: deque[TradeRecord] = deque(maxlen=max_entries)
    
    def record(self, trade: TradeRecord) -> None:
        """
        Record a trade.
        
        If journal is at capacity, oldest trade is automatically removed.
        """
        self._trades.append(trade)
    
    @property
    def trade_count(self) -> int:
        """Number of trades in journal."""
        return len(self._trades)
    
    def get_all(self) -> list[TradeRecord]:
        """Get all trades (oldest first)."""
        return list(self._trades)
    
    def get_recent(self, n: int) -> list[TradeRecord]:
        """
        Get N most recent trades (newest first).
        
        Args:
            n: Number of trades to return
        """
        # Get last n items, then reverse for newest-first
        trades = list(self._trades)[-n:]
        return list(reversed(trades))
    
    def get_by_symbol(self, symbol: str) -> list[TradeRecord]:
        """Get all trades for a symbol."""
        symbol = symbol.upper()
        return [t for t in self._trades if t.symbol.upper() == symbol]
    
    # ═══════════════════════════════════════════════════════════════════════
    # Statistics
    # ═══════════════════════════════════════════════════════════════════════
    
    @property
    def total_commission(self) -> Decimal:
        """Total commissions paid."""
        return sum((t.commission for t in self._trades), Decimal("0"))
    
    @property
    def total_volume(self) -> Decimal:
        """Total trading volume (sum of trade values)."""
        return sum((t.value for t in self._trades), Decimal("0"))
    
    @property
    def symbols_traded(self) -> list[str]:
        """Unique symbols traded."""
        return list(set(t.symbol for t in self._trades))
    
    def __len__(self) -> int:
        return len(self._trades)
    
    def __repr__(self) -> str:
        return f"TradeJournal(trades={len(self._trades)})"