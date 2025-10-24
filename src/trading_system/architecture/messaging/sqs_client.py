"""
SQS Client Wrapper - Async interface to Amazon SQS
"""

import json
from typing import Any, Dict, List, Optional

from aiobotocore.session import get_session
from botocore.exceptions import ClientError


class SQSClient:
    """Async wrapper around AWS SQS operations."""
    
    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        region_name: str = "us-east-1"
    ):
        self._session = get_session()
        self._endpoint_url = endpoint_url
        self._region_name = region_name
        self._client = None

    async def __aenter__(self):
        """Async context manager entry point."""
        self._client = await self._session.create_client(
            "sqs",
            region_name=self._region_name,
            endpoint_url=self._endpoint_url,
        ).__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit point."""
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

    async def create_queue(
        self,
        queue_name: str,
        attributes: Optional[Dict[str, str]] = None
    ) -> str:
        """Create an SQS queue."""
        try:
            params = {"QueueName": queue_name}
            if attributes:
                params["Attributes"] = attributes

            response = await self._client.create_queue(**params)
            queue_url = response["QueueUrl"]
            
            print(f"✓ Created queue: {queue_name}")
            print(f"  URL: {queue_url}")
            
            return queue_url
        except ClientError as e:
            print(f"✗ Error creating queue {queue_name}: {e}")
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
        message_attributes: Optional[Dict[str, Any]] = None
    ) -> str:
        """Send a message to a queue."""
        try:
            params = {
                "QueueUrl": queue_url,
                "MessageBody": json.dumps(message_body)
            }
            
            if message_attributes:
                params["MessageAttributes"] = message_attributes

            response = await self._client.send_message(**params)
            return response["MessageId"]
            
        except ClientError as e:
            print(f"✗ Error sending message: {e}")
            raise

    async def receive_messages(
        self,
        queue_url: str,
        max_messages: int = 1,
        wait_time_seconds: int = 0,
        visibility_timeout: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """Receive messages from a queue."""
        try:
            params = {
                "QueueUrl": queue_url,
                "MaxNumberOfMessages": max_messages,
                "WaitTimeSeconds": wait_time_seconds,
            }
            
            if visibility_timeout is not None:
                params["VisibilityTimeout"] = visibility_timeout

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

    async def delete_message(self, queue_url: str, receipt_handle: str) -> None:
        """Delete a message from the queue."""
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
        """Get queue metadata and statistics."""
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
        """List all queues."""
        try:
            params = {}
            if queue_name_prefix:
                params["QueueNamePrefix"] = queue_name_prefix

            response = await self._client.list_queues(**params)
            return response.get("QueueUrls", [])
            
        except ClientError as e:
            print(f"✗ Error listing queues: {e}")
            raise