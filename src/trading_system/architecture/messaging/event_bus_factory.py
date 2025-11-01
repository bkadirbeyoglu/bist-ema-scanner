"""
Event Bus Factory - Create the right event bus based on configuration.

This factory implements the Strategy pattern, allowing easy switching
between different event bus implementations (InMemory, SQS, Kafka, etc.)
without changing client code.

Usage:
    # Development (fast, in-memory)
    bus = await create_event_bus(EventBusType.IN_MEMORY)
    
    # Production (distributed, persistent)
    bus = await create_event_bus(EventBusType.SQS)
    
    # Automatic (based on environment)
    bus = await create_event_bus_from_config()
"""

from enum import Enum
from typing import Optional
import os

from trading_system.shared_kernel.event_bus_protocol import EventBus
from trading_system.shared_kernel.event_bus import InMemoryEventBus
from trading_system.architecture.messaging.sqs_event_bus import SQSEventBus
from trading_system.architecture.messaging.sqs_client import SQSConfig, SQSClient


# ============================================================================
# ENUM FOR CONFIGURATION
# ============================================================================

class EventBusType(str, Enum):
    """
    Available event bus implementations.
    
    This enum makes configuration type-safe and self-documenting.
    """
    IN_MEMORY = "in_memory"
    SQS = "sqs"
    # Future: KAFKA = "kafka", RABBITMQ = "rabbitmq", etc.


# ============================================================================
# FACTORY FUNCTIONS
# ============================================================================

async def create_event_bus(
    bus_type: EventBusType,
    sqs_config: Optional[SQSConfig] = None
) -> EventBus:
    """
    Create an event bus based on the specified type.
    
    Args:
        bus_type: Which implementation to create
        sqs_config: Configuration for SQS (if bus_type is SQS)
    
    Returns:
        EventBus implementation
    
    Raises:
        ValueError: If bus_type is unknown
    
    Note:
        For SQS event bus, the caller is responsible for calling bus.stop()
        and cleaning up the SQS client connection properly.
    
    Examples:
        # In-memory (development)
        bus = await create_event_bus(EventBusType.IN_MEMORY)
        await bus.start()
        # ... use bus ...
        await bus.stop()
        
        # SQS (production)
        config = SQSConfig(endpoint_url=None)  # Real AWS
        bus = await create_event_bus(EventBusType.SQS, sqs_config=config)
        await bus.start()
        # ... use bus ...
        await bus.stop()
    """
    if bus_type == EventBusType.IN_MEMORY:
        return InMemoryEventBus()
    
    elif bus_type == EventBusType.SQS:
        # Default config if none provided
        if sqs_config is None:
            # Try to read from environment variables
            sqs_config = SQSConfig(
                endpoint_url=os.getenv("SQS_ENDPOINT_URL", "http://localstack:4566"),
                region_name=os.getenv("AWS_REGION", "us-east-1"),
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID", "test"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY", "test"),
            )
        
        # Create SQS client directly (not using context manager)
        # The caller is responsible for cleanup via bus.stop()
        client = SQSClient(sqs_config)
        await client.connect()
        return SQSEventBus(client, create_queues=True)
    
    else:
        raise ValueError(f"Unknown event bus type: {bus_type}")


async def create_event_bus_from_config() -> EventBus:
    """
    Create event bus based on environment configuration.
    
    Reads EVENT_BUS_TYPE from environment:
    - "in_memory" → InMemoryEventBus
    - "sqs" → SQSEventBus
    - Not set → InMemoryEventBus (default)
    
    This is the recommended way to initialize the event bus in production,
    as it allows changing implementation without code changes.
    
    Environment variables:
        EVENT_BUS_TYPE: "in_memory" or "sqs" (default: "in_memory")
        SQS_ENDPOINT_URL: LocalStack or AWS endpoint (default: http://localstack:4566)
        AWS_REGION: AWS region (default: us-east-1)
        AWS_ACCESS_KEY_ID: AWS credentials (default: test)
        AWS_SECRET_ACCESS_KEY: AWS credentials (default: test)
    
    Examples:
        # Development (.env file)
        EVENT_BUS_TYPE=in_memory
        
        # Production (.env file)
        EVENT_BUS_TYPE=sqs
        SQS_ENDPOINT_URL=  # Empty = use real AWS
        AWS_REGION=us-west-2
        AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
        AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/...
    
    Usage:
        bus = await create_event_bus_from_config()
        await bus.start()
    """
    # Read configuration from environment
    bus_type_str = os.getenv("EVENT_BUS_TYPE", "in_memory").lower()
    
    try:
        bus_type = EventBusType(bus_type_str)
    except ValueError:
        # Invalid type, fallback to in-memory with warning
        print(f"⚠️  Warning: Unknown EVENT_BUS_TYPE='{bus_type_str}', using in_memory")
        bus_type = EventBusType.IN_MEMORY
    
    return await create_event_bus(bus_type)


# ============================================================================
# CONTEXT MANAGER FOR AUTOMATIC CLEANUP
# ============================================================================

class EventBusManager:
    """
    Context manager for event bus lifecycle.
    
    Handles start/stop automatically AND properly cleans up SQS client:
        async with EventBusManager() as bus:
            # Bus is started
            await bus.publish(event)
        # Bus is stopped automatically + resources cleaned up
    """
    
    def __init__(self, bus_type: Optional[EventBusType] = None):
        self.bus_type = bus_type
        self.bus: Optional[EventBus] = None
        self._sqs_client: Optional[SQSClient] = None
    
    async def __aenter__(self) -> EventBus:
        if self.bus_type:
            self.bus = await create_event_bus(self.bus_type)
        else:
            self.bus = await create_event_bus_from_config()
        
        # Track SQS client if it's an SQS bus (for proper cleanup)
        if isinstance(self.bus, SQSEventBus):
            self._sqs_client = self.bus._sqs_client
        
        await self.bus.start()
        return self.bus
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.bus:
            await self.bus.stop()
        
        # Clean up SQS client connection if we have one
        if self._sqs_client:
            await self._sqs_client.disconnect()


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import asyncio
    from trading_system.shared_kernel.events import BaseEvent
    from datetime import datetime, timezone
    
    # Example event
    class TestEvent(BaseEvent):
        def __init__(self, event_id, aggregate_id, occurred_at, message):
            super().__init__(event_id, aggregate_id, occurred_at)
            self.message = message
    
    async def main():
        # Method 1: Explicit type
        print("=== Method 1: Explicit Type ===")
        bus = await create_event_bus(EventBusType.IN_MEMORY)
        await bus.start()
        
        # Use bus...
        async def handler(event):
            print(f"Received: {event.message}")
        
        bus.subscribe(TestEvent, handler)
        await bus.publish(TestEvent("1", "1", datetime.now(timezone.utc), "Hello!"))
        
        await asyncio.sleep(0.1)  # Let handler run
        await bus.stop()
        
        # Method 2: From config
        print("\n=== Method 2: From Config ===")
        os.environ["EVENT_BUS_TYPE"] = "in_memory"
        bus2 = await create_event_bus_from_config()
        await bus2.start()
        # ... use bus2 ...
        await bus2.stop()
        
        # Method 3: Context manager (recommended)
        print("\n=== Method 3: Context Manager ===")
        async with EventBusManager(EventBusType.IN_MEMORY) as bus3:
            bus3.subscribe(TestEvent, handler)
            await bus3.publish(TestEvent("2", "2", datetime.now(timezone.utc), "World!"))
            await asyncio.sleep(0.1)
        # Automatically stopped and cleaned up
    
    asyncio.run(main())