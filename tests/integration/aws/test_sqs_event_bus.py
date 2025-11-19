"""
Integration tests for SQS Event Bus.

These tests verify that events are correctly published to and consumed from SQS.
Requires LocalStack to be running.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from typing import List

from trading_system.shared_kernel.base_event import BaseEvent
from trading_system.architecture.messaging.sqs_client import SQSConfig, create_sqs_client
from trading_system.architecture.messaging.sqs_event_bus import (
    SQSEventBus, get_queue_name_for_event
)


# ============================================================================
# TEST EVENTS
# ============================================================================

class TestEvent(BaseEvent):
    """Simple test event."""
    
    def __init__(
        self,
        event_id: str,
        aggregate_id: str,
        occurred_at: datetime,
        message: str
    ):
        super().__init__(event_id, aggregate_id, occurred_at)
        self.message = message
    
    def to_dict(self) -> dict:
        return {
            "message": self.message
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TestEvent':
        return cls(
            event_id=data.get("event_id", "test"),
            aggregate_id=data.get("aggregate_id", "test"),
            occurred_at=datetime.now(timezone.utc),
            message=data["message"]
        )


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
async def sqs_event_bus():
    """Create SQS event bus for testing."""
    config = SQSConfig(
        endpoint_url="http://localstack:4566",
        region_name="us-east-1",
        aws_access_key_id="test",
        aws_secret_access_key="test",
        wait_time_seconds=1,
        visibility_timeout=5  # ← Add this: short timeout for tests
    )
    
    async with create_sqs_client(config) as client:
        bus = SQSEventBus(client, create_queues=True, max_consumers=2)
        
        # Clean up any existing queues FIRST
        try:
            queues = await client.list_queues()
            for queue_url in queues:
                if 'TestEvent' in queue_url:
                    try:
                        await client.delete_queue(queue_url)
                    except Exception:
                        pass
            # Give localstack time to process deletions
            await asyncio.sleep(0.5)
        except Exception:
            pass
        
        try:
            yield bus
        finally:
            # Stop bus and wait for cleanup
            await bus.stop()
            await asyncio.sleep(1)
            
            # Cleanup queues after test
            try:
                queues = await client.list_queues()
                for queue_url in queues:
                    if 'TestEvent' in queue_url:
                        try:
                            await client.delete_queue(queue_url)
                        except Exception:
                            pass
            except Exception:
                pass


@pytest.fixture
def test_event():
    """Create a test event."""
    return TestEvent(
        event_id="test-123",
        aggregate_id="agg-456",
        occurred_at=datetime.now(timezone.utc),
        message="Hello from SQS!"
    )


# ============================================================================
# TESTS
# ============================================================================

@pytest.mark.asyncio
async def test_publish_event(sqs_event_bus, test_event):
    """Test publishing an event to SQS."""
    
    # Publish event
    await sqs_event_bus.publish(test_event)
    
    # Verify stats
    stats = sqs_event_bus.get_stats()
    assert stats["published_count"] == 1
    assert stats["error_count"] == 0


@pytest.mark.asyncio
async def test_subscribe_and_receive(sqs_event_bus, test_event):
    """Test subscribing to and receiving events."""
    
    # Track received events
    received_events: List[TestEvent] = []
    
    async def handler(event: TestEvent):
        received_events.append(event)
    
    # Subscribe
    subscription_id = sqs_event_bus.subscribe(TestEvent, handler)
    assert subscription_id is not None
    
    # Start consumer
    await sqs_event_bus.start()
    
    # Publish event
    await sqs_event_bus.publish(test_event)
    
    # Wait for consumption (give it time to poll and process)
    await asyncio.sleep(5)
    
    # Verify received
    assert len(received_events) == 1
    assert received_events[0].message == test_event.message
    
    # Verify stats
    stats = sqs_event_bus.get_stats()
    assert stats["published_count"] == 1
    assert stats["received_count"] == 1


async def test_multiple_subscribers(sqs_event_bus, test_event):
    """Test that multiple subscribers all receive the event."""
    
    # Track received events per handler
    handler1_events: List[TestEvent] = []
    handler2_events: List[TestEvent] = []
    
    async def handler1(event: TestEvent):
        print(f"📥 Handler1 called! Message: {event.message}")
        handler1_events.append(event)
        print(f"📊 Handler1 list now has {len(handler1_events)} events")
    
    async def handler2(event: TestEvent):
        print(f"📥 Handler2 called! Message: {event.message}")
        handler2_events.append(event)
        print(f"📊 Handler2 list now has {len(handler2_events)} events")
    
    # Subscribe both handlers
    sqs_event_bus.subscribe(TestEvent, handler1)
    sqs_event_bus.subscribe(TestEvent, handler2)
    
    # Start and publish
    await sqs_event_bus.start()
    await asyncio.sleep(1)  # ← Let consumers fully start

    await sqs_event_bus.publish(test_event)
    # Wait for consumption
    await asyncio.sleep(5)
    
    # Debug before assertion
    print(f"🔍 Before assert: handler1_events={len(handler1_events)}, handler2_events={len(handler2_events)}")
    
    # Both handlers should receive
    assert len(handler1_events) == 1
    assert len(handler2_events) == 1


async def test_handler_error_retry(sqs_event_bus, test_event):
    """Test that failed handlers trigger SQS retry."""
    
    attempt_count = 0
    
    async def failing_handler(event: TestEvent):
        nonlocal attempt_count
        attempt_count += 1
        
        if attempt_count < 3:
            raise ValueError("Simulated failure")
        # Success on 3rd attempt
    
    sqs_event_bus.subscribe(TestEvent, failing_handler)
    
    await sqs_event_bus.start()
    await asyncio.sleep(1)  # Let consumers start
    
    await sqs_event_bus.publish(test_event)
    
    # Wait for retries (visibility timeout is now 5s)
    # Need to wait for at least 2 retries: 5s + 5s + buffer
    await asyncio.sleep(12)
    
    # Should have attempted multiple times
    assert attempt_count >= 2


@pytest.mark.asyncio
async def test_filter_predicate(sqs_event_bus):
    """Test that filter predicates work correctly."""
    
    received_events: List[TestEvent] = []
    
    async def handler(event: TestEvent):
        received_events.append(event)
    
    # Subscribe with filter (only messages containing "important")
    sqs_event_bus.subscribe(
        TestEvent,
        handler,
        filter_predicate=lambda e: "important" in e.message.lower()
    )
    
    # Start consumer
    await sqs_event_bus.start()
    
    # Publish filtered and unfiltered events
    await sqs_event_bus.publish(TestEvent(
        "1", "1", datetime.now(timezone.utc),
        "Important message"
    ))
    
    await sqs_event_bus.publish(TestEvent(
        "2", "2", datetime.now(timezone.utc),
        "Regular message"
    ))
    
    await asyncio.sleep(5)
    
    # Should only receive the important one
    assert len(received_events) == 1
    assert "Important" in received_events[0].message


@pytest.mark.asyncio
async def test_unsubscribe(sqs_event_bus, test_event):
    """Test unsubscribing from events."""
    
    received_events: List[TestEvent] = []
    
    async def handler(event: TestEvent):
        received_events.append(event)
    
    # Subscribe
    sub_id = sqs_event_bus.subscribe(TestEvent, handler)
    
    # Unsubscribe immediately
    result = sqs_event_bus.unsubscribe(sub_id)
    assert result is True
    
    # Start and publish
    await sqs_event_bus.start()
    await sqs_event_bus.publish(test_event)
    
    await asyncio.sleep(5)
    
    # Should NOT receive (unsubscribed)
    assert len(received_events) == 0


@pytest.mark.asyncio
async def test_queue_creation(sqs_event_bus):
    """Test that queues are created automatically."""
    
    async def handler(event: TestEvent):
        pass
    
    # Subscribe (should create queue)
    sqs_event_bus.subscribe(TestEvent, handler)
    
    # Start (triggers queue creation)
    await sqs_event_bus.start()
    
    # Verify queue exists
    queue_name = get_queue_name_for_event(TestEvent, fifo=True)
    assert queue_name in sqs_event_bus._created_queues


# ============================================================================
# PERFORMANCE COMPARISON
# ============================================================================

@pytest.mark.asyncio
async def test_performance_comparison():
    """Compare InMemory vs SQS performance."""
    
    from trading_system.shared_kernel.event_bus import InMemoryEventBus
    import time
    
    # InMemory test
    inmem_bus = InMemoryEventBus()
    
    received_inmem = []
    
    async def inmem_handler(event: TestEvent):
        received_inmem.append(event)
    
    inmem_bus.subscribe(TestEvent, inmem_handler)
    await inmem_bus.start()
    
    start = time.time()
    for i in range(100):
        event = TestEvent("id", "agg", datetime.now(timezone.utc), f"msg-{i}")
        await inmem_bus.publish(event)
    inmem_duration = time.time() - start
    
    await inmem_bus.stop()
    
    print(f"\nInMemory: {inmem_duration:.3f}s for 100 events")
    print(f"Average: {inmem_duration / 100 * 1000:.2f}ms per event")
    
    # SQS test would be here (requires more complex setup)
    # Expected: ~25ms per event vs ~0.01ms for in-memory