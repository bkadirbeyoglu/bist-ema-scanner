import asyncio
import json
from trading_system.architecture.messaging.sqs_client import SQSClient

async def test_sqs():
    """Quick manual test of SQS client."""
    print("\n🧪 Testing SQS Client with LocalStack...\n")
    
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        # Create queue
        print("1️⃣  Creating queue...")
        queue_url = await sqs.create_queue("test-manual-queue")
        print(f"   ✅ Queue created: {queue_url}\n")
        
        # Send message
        print("2️⃣  Sending message...")
        msg_body = {
            "event_type": "OrderCreated",
            "order_id": "TEST-123",
            "symbol": "AAPL",
            "quantity": 100
        }
        msg_id = await sqs.send_message("test-manual-queue", msg_body)
        print(f"   ✅ Message sent: {msg_id}\n")
        
        # Receive message
        print("3️⃣  Receiving message...")
        messages = await sqs.receive_messages("test-manual-queue", wait_time_seconds=2)
        if messages:
            received = json.loads(messages[0]['Body'])
            print(f"   ✅ Message received:")
            print(f"      Event: {received['event_type']}")
            print(f"      Order: {received['order_id']}\n")
            
            # Delete message
            print("4️⃣  Deleting message...")
            await sqs.delete_message("test-manual-queue", messages[0]['ReceiptHandle'])
            print(f"   ✅ Message deleted\n")
        
        print("✅ SQS Client test complete!\n")

if __name__ == "__main__":
    asyncio.run(test_sqs())