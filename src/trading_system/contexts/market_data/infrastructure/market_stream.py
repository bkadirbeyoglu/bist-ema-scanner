"""
Production-grade WebSocket client for real-time market data.
Production-grade WebSocket client for real-time market data.

ARCHITECTURE DECISION LOG:
=========================

1. Why Three Tasks?
   - Receive: Fast path (network → queue)
   - Process: Slow path (queue → business logic)
   - Heartbeat: Independent (keep connection alive)
   
2. Why Queue?
   - Decouples producer (network) from consumer (handler)
   - Buffers bursts (1000 messages arrive, process 100/sec)
   - Prevents backpressure to network
   
3. Why Exponential Backoff?
   - Server might be overloaded
   - Don't hammer with reconnects
   - 5s, 10s, 20s, 40s, 60s max

4. Why Statistics?
   - Monitor health (messages_received vs processed)
   - Detect issues (high error count)
   - Capacity planning (queue_size trending up)
"""

import asyncio
import aiohttp
import json
import logging
from typing import Dict, Any, Optional, Callable, Awaitable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

@dataclass
class MarketDataStream:
    """
    WebSocket client with producer-consumer pattern.
    
    PATTERN: Producer-Consumer with Queue
    =====================================
    
    Producer (Task 1):
        while True:
            data = await network.receive()  # I/O bound
            await queue.put(data)           # Non-blocking
    
    Queue (Buffer):
        [msg1, msg2, msg3, ...]  # FIFO
        Max size: 1000 (configurable)
    
    Consumer (Task 2):
        while True:
            data = await queue.get()        # Waits if empty
            await process(data)             # CPU bound, can be slow
    
    Watchdog (Task 3):
        while True:
            await sleep(20)
            await ping()                    # Keep alive
    
    WHY THIS WORKS:
    - Network speed ≠ Processing speed
    - Queue absorbs speed difference
    - Tasks run concurrently (asyncio.create_task)
    - Failures isolated by task boundary
    """
     # PUBLIC CONFIGURATION
    # User provides these when creating instance
    url: str    # WebSocket URL (ws:// or wss://)
    on_message: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None      # Handler function
    reconnect_interval: int = 5     # Base reconnection delay (seconds)
    max_queue_size: int = 1000      # Maximum messages to buffer

     # PRIVATE STATE
    # These are managed internally, not set by user
    # init=False: Not in __init__ parameters
    # repr=False: Not shown in str(instance)
    _ws: Optional[aiohttp.ClientWebSocketResponse] = field(
        default=None, init=False, repr=False
    )       # The actual WebSocket representation

    _session: Optional[aiohttp.ClientSession] = field(
        default=None, init=False, repr=False
    )       # HTTP session (reused for all connections)

    _running: bool = field(default=False, init=False, repr=False)       # Controls background tasks: True = run, False = stop

    _message_queue: asyncio.Queue = field(
        default=None, init=False, repr=False
    )       # Buffer between receive and process tasks

    # STATISTICS & MONITORING
    # Track what's happening for observability
    messages_received: int = field(default=0, init=False, repr=False)
    messages_processed: int = field(default=0, init=False, repr=False)
    reconnections: int = field(default=0, init=False, repr=False)
    errors: int = field(default=0, init=False, repr=False)

    def __post_init__(self):
        """
        Called after dataclass __init__.

        Why here and not __init__?
        - dataclass creates __init__ automaticall
        - __post_init__ runs right after
        - Perfect for initialization that needs instance created first

        Why create queue here?
        - Queue needs event loop running
        - Might not be available at class definition time
        - Safe to create when instance is created
        """
        self._message_queue = asyncio.Queue(maxsize=self.max_queue_size)

    async def connect(self):
        """
        Establish WebSocket connection and start background tasks.

        CONTROL FLOW:
        1. Create HTTP session (if needed)
        2. Connect WebSocket
        3. Set _running = True (enables tasks)
        4. Launch 3 concurrent tasks
        5. Tasks run in background
        6. This function returns immediately

        ERROR HANDLING:
        - Connection fails -> log error
        - Schedule reconnection (with backoff)
        - Don't crash the application
        """
        try:
            # Step 1: Create session (reuse for all connections)
            if not self._session:
                # ClientSession: Connection pooling, cookie handling
                self._session = aiohttp.ClientSession()
            
            # Step 2: Connect WebSocket
            # ws_connect returns ClientWebSocketResponse
            # This is async: waits for TCP + WebSocket handshake
            self._ws = await self._session.ws_connect(self.url)
            
            # Step 3: Enable background tasks
            self._running = True
            
            # Step 4: Launch three concurrent tasks
            # create_task: Schedule coroutine to run
            # Doesn't wait - returns immediately
            # Task runs in background on event loop
            
            asyncio.create_task(self._receive_messages())
            # Task 1: Receive from network → queue
            
            asyncio.create_task(self._process_messages())
            # Task 2: Process from queue → handler
            
            asyncio.create_task(self._heartbeat())
            # Task 3: Periodic pings
            
            logger.info(f"WebSocket connected: {self.url}")
            
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            # Don't crash - try to reconnect
            await self._schedule_reconnect()

    async def disconnect(self):
        """
        Gracefully shutdown WebSocket connection.
        
        SHUTDOWN SEQUENCE:
        1. Set _running = False(stops tasks)
        2. Close WebSocket (sends close frame)
        3. Close HTTP session (cleanup)
        4. Tasks see _running = False and exit

        Why this order?
        - Stop accepting new messages first
        - Then close connection cleanly
        - Finally cleanup resources
        """
        # Step 1: Signal tasks to stop
        self._running = False

        # Step 2: Close WebSocket
        if self._ws:
            # Sends WebSocket close frame to server
            # Server acknlowledges, connection closed
            await self._ws.close()

        # Step 3: Close HTTP Session
        if self._session:
            # Close all connections in pool
            # Cleanup resources
            await self._session.close()

        logger.info("WebSocket disconnected")

    async def _receive_messages(self):
        """
        TASK 1: Network I/O - Receive messages from WebSocket.
        
        RESPONSIBILITY:
        - Get data from network FAST
        - Put in queue
        - Handle network errors
        - Trigger reconnection if needed
        
        NOT responsible for:
        - Processing message content (Task 2's job)
        - Business logic (handler's job)
        - Keeping connection alive (Task 3's job)
        
        LOOP STRUCTURE:
        while _running:              # Continue while system active
            check connection         # Is WebSocket open?
            receive message          # Network I/O (blocking)
            handle message type      # TEXT, ERROR, CLOSED, etc.
            put in queue            # Buffer for processing
        """
        while self._running:
            try:
                # Check 1: Is connection still alive?
                if not self._ws or self._session.closed:
                    logger.warning("WebSocket closed, reconnecting...")
                    await self._schedule_reconnect()
                    break  # Exit this task, reconnect creates new one

                # Step 1: Receive message (BLOCKS until message arrives)
                # This is the I/O operation we want to isolate
                msg = await self._ws.receive()

                # Step 2: Handle different message types
                # WebSocket protocol has multiple message types

                if msg.type == aiohttp.WSMsgType.TEXT:
                    # TEXT: JSON message with market data
                    try:
                        data = json.loads(msg.data)
                        await self._message_queue.put(data)
                        self.messages_received += 1
                    except json.JSONDecodeError as e:
                        # Invalid JSON - log and continue
                        logger.error(f"Invalid JSON: {e}")
                        self.errors += 1

                elif msg.type == aiohttp.WSMsgType.ERROR:
                    # ERROR: WebSocket error occurred
                    logger.error(f"WebSocket error: {msg.data}")
                    self.errors += 1
                    await self._schedule_reconnect()
                    break

                elif msg.type == aiohttp.WSMsgType.CLOSED:
                    # CLOSED: Server closed connection gracefully
                    logger.info("WebSocket closed by server")
                    await self._schedule_reconnect()
                    break

                # Note: Other types (BINARY, PING, PONG) handled automatically

            except Exception as e:
                # Unexpected error in receive loop
                logger.error(f"Error receiving message: {e}")
                self.errors += 1
                await self._schedule_reconnect()
                break

    async def _process_messages(self):
        """
        TASK 2: Business Logic - Process messages from queue.
        
        RESPONSIBILITY:
        - Get messages from queue
        - Call user's handler function
        - Handle errors in user code
        - Track processing statistics
        
        NOT responsible for:
        - Network I/O (Task 1's job)
        - Connection management (Task 1's job)
        
        ERROR ISOLATION:
        - If handler raises exception → log it, continue
        - One bad message doesn't stop processing
        - System stays healthy even with buggy handlers
        
        QUEUE BEHAVIOR:
        - get() blocks if queue empty (waits for data)
        - Processes messages in FIFO order
        - task_done() marks message as processed
        """
        while self._running:
            try:
                # Step 1: Get message from queue
                # BLOCKS if queue empty (waits for Task 1)
                # Returns immediately if messages available
                message = await self._message_queue.get()

                # Step 2: Call user's handler
                if self.on_message:
                    try:
                        # Handler can be slow - that's OK!
                        # We're isolated from network task
                        await self.on_message(message)
                        self.messages_processed += 1
                    
                    except Exception as e:
                         # CRITICAL: Handler error must not crash task
                        # Log with full traceback for debugging
                        logger.error(f"Handler error: {e}", exc_info=True)
                        self.errors += 1
                        # Continue processing next message
                
                # Step 3: Mark message as processed
                # Required for queue.join() to work
                self._message_queue.task_done()
            
            except asyncio.CancelledError:
                # Task cancelled (normal shutdown)
                # Clean exit
                break

            except Exception as e:
                # Unexpected error in processing loop
                logger.error(f"Error processing message: {e}")
                self.errors += 1
                # Continue trying to process

    async def _heartbeat(self):
        """
        TASK 3: Connection Health - Keep WebSocket alive.
        
        RESPONSIBILITY:
        - Send periodic pings to server
        - Detect dead connections
        - Runs independently of other tasks
        
        WHY NEEDED?
        - Firewalls may close idle connections
        - Load balancers timeout inactive sockets
        - Servers drop silent clients
        
        HOW IT WORKS:
        - Every 20 seconds: send ping
        - Server responds with pong (automatic)
        - If ping fails → connection is dead
        
        PING/PONG Protocol:
        Client → Server: PING frame
        Server → Client: PONG frame (echo)
        If PONG doesn't arrive → connection broken
        """
        while self._running:
            try:
                 # Wait 20 seconds between pings
                # Don't hammer server with constant pings
                await asyncio.sleep(20)

                # Check connection still alive
                if self._ws and not self._ws.closed:
                    # Send PING frame
                    # Server must respond with PONG
                    # aiohttp handles PONG automatically
                    await self._ws.ping()
                    logger.debug("Heartbeat ping sent")
                    
                # If ping() raises exception → connection dead
                # Will be caught by outer try/except
            
            except asyncio.CancelledError:
                # Task cancelled - clean shutdown
                break
                
            except Exception as e:
                # Ping failed - connection likely dead
                logger.error(f"Heartbeat error: {e}")
                # Let receive task detect and reconnect
                # Don't trigger reconnect here (race condition)

    async def _schedule_reconnect(self):
        """
        Schedule reconnection with exponential backoff.
        
        EXPONENTIAL BACKOFF:
        - Attempt 1: Wait 5 seconds   (reconnect_interval * 2^0)
        - Attempt 2: Wait 10 seconds  (reconnect_interval * 2^1)
        - Attempt 3: Wait 20 seconds  (reconnect_interval * 2^2)
        - Attempt 4: Wait 40 seconds  (reconnect_interval * 2^3)
        - Attempt 5+: Wait 60 seconds (capped at max)
        
        WHY EXPONENTIAL?
        - Server might be overloaded → give it time
        - Network might be down → don't spam
        - Cascade failures → back off prevents making it worse
        
        CALCULATION:
        backoff = interval * (2 ^ reconnections)
        capped at 60 seconds maximum
        """
        # Don't reconnect if shutting down
        if not self._running:
            return
        
        # Track reconnection attempts
        self.reconnections += 1

        # Calculate backoff: 5, 10, 20, 40, 60, 60, ...
        # 2 ** self.reconnections: 1, 2, 4, 8, 16, ...
        backoff = min(
            self.reconnect_interval * (2 ** self.reconnections),
            60  # Maximum 60 seconds
        )
        
        logger.info(f"Reconnecting in {backoff}s (attempt {self.reconnections})...")

        # Wait before reconnecting
        await asyncio.sleep(backoff)
        
        # Try to reconnect
        # This creates new tasks, old ones will exit
        await self.connect()

    async def subscribe(self, symbols: list):
        """
        Send subscription message to server.
        
        PROTOCOL:
        Most WebSocket APIs use subscribe/unsubscribe:
        
        Client → Server:
        {
            "action": "subscribe",
            "symbols": ["AAPL", "GOOGL", "MSFT"]
        }
        
        Server → Client:
        {
            "type": "subscribed",
            "symbols": ["AAPL", "GOOGL", "MSFT"]
        }
        
        Then server sends updates for those symbols only.
        """
        if self._ws and not self._ws.closed:
            message = {
                "action": "subscribe",
                "symbols": symbols
            }
            # send_json: Automatically converts dict → JSON → sends
            await self._ws.send_json(message)
            logger.info(f"Subscribed to: {symbols}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get current statistics for monitoring.
        
        HEALTH INDICATORS:
        - messages_received vs messages_processed
          → If gap growing: handler too slow
        
        - reconnections
          → If increasing: connection unstable
        
        - errors
          → If high: investigate logs
        
        - queue_size
          → If near max: backpressure, scale processing
        
        - connected
          → Current connection status
        """
        return {
            "messages_received": self.messages_received,
            "messages_processed": self.messages_processed,
            "reconnections": self.reconnections,
            "errors": self.errors,
            "queue_size": self._message_queue.qsize(),
            "connected": self._ws and not self._ws.closed if self._ws else False
        }