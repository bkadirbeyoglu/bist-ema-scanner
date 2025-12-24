"""
Unit tests for SNS Publisher.

Tests the SNSPublisher class which handles publishing events to SNS topics.
We mock the SNS client to test publishing logic in isolation.
"""

from datetime import datetime
from datetime import timezone
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from trading_system.architecture.messaging.sns.sns_publisher import SNSPublisher
from trading_system.architecture.messaging.sns.sns_publisher import PublishResult
from trading_system.shared_kernel.sns_events import PriceUpdatedEvent


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def mock_sns_client() -> AsyncMock:
    """Create a mock SNS client for testing."""
    client = AsyncMock()
    # Mock the publish response
    client.publish.return_value = {
        "MessageId": "test-message-id-12345",
        "SequenceNumber": None,
    }
    return client


@pytest.fixture
def publisher(mock_sns_client: AsyncMock) -> SNSPublisher:
    """Create a publisher with mocked client."""
    return SNSPublisher(
        sns_client=mock_sns_client,
        topic_arn="arn:aws:sns:us-east-1:000000000000:price-updates",
    )


@pytest.fixture
def sample_price_event() -> PriceUpdatedEvent:
    """Create a sample price event for testing."""
    return PriceUpdatedEvent(
        symbol="AAPL",
        price=Decimal("178.50"),
        timestamp=datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        source="market-data-service",
    )


# =============================================================================
# Test Cases
# =============================================================================

class TestSNSPublisher:
    """Tests for SNSPublisher."""

    @pytest.mark.asyncio
    async def test_publish_event_calls_sns_with_correct_payload(
        self,
        publisher: SNSPublisher,
        mock_sns_client: AsyncMock,
        sample_price_event: PriceUpdatedEvent,
    ) -> None:
        """Verify that publishing an event calls SNS with the right message."""
        # Act
        result = await publisher.publish(sample_price_event)

        # Assert - SNS was called
        mock_sns_client.publish.assert_called_once()

        # Assert - Check the call arguments
        # Note: SNSPublisher calls SNSClient.publish() with lowercase params
        # SNSClient internally converts to AWS PascalCase format
        call_kwargs = mock_sns_client.publish.call_args.kwargs
        assert call_kwargs["topic_arn"] == publisher.topic_arn

        # Assert - Message body contains event data
        message_body = call_kwargs["message"]
        assert message_body["symbol"] == "AAPL"
        assert message_body["price"] == "178.50"

    @pytest.mark.asyncio
    async def test_publish_event_returns_message_id(
        self,
        publisher: SNSPublisher,
        sample_price_event: PriceUpdatedEvent,
    ) -> None:
        """Verify that publish returns the SNS message ID."""
        # Act
        result = await publisher.publish(sample_price_event)

        # Assert
        assert result.success is True
        assert result.message_id == "test-message-id-12345"

    @pytest.mark.asyncio
    async def test_publish_includes_message_attributes_for_filtering(
        self,
        publisher: SNSPublisher,
        mock_sns_client: AsyncMock,
        sample_price_event: PriceUpdatedEvent,
    ) -> None:
        """
        Verify that message attributes are included for SNS filtering.
        
        Message attributes allow subscribers to filter which messages
        they receive based on event properties (e.g., symbol, event_type).
        """
        # Act
        await publisher.publish(sample_price_event)

        # Assert - Message attributes were included
        call_kwargs = mock_sns_client.publish.call_args.kwargs
        attributes = call_kwargs.get("message_attributes", {})

        # Check symbol attribute (for filtering by stock)
        assert "symbol" in attributes
        assert attributes["symbol"]["DataType"] == "String"
        assert attributes["symbol"]["StringValue"] == "AAPL"

        # Check event_type attribute (for filtering by event type)
        assert "event_type" in attributes
        assert attributes["event_type"]["StringValue"] == "PriceUpdatedEvent"

    @pytest.mark.asyncio
    async def test_publish_handles_sns_error_gracefully(
        self,
        publisher: SNSPublisher,
        mock_sns_client: AsyncMock,
        sample_price_event: PriceUpdatedEvent,
    ) -> None:
        """Verify that SNS errors are caught and returned in result."""
        # Arrange - Make SNS raise an error
        mock_sns_client.publish.side_effect = Exception("SNS unavailable")

        # Act
        result = await publisher.publish(sample_price_event)

        # Assert - Error is captured, not raised
        assert result.success is False
        assert "SNS unavailable" in result.error

    @pytest.mark.asyncio
    async def test_publish_with_custom_attributes(
        self,
        publisher: SNSPublisher,
        mock_sns_client: AsyncMock,
        sample_price_event: PriceUpdatedEvent,
    ) -> None:
        """Verify that custom attributes can be added to messages."""
        # Arrange
        custom_attrs = {
            "priority": "high",
            "source_region": "us-east-1",
        }

        # Act
        await publisher.publish(
            event=sample_price_event,
            extra_attributes=custom_attrs,
        )

        # Assert
        call_kwargs = mock_sns_client.publish.call_args.kwargs
        attributes = call_kwargs.get("message_attributes", {})

        assert attributes["priority"]["StringValue"] == "high"
        assert attributes["source_region"]["StringValue"] == "us-east-1"


class TestPublishResult:
    """Tests for PublishResult dataclass."""

    def test_success_result_creation(self) -> None:
        """Verify successful result creation."""
        result = PublishResult(
            success=True,
            message_id="msg-123",
            topic_arn="arn:aws:sns:us-east-1:000000000000:test",
        )

        assert result.success is True
        assert result.message_id == "msg-123"
        assert result.error is None

    def test_failure_result_creation(self) -> None:
        """Verify failure result creation."""
        result = PublishResult(
            success=False,
            message_id=None,
            topic_arn="arn:aws:sns:us-east-1:000000000000:test",
            error="Connection timeout",
        )

        assert result.success is False
        assert result.message_id is None
        assert result.error == "Connection timeout"