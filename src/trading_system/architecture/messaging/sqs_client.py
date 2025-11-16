"""
SQS Client Wrapper - Async interface to Amazon SQS

This module provides a high-level async interface to AWS SQS with:
- Configuration management via SQSConfig dataclass
- Message wrapper with metadata
- Context manager support for automatic cleanup
- JSON serialization/deserialization
- Error handling and retries

Usage:
    config = SQSConfig(endpoint_url="http://localhost:4566")
    async with create_sqs_client(config) as client:
        await client.create_queue("orders")
        await client.send_message(queue_url, {"order_id": 123})
"""

import json
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
from contextlib import asynccontextmanager, AsyncExitStack

from aiobotocore.session import get_session
from botocore.exceptions import ClientError


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class SQSConfig:
    """
    Configuration for SQS client.
    
    Attributes:
        endpoint_url: LocalStack endpoint or None for real AWS
        region_name: AWS region (default: us-east-1)
        aws_access_key_id: AWS credentials (use 'test' for LocalStack)
        aws_secret_access_key: AWS credentials (use 'test' for LocalStack)
        max_retries: Maximum retry attempts for operations
        visibility_timeout: Default visibility timeout in seconds
        wait_time_seconds: Long polling wait time (0-20 seconds)
    
    Examples:
        # LocalStack configuration
        config = SQSConfig(endpoint_url="http://localhost:4566")
        
        # Production AWS configuration
        config = SQSConfig(
            endpoint_url=None,  # Uses real AWS
            region_name="us-west-2",
            aws_access_key_id="AKIAIOSFODNN7EXAMPLE",
            aws_secret_access_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        )
    """
    endpoint_url: Optional[str] = "http://localhost:4566"  # LocalStack default
    region_name: str = "us-east-1"
    aws_access_key_id: str = "test"  # LocalStack doesn't validate credentials
    aws_secret_access_key: str = "test"
    max_retries: int = 3
    visibility_timeout: int = 30  # seconds
    wait_time_seconds: int = 20  # long polling (0-20)


# ============================================================================
# MESSAGE WRAPPER
# ============================================================================

@dataclass
class Message:
    """
    Represents an SQS message with metadata.
    
    Attributes:
        body: Message content (Python dict)
        attributes: Message attributes (metadata)
        message_id: SQS-assigned ID (set after sending)
        receipt_handle: Handle for deletion (set after receiving)
        received_at: Timestamp when received
    
    Usage:
        # Create message
        msg = Message(body={"order_id": 123, "status": "pending"})
        
        # Access after receiving
        print(f"Message ID: {msg.message_id}")
        print(f"Body: {msg.body}")
        
        # Delete using receipt handle
        await client.delete_message(queue_url, msg.receipt_handle)
    """
    body: Dict[str, Any]
    attributes: Dict[str, str] = field(default_factory=dict)
    message_id: Optional[str] = None
    receipt_handle: Optional[str] = None
    received_at: Optional[datetime] = None
    
    def to_json(self) -> str:
        """Serialize body to JSON string."""
        return json.dumps(self.body)
    
    @classmethod
    def from_sqs_message(cls, sqs_message: Dict) -> 'Message':
        """
        Create Message from raw SQS response.
        
        Args:
            sqs_message: Raw message dict from SQS API
            
        Returns:
            Message instance with parsed body
        """
        try:
            body = json.loads(sqs_message['Body'])
        except json.JSONDecodeError:
            # If body isn't JSON, wrap it
            body = {"raw_body": sqs_message['Body']}
        
        return cls(
            body=body,
            attributes=sqs_message.get('MessageAttributes', {}),
            message_id=sqs_message.get('MessageId'),
            receipt_handle=sqs_message.get('ReceiptHandle'),
            received_at=datetime.utcnow()
        )


# ============================================================================
# SQS CLIENT
# ============================================================================

