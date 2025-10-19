"""
Main entry point for the trading system.

This module integrates all components from Days 1-3:
- Domain entities (Order, Portfolio, Position)
- Value objects (Price, Quantity, Symbol)
- Domain events (OrderCreatedEvent, etc.)
- Event Bus (from shared_kernel)
"""
import asyncio
import logging
import signal
from typing import Optional, List, Any
from datetime import datetime
from dataclasses import dataclass, field
from decimal import Decimal

from trading_system.contexts.order_management.domain.entities.order import (
    Order, OrderType, OrderSide
)
from trading_system.shared_kernel.value_objects.price import Price
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.contexts.order_management.domain.events import OrderCreatedEvent
from trading_system.shared_kernel.event_bus import InMemoryEventBus

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# Simple Event Store (placeholder for Day 5)
@dataclass
class InMemoryEventStore:
    """
    Simple in-memory event store for development.
    
    In production, events would be persisted to:
    - PostgreSQL (event sourcing table)
    - AWS EventBridge (event routing)
    - Kafka (event streaming)
    
    For now, we use in-memory storage for simplicity.
    """
    events: List[Any] = field(default_factory=list)
    
    def append(self, event: Any) -> None:
        """Append an event to the store."""
        self.events.append(event)
    
    def get_all_events(self) -> List[Any]:
        """Get all stored events."""
        return self.events.copy()


