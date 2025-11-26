"""
WebSocket connection manager for multi-client support.

Handles connection tracking, subscriptions, and broadcasting.
"""
from typing import Dict, Set, List, Any, Optional
from collections import defaultdict  # Dict that creates default value for missing keys
import logging
import asyncio
from datetime import datetime
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)



class ConnectionManager:
    """Manages WebSocket connections and message broadcasting."""
    def __init__(self):
        # Store active WebSocket connections by client ID
        self.active_connections: Dict[str, WebSocket] = {}
        # Map client IDs to usernames (for authenticated connections)
        self.client_users: Dict[str, str] = {}
        # defaultdict(set): Auto-creates empty set for new keys, no KeyError
        # Track which topics each client subscribes to
        self.subscriptions: Dict[str, Set[str]] = defaultdict(set)
        # Track which clients subscribe to each topic (inverse mapping)
        self.topic_subscribers: Dict[str, Set[str]] = defaultdict(set)
        # Track connection timestamps
        self.connection_times: Dict[str, datetime] = {}
        # asyncio.Lock: Prevents race conditions when multiple async tasks modify data
        # (like threading.Lock but for async/await code)
        self._lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, client_id: str, username: Optional[str] = None):
        """Register a new client connection."""
        await websocket.accept()
        # async with lock: Ensures only one coroutine modifies data at a time
        async with self._lock:
            self.active_connections[client_id] = websocket
            self.subscriptions[client_id] = set()
            self.connection_times[client_id] = datetime.utcnow()
            if username:
                self.client_users[client_id] = username
        logger.info(f"Client connected: {client_id}")
    
    async def disconnect(self, client_id: str):
        """Remove client and clean up subscriptions."""
        async with self._lock:
            # .pop() removes and returns value, or default (None) if not found
            self.active_connections.pop(client_id, None)
            self.client_users.pop(client_id, None)
            self.connection_times.pop(client_id, None)
            # Get client's topics, then remove from reverse mapping
            client_topics = self.subscriptions.pop(client_id, set())
            for topic in client_topics:
                self.topic_subscribers[topic].discard(client_id)
                # Clean up empty topic entries
                if not self.topic_subscribers[topic]:
                    del self.topic_subscribers[topic]
        logger.info(f"Client disconnected: {client_id}")
    
    def subscribe(self, client_id: str, topics: List[str]) -> List[str]:
        """Subscribe client to topics."""
        if client_id not in self.active_connections:
            return []
        for topic in topics:
            # Add to both mappings: client->topics and topic->clients
            self.subscriptions[client_id].add(topic)
            self.topic_subscribers[topic].add(client_id)
        return topics
    
    def unsubscribe(self, client_id: str, topics: List[str]) -> List[str]:
        """Unsubscribe client from topics."""
        for topic in topics:
            # .discard() removes if exists, no error if not found (unlike .remove())
            self.subscriptions[client_id].discard(topic)
            self.topic_subscribers[topic].discard(client_id)
        return topics
    
    async def send_personal(self, client_id: str, message: Dict[str, Any]) -> bool:
        """Send message to specific client."""
        websocket = self.active_connections.get(client_id)
        if not websocket:
            return False
        try:
            await websocket.send_json(message)
            return True
        except:
            # Connection failed, clean up
            await self.disconnect(client_id)
            return False
    
    async def broadcast_to_topic(self, topic: str, message: Dict[str, Any]) -> int:
        """Broadcast message to all subscribers of a topic."""
        # .copy(): Create snapshot to avoid modification during iteration
        subscribers = self.topic_subscribers.get(topic, set()).copy()
        
        # Hierarchical topic matching: "signals.strategy-ma-001" also sends to "signals"
        # Split "signals.strategy-ma-001" -> ["signals", "strategy-ma-001"]
        parts = topic.split(".")
        for i in range(1, len(parts)):
            # Build parent topics: "signals"
            parent = ".".join(parts[:i])
            subscribers.update(self.topic_subscribers.get(parent, set()))
        
        # asyncio.gather: Run all send_personal calls concurrently (parallel)
        # return_exceptions=True: Don't stop on first error, collect all results
        results = await asyncio.gather(
            *[self.send_personal(cid, message) for cid in subscribers],
            return_exceptions=True
        )
        # Count successful sends (True values)
        return sum(1 for r in results if r is True)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        return {
            "total_connections": len(self.active_connections),
            "authenticated_connections": len(self.client_users),
            "total_topics": len(self.topic_subscribers),
            "topics": {t: len(s) for t, s in self.topic_subscribers.items()}
        }


# Singleton pattern: Create one instance shared across the application
# All imports of 'manager' get the same instance
manager = ConnectionManager()