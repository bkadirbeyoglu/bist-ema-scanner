# src/trading_system/contexts/composition_root.py
"""
Composition Root - Where we wire up all dependencies.

This is the ONLY place where we create concrete implementations
and wire them together. All other code depends on abstractions.
"""

import logging

from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.contexts.order_management.infrastructure.repositories import (
    InMemoryOrderRepository
)
from trading_system.contexts.order_management.application.services import (
    OrderManagementService
)
from trading_system.contexts.portfolio_management.application.event_handlers import (
    PortfolioEventHandlers
)
from trading_system.contexts.risk_management.application.event_handlers import (
    RiskManagementEventHandlers
)

logger = logging.getLogger(__name__)


class ApplicationContext:
    """
    Application context holding all wired dependencies.
    
    This is the Composition Root pattern:
    - Creates all concrete implementations
    - Wires dependencies together
    - Provides access to services
    """
    
    def __init__(self):
        logger.info("Initializing application context...")
        
        # Infrastructure
        self.event_bus = InMemoryEventBus()
        self.order_repository = InMemoryOrderRepository()
        
        # Application services
        self.order_service = OrderManagementService(
            order_repository=self.order_repository,
            event_bus=self.event_bus
        )
        
        # Event handlers - automatically subscribe on creation
        self.portfolio_handlers = PortfolioEventHandlers(
            event_bus=self.event_bus
        )
        
        self.risk_handlers = RiskManagementEventHandlers(
            event_bus=self.event_bus
        )
        
        logger.info("Application context initialized")
    
    def get_order_service(self) -> OrderManagementService:
        """Get order management service."""
        return self.order_service
    
    async def shutdown(self):
        """Graceful shutdown."""
        logger.info("Shutting down application context...")
        self.event_bus.clear()
        self.order_repository.clear()
        logger.info("Application context shut down")