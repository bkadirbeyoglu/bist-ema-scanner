#!/usr/bin/env python3
"""
Demo script for Notification Service.

Shows the notification service handling order events and generating
notifications across different channels.

Run from the notification-service directory:
    poetry run python demo.py
"""

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from notification_service.application.notification_service import NotificationApplicationService
from notification_service.application.templates import TemplateRegistry
from notification_service.domain.value_objects import NotificationChannel
from notification_service.infrastructure.notification_repository import InMemoryNotificationRepository


async def main() -> None:
    """Run the notification demo."""
    print("=" * 70)
    print("NOTIFICATION SERVICE DEMO")
    print("=" * 70)
    print()
    
    # Create service
    repository = InMemoryNotificationRepository()
    service = NotificationApplicationService(
        repository=repository,
        template_registry=TemplateRegistry(),
    )
    
    # Simulate order events (as they would arrive from SNS/SQS)
    events = [
        {
            "event_type": "OrderCreatedEvent",
            "event_id": "evt_001",
            "order_id": "order_demo_001",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "order_type": "limit",
            "limit_price": 150.00,
        },
        {
            "event_type": "OrderFilledEvent",
            "event_id": "evt_002",
            "order_id": "order_demo_001",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 100,
            "fill_price": 149.85,
            "filled_at": "2025-01-15T10:30:00Z",
        },
        {
            "event_type": "OrderCancelledEvent",
            "event_id": "evt_003",
            "order_id": "order_demo_002",
            "symbol": "GOOGL",
            "reason": "Market closed",
        },
    ]
    
    print("Processing order events...")
    print("-" * 70)
    
    for event in events:
        print(f"\n📨 Event: {event['event_type']}")
        print(f"   Order: {event['order_id']} - {event.get('symbol', 'N/A')}")
        print()
        
        channels = [NotificationChannel.EMAIL, NotificationChannel.SLACK]
        
        try:
            results = await service.handle_order_event(
                event_data=event,
                channels=channels,
                recipient_address="trader@example.com",
                recipient_name="Demo Trader",
            )
            
            for result in results:
                print(f"   {result.channel_log}")
                print()
        
        except ValueError as e:
            print(f"   ⚠️ Error: {e}")
        
        print("-" * 70)
    
    # Show statistics
    print("\n📊 NOTIFICATION STATISTICS")
    print("-" * 70)
    
    stats = await service.get_stats()
    print(f"Total notifications: {sum(stats.values())}")
    for status, count in stats.items():
        print(f"  {status}: {count}")
    
    # List notifications
    print("\n📋 NOTIFICATION HISTORY")
    print("-" * 70)
    
    notifications = await service.list_notifications()
    for notif in notifications:
        print(f"  [{notif.id[:20]}...] {notif.notification_type} via {notif.channel}")
    
    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())