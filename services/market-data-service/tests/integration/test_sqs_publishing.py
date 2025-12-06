"""
Integration Tests for SQS Publishing.

Tests the full flow from price engine to SQS queue.
Requires LocalStack running.

RUN: docker compose up localstack -d
     poetry run pytest tests/integration/ -v
"""

import pytest
import aioboto3
from decimal import Decimal
from datetime import datetime
import json

from market_data_service.domain.entities import Quote, PriceSource
from market_data_service.domain.events import PriceUpdatedEvent
from market_data_service.infrastructure.publishers.sqs_publisher import SQSPublisher
from market_data_service.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Test settings pointing to LocalStack."""
    return Settings(
        service_name="test-market-data",
        environment="development",
        aws_region="us-east-1",
        aws_endpoint_url="http://localhost:4566",
        sqs_price_queue_name="test-market-data-prices"
    )


@pytest.fixture
def sample_event() -> PriceUpdatedEvent:
    """Sample price event for testing."""
    return PriceUpdatedEvent(
        symbol="AAPL",
        price=Decimal("150.25"),
        bid=Decimal("150.20"),
        ask=Decimal("150.30"),
        volume=1000000,
        source="mock"
    )


class TestSQSPublisher:
    """Integration tests for SQS Publisher."""
    
    @pytest.mark.asyncio
    async def test_publisher_connects_and_creates_queue(self, settings: Settings):
        """
        Test: Publisher creates queue on connect
        
        Verifies:
        - Connect completes successfully
        - Queue is created in LocalStack
        """
        publisher = SQSPublisher(settings)
        
        await publisher.connect()
        
        # Verify queue exists
        session = aioboto3.Session()
        async with session.client(
            "sqs",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url
        ) as client:
            response = await client.list_queues(
                QueueNamePrefix=settings.sqs_price_queue_name
            )
            queue_urls = response.get("QueueUrls", [])
            assert len(queue_urls) >= 1
        
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_publisher_sends_message(
        self,
        settings: Settings,
        sample_event: PriceUpdatedEvent
    ):
        """
        Test: Publisher sends message to SQS
        
        Verifies:
        - Message is published successfully
        - Message can be received from queue
        - Message content matches event
        """
        publisher = SQSPublisher(settings)
        await publisher.connect()
        
        # Publish event
        await publisher.publish(sample_event)
        
        # Verify message in queue
        session = aioboto3.Session()
        async with session.client(
            "sqs",
            region_name=settings.aws_region,
            endpoint_url=settings.aws_endpoint_url
        ) as client:
            # Get queue URL
            response = await client.get_queue_url(
                QueueName=settings.sqs_price_queue_name
            )
            queue_url = response["QueueUrl"]
            
            # Receive message
            response = await client.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=5,
                MessageAttributeNames=["All"]
            )
            
            messages = response.get("Messages", [])
            assert len(messages) == 1
            
            message = messages[0]
            body = json.loads(message["Body"])
            
            assert body["symbol"] == "AAPL"
            assert body["price"] == "150.25"
            assert body["event_type"] == "PriceUpdatedEvent"
            
            # Check message attributes
            attrs = message.get("MessageAttributes", {})
            assert attrs["symbol"]["StringValue"] == "AAPL"
            assert attrs["event_type"]["StringValue"] == "PriceUpdatedEvent"
            
            # Clean up - delete message
            await client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=message["ReceiptHandle"]
            )
        
        await publisher.disconnect()
    
    @pytest.mark.asyncio
    async def test_publisher_get_queue_stats(self, settings: Settings):
        """
        Test: Publisher can retrieve queue statistics
        
        Verifies:
        - get_queue_stats returns metrics
        - Metrics include expected attributes
        """
        publisher = SQSPublisher(settings)
        await publisher.connect()
        
        stats = await publisher.get_queue_stats()
        
        assert "ApproximateNumberOfMessages" in stats
        assert "ApproximateNumberOfMessagesNotVisible" in stats
        
        await publisher.disconnect()