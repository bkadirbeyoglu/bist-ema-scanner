#!/usr/bin/env python3
"""Demo script for SNS Fan-Out Pattern. Run: poetry run python scripts/demo_sns_fanout.py"""

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from trading_system.architecture.messaging.sns.sns_client import get_sns_client, SNSConfig
from trading_system.architecture.messaging.sns.sns_publisher import SNSPublisher
from trading_system.architecture.messaging.sns.filter_policies import FilterPolicyBuilder, TradingFilters
from trading_system.architecture.messaging.sns.event_router import EventRouter
from trading_system.shared_kernel.sns_events import PriceUpdatedEvent, OrderCreatedEvent


async def main() -> None:
    print("\n" + "=" * 60)
    print("SNS FAN-OUT PATTERN DEMO")
    print("=" * 60)

    config = SNSConfig(endpoint_url="http://localhost:4566", region="us-east-1")

    # Part 1: Topic Creation & Publishing
    async with get_sns_client(config) as client:
        topic_arn = await client.create_topic("price-updates")
        print(f"\n✓ Created topic: {topic_arn}")

        publisher = SNSPublisher(client, topic_arn)
        event = PriceUpdatedEvent(
            symbol="AAPL", price=Decimal("178.50"),
            timestamp=datetime.now(timezone.utc), source="demo"
        )
        result = await publisher.publish(event)
        print(f"✓ Published event: {result.message_id[:20]}...")

    # Part 2: Filter Policies
    print("\n--- Filter Policy Examples ---")
    print(f"Symbols: {FilterPolicyBuilder().exact_match('symbol', 'AAPL', 'GOOGL').build()}")
    print(f"Trading: {TradingFilters.price_updates_for_symbols('AAPL', 'TSLA')}")

    # Part 3: Event Routing (singledispatch)
    print("\n--- Event Routing ---")
    router = EventRouter()
    events = [
        PriceUpdatedEvent(symbol="AAPL", price=Decimal("178.50"),
                          timestamp=datetime.now(timezone.utc), source="demo"),
        OrderCreatedEvent(order_id=uuid4(), symbol="AAPL", side="buy",
                          quantity=100, order_type="market"),
    ]
    for event in events:
        result = router.route(event)
        print(f"  {type(event).__name__} → {result.get('handler')}")

    print(f"\n✓ Router stats: {router.get_stats()}")
    print("\nDEMO COMPLETE!")


if __name__ == "__main__":
    asyncio.run(main())