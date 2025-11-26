"""
SQS-to-WebSocket bridge for real-time event streaming.

This bridge connects the backend event system (SQS from Day 5) to 
frontend clients (WebSocket from today):

    Strategy generates signal
           │
           ▼
    SQS Event Bus (Day 5)
           │
           ▼
    ┌──────────────────┐
    │  SQS Bridge      │  ◄── This module
    │  (polls SQS)     │
    └──────────────────┘
           │
           ▼
    Connection Manager
           │
           ▼
    WebSocket Clients (dashboards, apps)

Usage:
    # In FastAPI lifespan
    await sqs_bridge.start()  # On startup - begins polling SQS
    await sqs_bridge.stop()   # On shutdown - stops gracefully
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional
from decimal import Decimal

from trading_system.api.websocket.manager import manager
from trading_system.api.websocket.schemas import SignalMessage, SignalType

logger = logging.getLogger(__name__)


class SQSWebSocketBridge:
    """
    Bridges SQS events to WebSocket clients.
    
    Two modes:
    1. Production mode: Pass sqs_client to constructor, polls real SQS
    2. Demo mode: No sqs_client, use inject_event() for testing
    
    The bridge uses a handler pattern - each event type has a dedicated
    handler method that transforms the SQS message into WebSocket format.
    """
    
    def __init__(self, sqs_client=None):
        """
        Initialize bridge.
        
        Args:
            sqs_client: Async SQS client from Day 5 (aiobotocore)
                       If None, runs in demo mode (no SQS polling)
        """
        self._sqs_client = sqs_client
        self._running = False
        # Background task for SQS polling loop
        self._task: Optional[asyncio.Task] = None
        
        # Event type → handler method mapping
        # Add more handlers as you implement more event types
        self._handlers = {
            "SignalGeneratedEvent": self._handle_signal,
            # Future: "PerformanceUpdatedEvent": self._handle_performance,
            # Future: "OrderFilledEvent": self._handle_order,
        }
    
    async def start(self):
        """
        Start the bridge.
        
        In production mode: Creates background task to poll SQS
        In demo mode: Just logs startup (use inject_event for testing)
        """
        if self._running:
            return  # Already running, don't start twice
        
        self._running = True
        
        if self._sqs_client:
            # Production: Start background polling task
            # asyncio.create_task: Runs _listen_loop concurrently
            self._task = asyncio.create_task(self._listen_loop())
            logger.info("SQS-WebSocket bridge started (SQS mode)")
        else:
            # Demo: No SQS client, testing via inject_event()
            logger.info("SQS-WebSocket bridge started (demo mode - use inject_event)")
    
    async def stop(self):
        """
        Stop the bridge gracefully.
        
        Cancels the background task and waits for it to finish.
        Called during FastAPI shutdown.
        """
        self._running = False
        
        if self._task:
            # Cancel the background task
            self._task.cancel()
            try:
                # Wait for task to acknowledge cancellation
                await self._task
            except asyncio.CancelledError:
                # Expected - task was cancelled
                pass
        
        logger.info("SQS-WebSocket bridge stopped")
    
    async def _listen_loop(self):
        """
        Main SQS polling loop (runs as background task).
        
        Long-polling: wait_time_seconds=5 means SQS holds connection
        open for 5 seconds before returning empty if no messages.
        This is more efficient than frequent short polls.
        """
        while self._running:
            try:
                # Long-poll SQS for messages (up to 10 at a time)
                messages = await self._sqs_client.receive_messages(
                    "trading-events",      # Queue name from Day 5
                    max_messages=10,       # Batch size
                    wait_time_seconds=5    # Long-polling timeout
                )
                
                # Process each message
                for msg in messages:
                    await self._process_message(msg)
                    
            except asyncio.CancelledError:
                # Bridge is stopping, exit loop cleanly
                break
            except Exception as e:
                # Log error but don't crash - retry after delay
                logger.error(f"SQS listener error: {e}")
                await asyncio.sleep(5)  # Back-off before retry
    
    async def _process_message(self, message: Dict[str, Any]):
        """
        Route message to appropriate handler based on event_type.
        
        Pattern: Each event type has a dedicated handler method.
        This keeps the code organized as you add more event types.
        """
        try:
            event_type = message.get("event_type")
            handler = self._handlers.get(event_type)
            
            if handler:
                await handler(message)
            # Silently ignore unknown event types (may be for other consumers)
                
        except Exception as e:
            logger.error(f"Error processing message: {e}")
    
    async def _handle_signal(self, event: Dict[str, Any]):
        """
        Handle SignalGeneratedEvent from SQS.
        
        Transforms SQS event format → WebSocket SignalMessage format,
        then broadcasts to subscribers of the signal's topic.
        
        Topic hierarchy:
        - "signals" subscribers get ALL signals
        - "signals.{strategy_id}" subscribers get only that strategy
        """
        # Transform SQS event → Pydantic SignalMessage
        msg = SignalMessage(
            strategy_id=event.get("strategy_id", "unknown"),
            strategy_name=event.get("strategy_name", "Unknown"),
            symbol=event.get("symbol", ""),
            signal_type=SignalType(event.get("signal_type", "HOLD")),
            price=Decimal(str(event.get("price", 0))),
            indicators=event.get("indicators", {})
        )
        
        # Broadcast to topic: "signals.{strategy_id}"
        # Connection Manager also sends to parent topic "signals"
        topic = f"signals.{msg.strategy_id}"
        
        # model_dump(mode="json"): Converts Pydantic model to JSON-safe dict
        # (handles Decimal, datetime, etc.)
        await manager.broadcast_to_topic(topic, msg.model_dump(mode="json"))
    
    async def inject_event(self, event_type: str, data: Dict[str, Any]):
        """
        Inject event for testing (bypasses SQS).
        
        Use this in demo mode or tests to simulate events
        without running real SQS infrastructure.
        
        Example:
            await sqs_bridge.inject_event("SignalGeneratedEvent", {
                "strategy_id": "ma-001",
                "strategy_name": "Moving Average",
                "symbol": "AAPL",
                "signal_type": "BUY",
                "price": 150.0,
                "indicators": {"sma_20": 148.5, "sma_50": 145.0}
            })
        """
        # Add event_type to data (same format as real SQS message)
        data["event_type"] = event_type
        # Process through normal handler pipeline
        await self._process_message(data)


# Singleton instance - shared across the application
# All imports of 'sqs_bridge' get the same instance
sqs_bridge = SQSWebSocketBridge()