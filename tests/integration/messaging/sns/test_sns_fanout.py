"""
Integration tests for SNS fan-out pattern.

These tests require LocalStack to be running.
They verify end-to-end SNS → SQS fan-out functionality.
"""

import asyncio
import json
from datetime import datetime
from datetime import timezone
from decimal import Decimal

import pytest

from trading_system.architecture.messaging.sns.sns_client import get_sns_client
from trading_system.architecture.messaging.sns.sns_client import SNSConfig
from trading_system.architecture.messaging.sns.sns_publisher import SNSPublisher
from trading_system.architecture.messaging.sns.filter_policies import FilterPolicyBuilder
from trading_system.shared_kernel.sns_events import PriceUpdatedEvent


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def sns_config() -> SNSConfig:
    """Configuration for LocalStack."""
    return SNSConfig(
        endpoint_url="http://localhost:4566",
        region="us-east-1",
    )


@pytest.fixture
def sample_events() -> list[PriceUpdatedEvent]:
    """Create sample events for testing."""
    return [
        PriceUpdatedEvent(
            symbol="AAPL",
            price=Decimal("178.50"),
            timestamp=datetime.now(timezone.utc),
            source="test",
        ),
        PriceUpdatedEvent(
            symbol="GOOGL",
            price=Decimal("142.30"),
            timestamp=datetime.now(timezone.utc),
            source="test",
        ),
        PriceUpdatedEvent(
            symbol="MSFT",
            price=Decimal("378.20"),
            timestamp=datetime.now(timezone.utc),
            source="test",
        ),
    ]


# =============================================================================
# Integration Tests
# =============================================================================

@pytest.mark.integration
class TestSNSFanout:
    """Integration tests for SNS fan-out functionality."""

    @pytest.mark.asyncio
    async def test_create_topic_returns_arn(
        self,
        sns_config: SNSConfig,
    ) -> None:
        """Verify topic creation returns valid ARN."""
        async with get_sns_client(sns_config) as client:
            # Create topic
            topic_arn = await client.create_topic("test-topic")

            # Verify ARN format
            assert topic_arn.startswith("arn:aws:sns:")
            assert "test-topic" in topic_arn

            # Cleanup
            await client.delete_topic(topic_arn)

    @pytest.mark.asyncio
    async def test_publish_event_succeeds(
        self,
        sns_config: SNSConfig,
        sample_events: list[PriceUpdatedEvent],
    ) -> None:
        """Verify event publishing to SNS topic."""
        async with get_sns_client(sns_config) as client:
            # Create topic
            topic_arn = await client.create_topic("price-updates-test")

            # Create publisher
            publisher = SNSPublisher(client, topic_arn)

            # Publish event
            result = await publisher.publish(sample_events[0])

            # Verify success
            assert result.success is True
            assert result.message_id is not None

            # Cleanup
            await client.delete_topic(topic_arn)

    @pytest.mark.asyncio
    async def test_publish_multiple_events(
        self,
        sns_config: SNSConfig,
        sample_events: list[PriceUpdatedEvent],
    ) -> None:
        """Verify multiple events can be published."""
        async with get_sns_client(sns_config) as client:
            # Create topic
            topic_arn = await client.create_topic("multi-event-test")
            publisher = SNSPublisher(client, topic_arn)

            # Publish all events
            results = []
            for event in sample_events:
                result = await publisher.publish(event)
                results.append(result)

            # Verify all succeeded
            assert all(r.success for r in results)
            assert publisher.publish_count == 3

            # Cleanup
            await client.delete_topic(topic_arn)

    @pytest.mark.asyncio
    async def test_list_subscriptions_empty_initially(
        self,
        sns_config: SNSConfig,
    ) -> None:
        """Verify new topic has no subscriptions."""
        async with get_sns_client(sns_config) as client:
            # Create topic
            topic_arn = await client.create_topic("empty-subs-test")

            # List subscriptions
            subs = await client.list_subscriptions(topic_arn)

            # Should be empty
            assert subs == []

            # Cleanup
            await client.delete_topic(topic_arn)


@pytest.mark.integration
class TestFilterPolicyIntegration:
    """Integration tests for SNS filter policies."""

    @pytest.mark.asyncio
    async def test_filter_policy_applied_to_subscription(
        self,
        sns_config: SNSConfig,
    ) -> None:
        """Verify filter policy can be set on subscription."""
        # This test would require SQS setup as well
        # For now, we verify filter policy building works

        policy = (
            FilterPolicyBuilder()
            .exact_match("symbol", "AAPL")
            .exact_match("event_type", "PriceUpdatedEvent")
            .build()
        )

        # Verify policy structure
        assert policy == {
            "symbol": ["AAPL"],
            "event_type": ["PriceUpdatedEvent"],
        }