class TradingSystemApp:
    """
    Main application class for the trading system.
    
    This class manages the lifecycle of all trading components
    and coordinates their interactions.
    
    PYTHON FEATURE: __init__ is the constructor
    ============================================
    Called automatically when you create an instance:
    app = TradingSystemApp()  # This calls __init__
    
    self refers to the instance being created
    Similar to 'this' in Java/C#/JavaScript
    """
    
    def __init__(self):
        """Initialize the trading system components."""
        self.event_bus: Optional[InMemoryEventBus] = None
        self.event_store: Optional[InMemoryEventStore] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def startup(self) -> None:
        """
        Start up the trading system components.
        
        This method:
        1. Initializes the event infrastructure
        2. Registers event handlers
        3. Performs system health checks
        
        PYTHON KEYWORD: async
        ====================
        Marks a function as asynchronous (coroutine)
        Can use 'await' inside to pause execution
        Must be called with 'await' or asyncio.run()
        """
        logger.info("=" * 60)
        logger.info("🚀 Starting Algorithmic Trading System")
        logger.info("=" * 60)
        
        # Initialize event infrastructure
        logger.info("📊 Initializing event infrastructure...")
        self.event_bus = InMemoryEventBus()
        self.event_store = InMemoryEventStore()
        
        # Register event handlers
        await self._register_handlers()
        
        # Perform system check
        await self._system_check()
        
        self._running = True
        logger.info("✅ All systems operational")
        logger.info("📈 Trading system ready for orders")
    
    async def shutdown(self) -> None:
        """
        Gracefully shut down the trading system.
        
        This ensures all pending operations complete
        and resources are properly cleaned up.
        """
        logger.info("🛑 Initiating shutdown sequence...")
        self._running = False
        
        # Signal shutdown to all components
        self._shutdown_event.set()
        
        # Allow time for graceful shutdown
        await asyncio.sleep(0.5)
        
        # Cleanup resources
        if self.event_store:
            events_count = len(self.event_store.get_all_events())
            logger.info(f"📝 Processed {events_count} events this session")
        
        logger.info("✅ Shutdown complete")
    
    async def _register_handlers(self) -> None:
        """
        Register event handlers for domain events.
        
        PYTHON CONVENTION: Leading underscore (_)
        =========================================
        Indicates "internal" or "private" method
        Not enforced by Python, just a convention
        Tells users "don't call this directly"
        
        PATTERN EXPLANATION: Event Handler Registration
        ================================================
        This method sets up the "listeners" for our event-driven system.
        When events are published to the event bus, these handlers will
        automatically be called to process them.
        
        Think of it like subscribing to a newsletter:
        - Event Bus = Post Office
        - Events = Letters/Magazines
        - Handlers = Mailboxes that receive specific types of mail
        - subscribe() = Telling the post office your address
        """
        
        # ================================================================
        # NESTED FUNCTION: Event Handler Definition
        # ================================================================
        # We define the handler INSIDE this method rather than as a
        # separate class method. This is a deliberate design choice.
        
        async def handle_order_created(event: OrderCreatedEvent):
            """
            Handler for order created events.
            
            PYTHON FEATURE: Nested Function (Closure)
            ==========================================
            This function is defined INSIDE another function (_register_handlers).
            
            Key Benefits:
            1. CLOSURE: Has access to outer function's variables
               - Can access 'self' from _register_handlers
               - Can access 'logger' from module level
               - Can access self.event_store without passing it as parameter
            
            2. ENCAPSULATION: Handler logic is close to where it's registered
               - Easy to see what handlers exist
               - Clear relationship between handler and subscription
            
            3. SPECIALIZATION: Can create handler variations easily
               - Each handler is customized for its specific event
               - No need for complex inheritance hierarchies
            
            Alternative Approach (Class Method):
            ====================================
            We COULD define this as a class method:
            
            class TradingSystemApp:
                async def _handle_order_created(self, event):
                    ...
            
            But nested functions are cleaner here because:
            - Handler is only used in one place (this registration)
            - Keeps related code together
            - Python convention for event handlers
            
            ASYNC KEYWORD:
            ==============
            The handler is async because:
            - Event bus calls handlers with 'await'
            - Allows handler to do async operations (DB calls, API requests)
            - Doesn't block other handlers from running
            """
            
            # Log the event in a human-readable format
            # event.side.value gets the string value from the enum (e.g., "BUY")
            logger.info(f"📩 Order created: {event.order_id} - "
                       f"{event.side.value} {event.quantity} {event.symbol}")
            
            # Store the event for later analysis/replay
            # This demonstrates the CLOSURE in action:
            # - 'self' comes from the outer _register_handlers method
            # - The nested function "closes over" the outer function's variables
            # - This is why it's called a "closure"
            self.event_store.append(event)
        
        # ================================================================
        # SUBSCRIPTION: Connecting Handler to Event Type
        # ================================================================
        # This is where the "magic" happens - we tell the event bus:
        # "When you see an OrderCreatedEvent, call handle_order_created"
        
        # subscribe() signature: subscribe(event_type, handler_function)
        # - event_type: The CLASS of events to listen for (not an instance!)
        # - handler_function: The async function to call when event occurs
        
        # Note: We pass the FUNCTION OBJECT, not a function call
        # CORRECT:   subscribe(OrderCreatedEvent, handle_order_created)
        # WRONG:     subscribe(OrderCreatedEvent, handle_order_created())
        #            ^ This would CALL the function immediately!
        
        self.event_bus.subscribe(OrderCreatedEvent, handle_order_created)
        
        # ================================================================
        # WHAT HAPPENS AFTER REGISTRATION?
        # ================================================================
        # 1. Somewhere in the system, code publishes an event:
        #    await event_bus.publish(OrderCreatedEvent(...))
        #
        # 2. Event bus sees it's an OrderCreatedEvent
        #
        # 3. Event bus looks up all handlers subscribed to OrderCreatedEvent
        #
        # 4. Event bus calls: await handle_order_created(event)
        #
        # 5. Our handler executes: logs the message, stores the event
        #
        # 6. Event bus moves on to the next handler (if any)
        
        # ================================================================
        # SCALING TO MULTIPLE HANDLERS
        # ================================================================
        # To add more handlers, just define more nested functions and
        # subscribe them:
        #
        # async def handle_order_validated(event: OrderValidatedEvent):
        #     logger.info(f"✅ Order validated: {event.order_id}")
        #     self.event_store.append(event)
        #
        # self.event_bus.subscribe(OrderValidatedEvent, handle_order_validated)
        #
        # async def handle_order_rejected(event: OrderRejectedEvent):
        #     logger.error(f"❌ Order rejected: {event.order_id}")
        #     # Could send alert, update metrics, etc.
        #
        # self.event_bus.subscribe(OrderRejectedEvent, handle_order_rejected)
        
        logger.info("🔔 Event handlers registered")
    
    async def _system_check(self) -> None:
        """Perform system health check."""
        logger.info("🔍 Running system checks...")
        
        try:
            # Test order creation using factory method
            # Order entity signature: symbol, quantity (int), side, order_type
            test_order = Order.create_market_order(
                symbol=Symbol("AAPL"),
                quantity=100,  # int, not Decimal
                side=OrderSide.BUY
            )
            
            # Test event publishing
            # Market orders don't have a price until filled
            await self.event_bus.publish(OrderCreatedEvent(
                event_id=f"test-{datetime.utcnow().isoformat()}",
                timestamp=datetime.utcnow(),
                version=1,
                order_id=str(test_order.id),
                symbol=test_order.symbol.ticker,  # Symbol has 'ticker', not 'value'
                quantity=Decimal(str(test_order.quantity)),
                price=None,  # Market orders have no price at creation
                order_type=test_order.order_type,
                side=test_order.side,
                account_id=None,  # Account ID not part of Order entity yet
                metadata={}
            ))
            
            logger.info("✅ System check passed")
            
        except Exception as e:
            logger.error(f"❌ System check failed: {e}")
            raise
    
    async def run(self) -> None:
        """
        Run the main application loop.
        
        This method keeps the application running until
        a shutdown signal is received.
        
        SIGNAL HANDLING:
        ================
        The application waits for a shutdown signal (Ctrl+C or SIGTERM).
        When received, it performs graceful shutdown.
        
        The asyncio.CancelledError exception is raised when tasks
        are cancelled (happens during signal handling).
        """
        try:
            await self.startup()
            
            logger.info("-" * 60)
            logger.info("💡 Press Ctrl+C to shutdown")
            logger.info("-" * 60)
            
            # Wait for shutdown signal
            # Event.wait() is an async operation that blocks
            # until the event is set (by shutdown signal)
            await self._shutdown_event.wait()
            
            logger.info("🛑 Shutdown signal received, stopping...")
            
        except asyncio.CancelledError:
            # This is expected when signal handler cancels tasks
            logger.info("🔥 Task cancelled, initiating shutdown...")
            # Don't re-raise, proceed to finally block
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}", exc_info=True)
            raise
        finally:
            # Finally block ALWAYS runs, even if exception occurs
            # Perfect for cleanup code
            
            # Add a timeout to shutdown to prevent hanging
            try:
                await asyncio.wait_for(self.shutdown(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Shutdown timed out after 5 seconds")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")


def setup_signal_handlers(app: TradingSystemApp, loop: asyncio.AbstractEventLoop):
    """
    Set up signal handlers for graceful shutdown.
    
    UNIX SIGNALS explained:
    =======================
    SIGINT (2): Interrupt from keyboard (Ctrl+C)
    SIGTERM (15): Termination signal (docker stop, kill command)
    
    These signals allow graceful shutdown before force-kill
    
    ASYNCIO SIGNAL HANDLING:
    ========================
    For asyncio applications, we need to bridge the gap between
    synchronous signal handlers and the async event loop.
    
    Problem: signal.signal() handlers are synchronous, but we need
    to trigger async shutdown.
    
    Solution: Use a synchronous handler that schedules async work
    on the event loop using loop.call_soon_threadsafe()
    """
    
    def signal_handler(signum, frame):
        """
        Synchronous signal handler.
        
        This runs in the main thread when a signal is received.
        We can't call async functions directly, so we schedule
        the shutdown on the event loop.
        """
        logger.info(f"📡 Received signal {signum}")
        
        # Schedule the shutdown event to be set on the event loop
        # call_soon_threadsafe ensures thread-safe scheduling
        loop.call_soon_threadsafe(app._shutdown_event.set)
        
        # IMPORTANT: Also cancel all running tasks to ensure clean exit
        # This forces the event loop to stop waiting
        for task in asyncio.all_tasks(loop):
            loop.call_soon_threadsafe(task.cancel)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main() -> None:
    """
    Entry point for the application.
    
    This function:
    1. Creates the application instance
    2. Sets up signal handlers
    3. Runs the async event loop
    
    PYTHON CONVENTION: if __name__ == "__main__"
    =============================================
    This block only runs if script is executed directly
    Not run if script is imported as a module
    
    Example:
    python main.py        # Runs main()
    import main          # Does NOT run main()
    """
    # Print startup banner
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "ALGORITHMIC TRADING SYSTEM" + " " * 17 + "║")
    print("║" + " " * 20 + "Docker Edition v1.0" + " " * 19 + "║")
    print("╚" + "═" * 58 + "╝")
    
    # Create application instance
    app = TradingSystemApp()
    
    # Create event loop explicitly so we can pass it to signal handlers
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Set up signal handlers with access to the event loop
    setup_signal_handlers(app, loop)
    
    try:
        # Run the application
        # Use loop.run_until_complete instead of asyncio.run()
        # because we need to manage the loop ourselves for signal handling
        loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        # This should rarely happen now that we have signal handlers
        logger.info("⌨️ Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Application crashed: {e}", exc_info=True)
        raise
    finally:
        # Clean up any remaining tasks
        try:
            # Cancel all remaining tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Wait for all tasks to complete cancellation
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            # Close the loop
            loop.close()
            logger.info("🔒 Event loop closed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()