class SQSClient:
    """
    Async wrapper around AWS SQS operations.
    
    This class provides high-level operations for SQS queues:
    - Queue management (create, delete, list)
    - Message operations (send, receive, delete)
    - Batch operations for efficiency
    - Error handling and retries
    
    The client can be used with either a SQSConfig object or legacy
    parameters for backward compatibility.
    
    Examples:
        # New way (with config)
        config = SQSConfig(endpoint_url="http://localhost:4566")
        async with SQSClient(config) as client:
            await client.create_queue("orders")
        
        # Old way (backward compatible)
        async with SQSClient(endpoint_url="http://localhost:4566") as client:
            await client.create_queue("orders")
    """
    
    def __init__(
        self,
        config: Optional[SQSConfig] = None,
        endpoint_url: Optional[str] = None,
        region_name: str = "us-east-1"
    ):
        """
        Initialize SQS client.
        
        Args:
            config: SQSConfig instance (preferred)
            endpoint_url: Direct endpoint URL (legacy, for backward compatibility)
            region_name: AWS region (legacy, for backward compatibility)
        
        Note: If config is provided, endpoint_url and region_name are ignored.
        """
        # Support both new (config) and old (direct params) initialization
        if config is not None:
            self.config = config
        else:
            # Legacy initialization for backward compatibility
            self.config = SQSConfig(
                endpoint_url=endpoint_url,
                region_name=region_name
            )
        
        self._session = get_session()
        self._client = None
        self._exit_stack = None  # For proper context manager cleanup

    async def __aenter__(self):
        """Async context manager entry point."""
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit point."""
        await self.disconnect()
    
    async def connect(self):
        """
        Establish connection to SQS.
        
        Uses AsyncExitStack to properly manage the aiobotocore client
        context manager without directly calling dunder methods.
        """
        self._exit_stack = AsyncExitStack()
        
        # Create the client context manager
        client_cm = self._session.create_client(
            "sqs",
            region_name=self.config.region_name,
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.aws_access_key_id,
            aws_secret_access_key=self.config.aws_secret_access_key,
        )
        
        # Enter the context properly using AsyncExitStack
        # This avoids calling __aenter__() directly (pylint warning)
        self._client = await self._exit_stack.enter_async_context(client_cm)
        return self
    
    async def disconnect(self):
        """
        Close SQS connection and cleanup resources.
        
        Uses AsyncExitStack.aclose() to properly exit all context managers.
        """
        if self._exit_stack:
            await self._exit_stack.aclose()
            self._exit_stack = None
        self._client = None

    async def create_queue(
        self,
        queue_name: str,
        attributes: Optional[Dict[str, str]] = None,
        fifo: bool = False,
        content_deduplication: bool = True
    ) -> str:
        """
        Create an SQS queue.
        
        Args:
            queue_name: Name of the queue
            attributes: Additional queue attributes
            fifo: Whether to create a FIFO queue
            content_deduplication: Enable content-based deduplication (FIFO only)
        
        Returns:
            Queue URL
        """
        try:
            # FIFO queues must end with .fifo
            if fifo and not queue_name.endswith('.fifo'):
                queue_name = f"{queue_name}.fifo"
            
            # Build queue attributes
            queue_attributes = attributes.copy() if attributes else {}
            
            if fifo:
                queue_attributes['FifoQueue'] = 'true'
                if content_deduplication:
                    queue_attributes['ContentBasedDeduplication'] = 'true'
            
            queue_attributes['VisibilityTimeout'] = str(self.config.visibility_timeout)
            
            params = {"QueueName": queue_name}
            if queue_attributes:
                params["Attributes"] = queue_attributes
            response = await self._client.create_queue(**params)
            queue_url = response["QueueUrl"]
            
            print(f"✓ Created queue: {queue_name}")
            print(f"  URL: {queue_url}")
            
            return queue_url
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'QueueAlreadyExists':
                # Queue exists - get its URL
                print(f"✓ Queue '{queue_name}' already exists, fetching URL")
                return await self.get_queue_url(queue_name)  # ← FIX: Return the URL!
            raise

    async def get_queue_url(self, queue_name: str) -> Optional[str]:
        """Get URL for an existing queue."""
        try:
            response = await self._client.get_queue_url(QueueName=queue_name)
            return response["QueueUrl"]
        except ClientError as e:
            if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
                return None
            raise

    async def send_message(
        self,
        queue_url: str,
        message_body: Dict[str, Any],
        message_attributes: Optional[Dict[str, Any]] = None,
        message_group_id: Optional[str] = None,
        message_deduplication_id: Optional[str] = None
    ) -> str:
        """
        Send a message to a queue.
        
        Args:
            queue_url: URL of the queue
            message_body: Message content (will be JSON serialized)
            message_attributes: Optional message attributes
            message_group_id: Required for FIFO queues
            message_deduplication_id: Optional deduplication ID for FIFO
        
        Returns:
            Message ID
        
        Examples:
            # Standard queue
            msg_id = await client.send_message(url, {"order_id": 123})
            
            # FIFO queue
            msg_id = await client.send_message(
                url,
                {"order_id": 123},
                message_group_id="orders"
            )
        """
        try:
            params = {
                "QueueUrl": queue_url,
                "MessageBody": json.dumps(message_body)
            }
            
            if message_attributes:
                params["MessageAttributes"] = message_attributes
            
            # FIFO queue parameters
            if message_group_id:
                params["MessageGroupId"] = message_group_id
            if message_deduplication_id:
                params["MessageDeduplicationId"] = message_deduplication_id

            response = await self._client.send_message(**params)
            return response["MessageId"]
            
        except ClientError as e:
            print(f"✗ Error sending message: {e}")
            raise

    async def receive_messages(
        self,
        queue_url: str,
        max_messages: int = 1,
        wait_time_seconds: Optional[int] = None,
        visibility_timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Receive messages from a queue.
        
        Args:
            queue_url: URL of the queue
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time (uses config default if None)
            visibility_timeout: Visibility timeout (uses config default if None)
        
        Returns:
            List of messages (dicts with body and _receipt_handle)
        
        Examples:
            # Short polling
            messages = await client.receive_messages(url, wait_time_seconds=0)
            
            # Long polling
            messages = await client.receive_messages(url, wait_time_seconds=20)
        """
        try:
            params = {
                "QueueUrl": queue_url,
                "MaxNumberOfMessages": max_messages,
                "WaitTimeSeconds": (
                    wait_time_seconds 
                    if wait_time_seconds is not None 
                    else self.config.wait_time_seconds
                ),
            }
            
            if visibility_timeout is not None:
                params["VisibilityTimeout"] = visibility_timeout
            else:
                params["VisibilityTimeout"] = self.config.visibility_timeout

            response = await self._client.receive_message(**params)
            messages = response.get("Messages", [])
            
            # Parse message bodies and add receipt handle for deletion
            parsed_messages = []
            for msg in messages:
                try:
                    body = json.loads(msg["Body"])
                    # Store receipt handle in the parsed message for later deletion
                    body["_receipt_handle"] = msg["ReceiptHandle"]
                    parsed_messages.append(body)
                except json.JSONDecodeError:
                    # If body is not JSON, keep it as-is
                    parsed_messages.append({
                        "Body": msg["Body"],
                        "_receipt_handle": msg["ReceiptHandle"]
                    })
            
            return parsed_messages
            
        except ClientError as e:
            # If queue doesn't exist, return empty list instead of raising
            if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
                return []
            print(f"✗ Error receiving messages: {e}")
            raise
    
    async def receive_messages_as_objects(
        self,
        queue_url: str,
        max_messages: int = 1,
        wait_time_seconds: Optional[int] = None,
        visibility_timeout: Optional[int] = None
    ) -> List[Message]:
        """
        Receive messages as Message objects.
        
        This is an alternative to receive_messages() that returns
        Message objects instead of dicts. Use this when you want
        structured message handling.
        
        Args:
            queue_url: URL of the queue
            max_messages: Maximum number of messages to receive (1-10)
            wait_time_seconds: Long polling wait time
            visibility_timeout: Visibility timeout
        
        Returns:
            List of Message objects
        """
        try:
            params = {
                "QueueUrl": queue_url,
                "MaxNumberOfMessages": max_messages,
                "WaitTimeSeconds": (
                    wait_time_seconds 
                    if wait_time_seconds is not None 
                    else self.config.wait_time_seconds
                ),
            }
            
            if visibility_timeout is not None:
                params["VisibilityTimeout"] = visibility_timeout

            response = await self._client.receive_message(**params)
            raw_messages = response.get("Messages", [])
            
            # Convert to Message objects
            return [Message.from_sqs_message(msg) for msg in raw_messages]
            
        except ClientError as e:
            if e.response["Error"]["Code"] == "AWS.SimpleQueueService.NonExistentQueue":
                return []
            raise

    async def delete_message(self, queue_url: str, receipt_handle: str) -> None:
        """
        Delete a message from the queue.
        
        Args:
            queue_url: URL of the queue
            receipt_handle: Receipt handle from received message
        
        Examples:
            messages = await client.receive_messages(url)
            for msg in messages:
                # Process message...
                await client.delete_message(url, msg["_receipt_handle"])
        """
        try:
            await self._client.delete_message(
                QueueUrl=queue_url,
                ReceiptHandle=receipt_handle
            )
        except ClientError as e:
            print(f"✗ Error deleting message: {e}")
            raise

    async def get_queue_attributes(
        self,
        queue_url: str,
        attribute_names: Optional[List[str]] = None
    ) -> Dict[str, str]:
        """
        Get queue metadata and statistics.
        
        Args:
            queue_url: URL of the queue
            attribute_names: List of attribute names or ["All"]
        
        Returns:
            Dictionary of queue attributes
        
        Useful Attributes:
            - ApproximateNumberOfMessages: Messages ready
            - ApproximateNumberOfMessagesNotVisible: Being processed
            - ApproximateNumberOfMessagesDelayed: Delayed messages
        """
        try:
            if attribute_names is None:
                attribute_names = ["All"]

            response = await self._client.get_queue_attributes(
                QueueUrl=queue_url,
                AttributeNames=attribute_names
            )
            
            return response.get("Attributes", {})
            
        except ClientError as e:
            print(f"✗ Error getting queue attributes: {e}")
            raise

    async def list_queues(self, queue_name_prefix: str = "") -> List[str]:
        """
        List all queues.
        
        Args:
            queue_name_prefix: Filter queues by name prefix
        
        Returns:
            List of queue URLs
        """
        try:
            params = {}
            if queue_name_prefix:
                params["QueueNamePrefix"] = queue_name_prefix

            response = await self._client.list_queues(**params)
            return response.get("QueueUrls", [])
            
        except ClientError as e:
            print(f"✗ Error listing queues: {e}")
            raise
    
    async def delete_queue(self, queue_url: str) -> None:
        """
        Delete a queue.
        
        Args:
            queue_url: URL of the queue to delete
        
        Warning:
            This permanently deletes the queue and all messages!
        """
        try:
            await self._client.delete_queue(QueueUrl=queue_url)
            print(f"✓ Deleted queue: {queue_url}")
        except ClientError as e:
            print(f"✗ Error deleting queue: {e}")
            raise
    
    async def purge_queue(self, queue_url: str) -> None:
        """
        Delete all messages from a queue.
        
        Args:
            queue_url: URL of the queue to purge
        
        Warning:
            This permanently deletes all messages in the queue!
        """
        try:
            await self._client.purge_queue(QueueUrl=queue_url)
            print(f"✓ Purged queue: {queue_url}")
        except ClientError as e:
            print(f"✗ Error purging queue: {e}")
            raise


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

