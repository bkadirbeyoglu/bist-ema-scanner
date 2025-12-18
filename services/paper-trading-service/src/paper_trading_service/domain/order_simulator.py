"""
Order Simulator.

Simulates realistic order execution with slippage and commissions.

═══════════════════════════════════════════════════════════════════════════════
PYTHON FEATURE: match statement (Python 3.10+)
═══════════════════════════════════════════════════════════════════════════════

The match statement provides structural pattern matching—like switch/case
but more powerful. It can match values, types, and even destructure objects.

Basic syntax:
    match value:
        case Pattern1:
            # handle pattern 1
        case Pattern2 if condition:
            # pattern with guard clause
        case _:
            # wildcard (default case)

Examples:
    # Match on value
    match status_code:
        case 200:
            return "OK"
        case 404:
            return "Not Found"
        case _:
            return "Unknown"
    
    # Match on enum
    match side:
        case OrderSide.BUY:
            return price + slippage
        case OrderSide.SELL:
            return price - slippage

Benefits over if/elif chains:
    • More readable for multiple branches
    • Exhaustiveness checking with type checkers
    • Can destructure values (e.g., tuples, dataclasses)
    • Guards (if conditions) for complex matching
═══════════════════════════════════════════════════════════════════════════════
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class OrderSide(str, Enum):
    """Order direction."""
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    """Order type."""
    MARKET = "MARKET"
    LIMIT = "LIMIT"


@dataclass
class OrderRequest:
    """Request to execute an order."""
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: Decimal | None = None
    order_id: UUID = field(default_factory=uuid4)

    def __post_init__(self) -> None:
        self.symbol = self.symbol.upper()
        if self.order_type == OrderType.LIMIT and self.limit_price is None:
            raise ValueError("Limit orders require limit_price")
        

@dataclass
class OrderResult:
    """Result of order execution."""
    order_id: UUID
    symbol: str
    side: OrderSide
    quantity: int
    filled: bool
    fill_price: Decimal | None = None
    slippage: Decimal = Decimal("0")
    commission: Decimal = Decimal("0")
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rejection_reason: str | None = None


class OrderSimulator:
    """
    Simulates order execution with slippage and commissions.
    
    Slippage models the market impact of your order:
    - BUY: Price moves up (you pay more)
    - SELL: Price moves down (you receive less)
    """
    
    def __init__(
        self,
        slippage_bps: int = 5,
        commission_per_share: Decimal = Decimal("0.005"),
        min_commission: Decimal = Decimal("1.00"),
    ) -> None:
        """
        Create order simulator.
        
        Args:
            slippage_bps: Slippage in basis points (5 = 0.05%)
            commission_per_share: Commission per share
            min_commission: Minimum commission per order
        """
        self._slippage_rate = Decimal(slippage_bps) / Decimal("10000")
        self._commission_per_share = commission_per_share
        self._min_commission = min_commission

    def execute(
        self,
        request: OrderRequest,
        market_price: Decimal
    ) -> OrderResult:
        """
        Execute an order request.
        
        Args:
            request: The order to execute
            market_price: Current market price
            
        Returns:
            Execution result (filled or rejected)
        """
        # ═══════════════════════════════════════════════════════════════════
        # Using match statement to route by order type
        # ═══════════════════════════════════════════════════════════════════
        match request.order_type:
            case OrderType.MARKET:
                return self._execute_market(request, market_price)
            case OrderType.LIMIT:
                return self._execute_limit(request, market_price)
            case _:
                return OrderResult(
                    order_id=request.order_id,
                    symbol=request.symbol,
                    side=request.side,
                    quantity=request.quantity,
                    filled=False,
                    rejection_reason=f"Unknown order type: {request.order_type}",
                )
            
    def _execute_market(
        self,
        request: OrderRequest,
        market_price: Decimal
    ) -> OrderResult:
        """Execute market order with slippage."""
        market_price = Decimal(str(market_price))
        slippage = (market_price * self._slippage_rate).quantize(Decimal("0.01"))
        
        # Apply slippage based on order side
        match request.side:
            case OrderSide.BUY:
                fill_price = market_price + slippage
            case OrderSide.SELL:
                fill_price = market_price - slippage
        
        commission = self._calculate_commission(request.quantity)
        
        return OrderResult(
            order_id=request.order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled=True,
            fill_price=fill_price,
            slippage=slippage,
            commission=commission,
        )
    
    def _execute_limit(
        self,
        request: OrderRequest,
        market_price: Decimal,
    ) -> OrderResult:
        """Execute limit order if conditions met."""
        market_price = Decimal(str(market_price))
        limit_price = request.limit_price
        
        # Check if limit conditions are met
        can_fill = False
        match request.side:
            case OrderSide.BUY:
                can_fill = market_price <= limit_price
            case OrderSide.SELL:
                can_fill = market_price >= limit_price
        
        if not can_fill:
            return OrderResult(
                order_id=request.order_id,
                symbol=request.symbol,
                side=request.side,
                quantity=request.quantity,
                filled=False,
                rejection_reason=f"Limit not met: market {market_price} vs limit {limit_price}",
            )
        
        commission = self._calculate_commission(request.quantity)
        
        return OrderResult(
            order_id=request.order_id,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled=True,
            fill_price=market_price,
            slippage=Decimal("0"),
            commission=commission,
        )
    
    def _calculate_commission(self, quantity: int) -> Decimal:
        """Calculate commission with minimum."""
        commission = self._commission_per_share * quantity
        return max(commission, self._min_commission)