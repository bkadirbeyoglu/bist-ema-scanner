"""Integration tests for SQS client."""

import pytest
import uuid

from trading_system.architecture.messaging.sqs_client import SQSClient


def unique_queue_name(base_name: str) -> str:
    """Generate unique queue name to avoid test interference."""
    return f"{base_name}-{uuid.uuid4().hex[:8]}"


@pytest.mark.asyncio
async def test_create_and_list_queue():
    """Test creating a queue and verifying it exists."""
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        queue_name = unique_queue_name("test-orders-queue")
        queue_url = await sqs.create_queue(queue_name)
        
        assert queue_url is not None
        assert queue_name in queue_url
        assert ":4566" in queue_url


@pytest.mark.asyncio
async def test_send_and_receive_message():
    """Test sending and receiving a message."""
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        queue_name = unique_queue_name("test-messages-queue")
        queue_url = await sqs.create_queue(queue_name)
        
        message_body = {
            "event_type": "OrderCreated",
            "order_id": "12345",
            "symbol": "AAPL",
            "quantity": 100,
            "price": "150.25"
        }
        
        message_id = await sqs.send_message(queue_url, message_body)
        assert message_id is not None
        
        messages = await sqs.receive_messages(queue_url, max_messages=1, wait_time_seconds=5)
        assert len(messages) == 1
        
        assert messages[0]['event_type'] == "OrderCreated"
        assert messages[0]['order_id'] == "12345"
        
        await sqs.delete_message(queue_url, messages[0]['_receipt_handle'])
        
        empty_messages = await sqs.receive_messages(queue_url, max_messages=1, wait_time_seconds=1)
        assert len(empty_messages) == 0


@pytest.mark.asyncio
async def test_delete_message():
    """Test deleting a message after processing."""
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        queue_name = unique_queue_name("test-delete-queue")
        queue_url = await sqs.create_queue(queue_name)

        # Send and receive a message
        test_message = {"test": "data"}
        await sqs.send_message(queue_url, test_message)
        messages = await sqs.receive_messages(
            queue_url, 
            max_messages=1, 
            wait_time_seconds=1
        )

        assert len(messages) == 1

        # Delete the message
        receipt_handle = messages[0].get("_receipt_handle")
        assert receipt_handle is not None

        await sqs.delete_message(queue_url, receipt_handle)

        # Try to receive again - should be empty (message was deleted)
        messages = await sqs.receive_messages(
            queue_url, 
            max_messages=1,
            wait_time_seconds=1
        )
        assert len(messages) == 0


@pytest.mark.asyncio
async def test_get_queue_attributes():
    """Test retrieving queue attributes."""
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        queue_name = unique_queue_name("test-attributes-queue")
        queue_url = await sqs.create_queue(queue_name)

        # Send some messages
        for i in range(3):
            await sqs.send_message(queue_url, {"message": i})

        # Get queue attributes
        attributes = await sqs.get_queue_attributes(queue_url)

        # Verify attributes exist
        assert "ApproximateNumberOfMessages" in attributes


@pytest.mark.asyncio
async def test_queue_not_found():
    """Test handling of non-existent queue."""
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        # Try to receive from non-existent queue
        # Should return empty list, not raise an exception
        messages = await sqs.receive_messages(
            "http://localhost:4566/000000000000/non-existent-queue",
            max_messages=1,
            wait_time_seconds=1
        )
        
        # Should gracefully return empty list
        assert messages == []


@pytest.mark.asyncio
async def test_batch_send_messages():
    """Test sending multiple messages in a batch."""
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        queue_name = unique_queue_name("test-batch-queue")
        queue_url = await sqs.create_queue(queue_name)

        # Send batch of messages
        messages = [
            {"id": "1", "data": "first"},
            {"id": "2", "data": "second"},
            {"id": "3", "data": "third"},
        ]

        for msg in messages:
            await sqs.send_message(queue_url, msg)

        # Receive messages
        received = await sqs.receive_messages(queue_url, max_messages=10)

        # Verify all messages were received
        assert len(received) == 3
        
        received_ids = {msg["id"] for msg in received}
        assert received_ids == {"1", "2", "3"}