@asynccontextmanager
async def create_sqs_client(config: Optional[SQSConfig] = None):
    """
    Create SQS client as async context manager.
    
    This is the preferred way to create an SQS client as it handles
    connection and cleanup automatically.
    
    Args:
        config: Optional SQSConfig (uses defaults if None)
    
    Yields:
        Connected SQSClient instance
    
    Examples:
        # With custom config
        config = SQSConfig(endpoint_url="http://localhost:4566")
        async with create_sqs_client(config) as client:
            await client.create_queue("orders")
            await client.send_message(url, {"order_id": 123})
        
        # With defaults (connects to LocalStack)
        async with create_sqs_client() as client:
            await client.create_queue("orders")
    """
    config = config or SQSConfig()
    client = SQSClient(config)
    
    try:
        await client.connect()
        yield client
    finally:
        await client.disconnect()


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def main():
        """Example demonstrating SQS client usage."""
        
        # Create client with LocalStack configuration
        config = SQSConfig(
            endpoint_url="http://localhost:4566",
            region_name="us-east-1",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        
        async with create_sqs_client(config) as client:
            # Create a FIFO queue
            queue_url = await client.create_queue("example-orders", fifo=True)
            
            # Send a message
            message_id = await client.send_message(
                queue_url,
                {
                    "order_id": "ORD-001",
                    "symbol": "AAPL",
                    "quantity": 100,
                    "price": 150.25,
                },
                message_group_id="orders"  # Required for FIFO
            )
            print(f"Sent message: {message_id}")
            
            # Receive messages
            messages = await client.receive_messages(queue_url, wait_time_seconds=5)
            for msg in messages:
                print(f"Received: {msg}")
                
                # Delete after processing
                await client.delete_message(queue_url, msg["_receipt_handle"])
            
            # Get queue stats
            attrs = await client.get_queue_attributes(queue_url)
            print(f"Queue stats: {attrs}")
            
            # Cleanup
            await client.delete_queue(queue_url)
    
    # Run example
    asyncio.run(main())