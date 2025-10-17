"""
Repository interfaces for Order Management context.

This module defines the contract that any order storage mechanism must follow.
"""

from abc import ABC, abstractmethod
from typing import List, Optional
from uuid import UUID

from trading_system.contexts.order_management.domain.entities.order import (
    Order, OrderStatus
)


class OrderRepository(ABC):
    """
    Abstract repository for Order aggregate.
    
    This ABC defines the interface for order persistence.
    Any concrete implementation (PostgreSQL, MongoDB, in-memory)
    MUST implement all @abstractmethod methods.
    """

    @abstractmethod
    async def save(self, order: Order) -> None:
        """
        Save or update an order.
        
        The @abstractmethod decorator means:
        - This method has no implementation here
        - Subclasses MUST override this method
        - If they don't, Python raises TypeError when instantiating
        """
        pass

    @abstractmethod
    async def find_by_id(self, order_id: UUID) -> Optional[Order]:
        """
        Find order by unique identifier.
        
        Returns:
            Order if found, None if not found
        """
        pass

    @abstractmethod
    async def find_by_symbol(self, symbol: str) -> List[Order]:
        """
        Find all orders for a symbol.
        
        Returns:
            List of orders (empty list if none found)
        """
        pass

    @abstractmethod
    async def find_by_status(self, status: OrderStatus) -> List[Order]:
        """Find orders by status."""
        pass
    
    @abstractmethod
    async def find_active_orders(self) -> List[Order]:
        """Find all active orders (PENDING or SUBMITTED)."""
        pass

    @abstractmethod
    async def delete(self, order_id: UUID) -> bool:
        """
        Delete an order.
        
        Returns:
            True if deleted, False if not found
        """
        pass

    # Concrete method - subclasses inherit this
    async def exists(self, order_id: UUID) -> bool:
        """Check if order exists."""
        order = await self.find_by_id(order_id)
        return order is not None