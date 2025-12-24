"""
SNS Publisher for event distribution.

Publishes domain events to SNS topics with proper message attributes
for filtering. This is the "publish" side of the pub/sub pattern.
"""

import json
import logging
from dataclasses import dataclass
from dataclasses import field
from datetime import datetime
from datetime import timezone
from decimal import Decimal
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from trading_system.architecture.messaging.sns.sns_client import SNSClient


logger = logging.getLogger(__name__)


# =============================================================================
# Result Types
# =============================================================================

@dataclass
class PublishResult:
    """
    Result of a publish operation.
    
    We use a result type instead of exceptions because publishing
    failures are expected in distributed systems (network issues,
    throttling, etc.) and should be handled gracefully.
    """

    success: bool
    message_id: str | None
    topic_arn: str
    error: str | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


# =============================================================================
# Event Protocol
# =============================================================================

@runtime_checkable
class Publishable(Protocol):
    """
    Protocol for events that can be published to SNS.
    
    Any event class implementing these methods can be published.
    This uses Python's structural typing (duck typing with type hints).
    """

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dictionary for serialization."""
        ...

    @property
    def event_type(self) -> str:
        """Return the event type name (e.g., 'PriceUpdatedEvent')."""
        ...


# =============================================================================
# SNS Publisher
# =============================================================================

class SNSPublisher:
    """
    Publishes events to an SNS topic.
    
    This class handles:
    - Serializing events to JSON
    - Adding message attributes for filtering
    - Error handling and result reporting
    
    Example:
        publisher = SNSPublisher(sns_client, topic_arn)
        result = await publisher.publish(price_event)
        if result.success:
            print(f"Published: {result.message_id}")
    """

    def __init__(
        self,
        sns_client: SNSClient,
        topic_arn: str,
    ) -> None:
        """
        Initialize the publisher.
        
        Args:
            sns_client: The SNS client for AWS operations
            topic_arn: The ARN of the topic to publish to
        """
        self._client = sns_client
        self._topic_arn = topic_arn
        self._publish_count = 0

    @property
    def topic_arn(self) -> str:
        """Get the topic ARN."""
        return self._topic_arn

    @property
    def publish_count(self) -> int:
        """Get the number of successful publishes."""
        return self._publish_count
    
    async def publish(
        self,
        event: Publishable,
        extra_attributes: dict[str, str] | None = None,
    ) -> PublishResult:
        """
        Publish an event to the SNS topic.
        
        Args:
            event: The event to publish (must implement Publishable protocol)
            extra_attributes: Additional message attributes for filtering
            
        Returns:
            PublishResult indicating success/failure
        """
        try:
            # Convert event to dictionary
            message_body = event.to_dict()

            # Build message attributes for SNS filtering
            message_attributes = self._build_attributes(event, extra_attributes)

            # Publish to SNS
            response = await self._client.publish(
                topic_arn=self._topic_arn,
                message=message_body,
                message_attributes=message_attributes,
            )

            self._publish_count += 1

            logger.debug(
                "Published event to SNS",
                extra={
                    "topic": self._topic_arn,
                    "event_type": event.event_type,
                    "message_id": response.get("MessageId"),
                },
            )

            return PublishResult(
                success=True,
                message_id=response.get("MessageId"),
                topic_arn=self._topic_arn,
            )

        except Exception as e:
            logger.error(
                f"Failed to publish event: {e}",
                extra={
                    "topic": self._topic_arn,
                    "event_type": event.event_type,
                    "error": str(e),
                },
            )

            return PublishResult(
                success=False,
                message_id=None,
                topic_arn=self._topic_arn,
                error=str(e),
            )

    def _build_attributes(
        self,
        event: Publishable,
        extra_attributes: dict[str, str] | None = None,
    ) -> dict[str, dict[str, str]]:
        """
        Build SNS message attributes from event.
        
        Message attributes are key-value pairs that SNS can use
        for filtering. They're separate from the message body.
        
        SNS attribute format:
        {
            "attribute_name": {
                "DataType": "String",
                "StringValue": "attribute_value"
            }
        }
        """
        attributes: dict[str, dict[str, str]] = {}

        # Add event type (for filtering by event class)
        attributes["event_type"] = {
            "DataType": "String",
            "StringValue": event.event_type,
        }

        # Add event-specific attributes
        event_dict = event.to_dict()

        # Add symbol if present (common in trading events)
        if "symbol" in event_dict:
            attributes["symbol"] = {
                "DataType": "String",
                "StringValue": str(event_dict["symbol"]),
            }

        # Add price_change_pct if present (for threshold filtering)
        if "price_change_pct" in event_dict:
            attributes["price_change_pct"] = {
                "DataType": "Number",
                "StringValue": str(event_dict["price_change_pct"]),
            }

        # Add custom attributes
        if extra_attributes:
            for key, value in extra_attributes.items():
                attributes[key] = {
                    "DataType": "String",
                    "StringValue": str(value),
                }

        return attributes


# =============================================================================
# Multi-Topic Publisher
# =============================================================================

class MultiTopicPublisher:
    """
    Publishes events to multiple SNS topics.
    
    Useful when an event should fan-out to different topic groups.
    For example, a trade execution might go to both "order-events"
    and "notification-events".
    """

    def __init__(
        self,
        sns_client: SNSClient,
        topic_arns: list[str],
    ) -> None:
        """
        Initialize with multiple topics.
        
        Args:
            sns_client: The SNS client
            topic_arns: List of topic ARNs to publish to
        """
        self._publishers = [
            SNSPublisher(sns_client, arn) for arn in topic_arns
        ]

    async def publish(
        self,
        event: Publishable,
        extra_attributes: dict[str, str] | None = None,
    ) -> list[PublishResult]:
        """
        Publish to all topics.
        
        Returns:
            List of results, one per topic
        """
        results = []
        for publisher in self._publishers:
            result = await publisher.publish(event, extra_attributes)
            results.append(result)
        return results