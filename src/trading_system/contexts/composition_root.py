"""
Composition Root - Dependency Injection Container.

This module is responsible for creating and wiring together all dependencies.
It follows the Composition Root pattern - all object creation happens here.
"""

import asyncio
from typing import Optional
from dataclasses import dataclass

from trading_system.config import Config
from trading_system.shared_kernel.event_bus_protocol import EventBus
from trading_system.architecture.messaging.event_bus_factory import (
    create_event_bus,
    EventBusType
)
from trading_system.architecture.messaging.sqs_client import SQSConfig

# Import your domain services, repositories, etc.
# from trading_system.contexts.order_management.application.services import OrderService
# from trading_system.contexts.order_management.infrastructure.repositories import InMemoryOrderRepository


@dataclass
class CompositionRoot:
    """
    Dependency injection container.
    
    This class holds all the application's dependencies and makes them
    available to the rest of the application.
    
    Usage:
        # Create with defaults
        root = await CompositionRoot.create()
        
        # Use dependencies
        await root.event_bus.publish(some_event)
        
        # Cleanup when done
        await root.cleanup()
    """
    
    config: Config
    event_bus: EventBus
    
    # Add other dependencies here as you build them:
    # order_repository: OrderRepository
    # order_service: OrderService
    # portfolio_service: PortfolioService
    # etc.
    
    @classmethod
    async def create(cls, config: Optional[Config] = None) -> 'CompositionRoot':
        """
        Create and initialize composition root.
        
        This factory method creates all dependencies and wires them together.
        
        Args:
            config: Optional config (creates default if None)
        
        Returns:
            Fully initialized CompositionRoot
        
        Examples:
            # With default config
            root = await CompositionRoot.create()
            
            # With custom config
            config = Config(environment="production")
            root = await CompositionRoot.create(config)
        """
        if config is None:
            config = Config()
        
        # Validate configuration
        config.validate()
        
        # Create event bus based on configuration
        event_bus = await cls._create_event_bus(config)
        await event_bus.start()
        
        # Create other dependencies here...
        # order_repository = InMemoryOrderRepository()
        # order_service = OrderService(order_repository, event_bus)
        
        return cls(
            config=config,
            event_bus=event_bus,
            # Add other dependencies:
            # order_repository=order_repository,
            # order_service=order_service,
        )
    
    @staticmethod
    async def _create_event_bus(config: Config) -> EventBus:
        """
        Create event bus based on configuration.
        
        Args:
            config: Application configuration
        
        Returns:
            Configured event bus instance
        """
        if config.event_bus_type == EventBusType.IN_MEMORY:
            return await create_event_bus(EventBusType.IN_MEMORY)
        
        elif config.event_bus_type == EventBusType.SQS:
            # Create SQS config from application config
            sqs_config = SQSConfig(
                endpoint_url=config.sqs_endpoint_url,
                region_name=config.sqs_region,
                aws_access_key_id=config.sqs_access_key,
                aws_secret_access_key=config.sqs_secret_key
            )
            return await create_event_bus(EventBusType.SQS, sqs_config)
        
        else:
            raise ValueError(f"Unknown event bus type: {config.event_bus_type}")
    
    async def cleanup(self) -> None:
        """
        Clean up resources.
        
        Call this when shutting down the application to ensure
        all resources are properly released.
        """
        # Stop event bus
        await self.event_bus.stop()
        
        # Clean up SQS client if using SQS
        from trading_system.architecture.messaging.sqs_event_bus import SQSEventBus
        if isinstance(self.event_bus, SQSEventBus):
            await self.event_bus._sqs_client.disconnect()
        
        # Clean up other resources as needed...
        # await self.database.disconnect()
        # await self.redis.disconnect()


# ============================================================================
# CONVENIENCE FUNCTION
# ============================================================================

async def initialize_application(config: Optional[Config] = None) -> CompositionRoot:
    """
    Initialize the entire application.
    
    This is the main entry point for application initialization.
    
    Args:
        config: Optional configuration
    
    Returns:
        Initialized composition root
    
    Examples:
        # In main.py
        async def main():
            root = await initialize_application()
            
            # Use the application...
            await root.event_bus.publish(some_event)
            
            # Cleanup
            await root.cleanup()
    """
    return await CompositionRoot.create(config)