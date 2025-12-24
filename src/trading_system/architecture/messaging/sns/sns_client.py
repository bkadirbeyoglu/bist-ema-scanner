"""
Async SNS Client using aioboto3.

aioboto3 provides native async support for AWS services, making our code
simpler than manually wrapping synchronous boto3 with run_in_executor.
"""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any
from typing import AsyncIterator
from typing import Final

import aioboto3
from botocore.config import Config

from trading_system.architecture.messaging.sns.constants import AWS_ENDPOINT_URL
from trading_system.architecture.messaging.sns.constants import AWS_REGION


# =============================================================================
# Configuration
# =============================================================================

MAX_TOPICS_PER_REQUEST: Final[int] = 100


@dataclass(frozen=True)
class SNSConfig:
    """
    Configuration for SNS client.
    
    frozen=True makes this immutable - safe to share across async tasks.
    """

    endpoint_url: str | None = AWS_ENDPOINT_URL  # None = use real AWS
    region: str = AWS_REGION
    connect_timeout: int = 5
    read_timeout: int = 30


# =============================================================================
# SNS Client
# =============================================================================

class SNSClient:
    """
    Async SNS client using aioboto3.
    
    aioboto3 wraps boto3 to provide native async/await support.
    All AWS API calls are non-blocking.
    
    Example:
        async with get_sns_client() as client:
            topic_arn = await client.create_topic("my-topic")
            await client.publish(topic_arn, {"key": "value"})
    """

    def __init__(self, client: Any, config: SNSConfig) -> None:
        """
        Initialize with an aioboto3 SNS client.
        
        Note: Don't instantiate directly - use get_sns_client() context manager.
        """
        self._client = client
        self._config = config

    # -------------------------------------------------------------------------
    # Topic Management
    # -------------------------------------------------------------------------

    async def create_topic(self, name: str) -> str:
        """
        Create an SNS topic.
        
        Returns:
            Topic ARN (Amazon Resource Name) - unique identifier like:
            arn:aws:sns:us-east-1:123456789:price-updates
            
        Note:
            create_topic is idempotent - calling it for an existing topic
            just returns the existing ARN (doesn't create a duplicate).
        """
        response = await self._client.create_topic(Name=name)
        return response["TopicArn"]

    async def delete_topic(self, topic_arn: str) -> None:
        """Delete an SNS topic. Warning: also removes all subscriptions."""
        await self._client.delete_topic(TopicArn=topic_arn)

    async def list_topics(self) -> list[str]:
        """List all SNS topic ARNs."""
        response = await self._client.list_topics()
        return [topic["TopicArn"] for topic in response.get("Topics", [])]

    async def get_topic_arn(self, topic_name: str) -> str | None:
        """
        Get the ARN for a topic by name.
        
        ARNs end with the topic name, so we can match by suffix.
        Example: arn:aws:sns:us-east-1:000000000000:price-updates
                                                    ^^^^^^^^^^^^^^
        """
        topics = await self.list_topics()
        for arn in topics:
            if arn.endswith(f":{topic_name}"):
                return arn
        return None

    # -------------------------------------------------------------------------
    # Publishing
    # -------------------------------------------------------------------------

    async def publish(
        self,
        topic_arn: str,
        message: dict[str, Any],
        message_attributes: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Publish a message to an SNS topic.
        
        Args:
            topic_arn: The topic ARN to publish to
            message: Message payload (will be JSON serialized)
            message_attributes: Optional attributes for filtering
            
        Returns:
            SNS publish response containing MessageId
        """
        publish_kwargs: dict[str, Any] = {
            "TopicArn": topic_arn,
            "Message": json.dumps(message, default=str),
        }

        if message_attributes:
            publish_kwargs["MessageAttributes"] = message_attributes

        return await self._client.publish(**publish_kwargs)

    # -------------------------------------------------------------------------
    # Subscriptions
    # -------------------------------------------------------------------------

    async def subscribe_sqs(
        self,
        topic_arn: str,
        queue_arn: str,
        filter_policy: dict[str, Any] | None = None,
    ) -> str:
        """
        Subscribe an SQS queue to an SNS topic.
        
        This is the core of the fan-out pattern: when a message is
        published to the topic, SNS delivers it to all subscribed queues.
        """
        response = await self._client.subscribe(
            TopicArn=topic_arn,
            Protocol="sqs",
            Endpoint=queue_arn,
        )

        subscription_arn = response["SubscriptionArn"]

        # Apply filter policy if provided
        if filter_policy and subscription_arn != "pending confirmation":
            await self.set_subscription_filter(subscription_arn, filter_policy)

        return subscription_arn

    async def set_subscription_filter(
        self,
        subscription_arn: str,
        filter_policy: dict[str, Any],
    ) -> None:
        """Set a filter policy on a subscription."""
        await self._client.set_subscription_attributes(
            SubscriptionArn=subscription_arn,
            AttributeName="FilterPolicy",
            AttributeValue=json.dumps(filter_policy),
        )

    async def unsubscribe(self, subscription_arn: str) -> None:
        """Remove a subscription."""
        await self._client.unsubscribe(SubscriptionArn=subscription_arn)

    async def list_subscriptions(self, topic_arn: str) -> list[dict[str, Any]]:
        """List all subscriptions for a topic."""
        response = await self._client.list_subscriptions_by_topic(
            TopicArn=topic_arn
        )
        return response.get("Subscriptions", [])


# =============================================================================
# Context Manager for Client Lifecycle
# =============================================================================

@asynccontextmanager
async def get_sns_client(
    config: SNSConfig | None = None,
) -> AsyncIterator[SNSClient]:
    """
    Async context manager for SNS client.
    
    Creates the aioboto3 session and SNS client, ensuring proper cleanup.
    
    Usage:
        async with get_sns_client() as client:
            await client.create_topic("my-topic")
        # Client automatically closed here
    """
    config = config or SNSConfig()
    
    # aioboto3.Session() is similar to boto3.Session()
    session = aioboto3.Session()
    
    # Configure timeouts and retries
    boto_config = Config(
        connect_timeout=config.connect_timeout,
        read_timeout=config.read_timeout,
        retries={"max_attempts": 3, "mode": "standard"},
    )
    
    # Create async client - note the 'async with'
    async with session.client(
        "sns",
        endpoint_url=config.endpoint_url,
        region_name=config.region,
        config=boto_config,
        aws_access_key_id="test",      # LocalStack accepts any credentials
        aws_secret_access_key="test",
    ) as client:
        yield SNSClient(client, config)