"""
Concrete repository implementations.
"""

from typing import Dict, List, Optional
from uuid import UUID

from trading_system.contexts.order_management.domain.entities.order import (
    Order, OrderStatus
)
from trading_system.contexts.order_management.domain.repositories import (
    OrderRepository
)

class InMemoryOrderRepository(OrderRepository):
    """
    In-memory order repository using Python dict.
    
    Why start with in-memory?
    -------------------------
    1. Fast development (no database setup)
    2. Perfect for testing (instant, no cleanup)
    3. Validates the interface design
    4. Same interface as real implementation
    
    When to use:
    -----------
    - Development and prototyping
    - Unit tests
    - Integration tests
    - Demo environments
    
    When NOT to use:
    ---------------
    - Production (data lost on restart)
    - When you need persistence
    - When you need transactions
    """
    
    def __init__(self):
        """Initialize empty repository."""
        self._orders: Dict[UUID, Order] = {}

    async def save(self, order: Order) -> None:
        """Save order to dict."""
        self._orders[order.id] = order

    async def find_by_id(self, order_id: UUID) -> Optional[Order]:
        """Find order by ID."""
        return self._orders.get(order_id)
    
    async def find_by_symbol(self, symbol: str) -> List[Order]:
        """Find all orders for a symbol."""
        return [
            order  # Collect this order
            for order in self._orders.values()  # Loop through all orders (dict values only, ignore keys)
            if str(order.symbol) == symbol  # Filter: only include if symbols match (convert Symbol object to str)
        ]
        # This is a list comprehension - equivalent to:
        # result = []
        # for order in self._orders.values():
        #     if str(order.symbol) == symbol:
        #         result.append(order)
        # return result

    async def find_by_status(self, status: OrderStatus) -> List[Order]:
        """Find orders by status."""
        return [
            order 
            for order in self._orders.values() 
            if order.status == status
        ]
    
    async def find_active_orders(self) -> List[Order]:
        """Find active orders."""
        return [
            order 
            for order in self._orders.values() 
            if order.is_active
        ]
    
    async def delete(self, order_id: UUID) -> bool:
        """Delete order from dict."""
        deleted_order = self._orders.pop(order_id, None)
        return deleted_order is not None
    
    # Additional methods for testing
    def clear(self) -> None:
        """Clear all orders (for testing)."""
        self._orders.clear()
    
    @property
    def size(self) -> int:
        """Get number of stored orders."""
        return len(self._orders)

