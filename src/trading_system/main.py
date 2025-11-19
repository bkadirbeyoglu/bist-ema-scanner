# src/trading_system/main.py
# pylint: disable=no-member,unexpected-keyword-arg,no-value-for-parameter
"""
Main entry point for the trading system with PostgreSQL event store.
"""
import asyncio
import logging
import signal
from typing import Optional
from datetime import datetime
from decimal import Decimal

from trading_system.contexts.order_management.domain.entities.order import (
    Order, OrderType, OrderSide
)
from trading_system.shared_kernel.value_objects.price import Price
from trading_system.shared_kernel.value_objects.symbol import Symbol
from trading_system.contexts.order_management.domain.events import OrderCreatedEvent

# New imports for PostgreSQL event store
from trading_system.architecture.event_store.postgres_connection import PostgresConnectionPool
from trading_system.architecture.event_store.postgres_event_store import PostgresEventStore
from trading_system.architecture.event_store.dual_event_bus import DualEventBus
from trading_system.architecture.messaging.sqs_event_bus import SQSEventBus

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class TradingSystemApp:
    """Main application class with PostgreSQL event store."""
    
    def __init__(self):
        """Initialize the trading system components."""
        # Changed from InMemoryEventBus to DualEventBus
        self.event_bus: Optional[DualEventBus] = None
        # Changed from InMemoryEventStore to PostgresEventStore
        self.event_store: Optional[PostgresEventStore] = None
        # New: PostgreSQL connection pool
        self.pg_pool: Optional[PostgresConnectionPool] = None
        self._running = False
        self._shutdown_event = asyncio.Event()
    
    async def startup(self) -> None:
        """Start up the trading system with PostgreSQL event store."""
        logger.info("=" * 60)
        logger.info("🚀 Starting Algorithmic Trading System")
        logger.info("=" * 60)
        
        # Initialize PostgreSQL connection pool
        logger.info("📊 Initializing PostgreSQL event store...")
        self.pg_pool = PostgresConnectionPool(
            host="localhost",  # or "postgres" if running in Docker
            port=5432,
            database="trading_db",
            user="trading",
            password="password"
        )
        await self.pg_pool.connect()
        
        # Create event store
        self.event_store = PostgresEventStore(self.pg_pool)
        logger.info("✓ PostgreSQL event store ready")
        
        # Create SQS event bus
        logger.info("📊 Initializing SQS event bus...")
        sqs_bus = SQSEventBus(
            queue_url="http://localhost:4566/000000000000/trading-events",
            region="us-east-1"
        )
        
        # Create dual event bus (publishes to both SQS and PostgreSQL)
        logger.info("📊 Creating dual event bus...")
        self.event_bus = DualEventBus(
            sqs_bus=sqs_bus,
            event_store=self.event_store
        )
        
        # Start the event bus
        await self.event_bus.start()
        logger.info("✓ Dual event bus started (SQS + PostgreSQL)")
        
        # Register event handlers
        await self._register_handlers()
        
        # Perform system check
        await self._system_check()
        
        self._running = True
        logger.info("✅ All systems operational")
        logger.info("📈 Events now go to both SQS and PostgreSQL for audit trail!")
    
    async def shutdown(self) -> None:
        """Gracefully shut down the trading system."""
        logger.info("🛑 Initiating shutdown sequence...")
        self._running = False
        
        # Signal shutdown
        self._shutdown_event.set()
        await asyncio.sleep(0.5)
        
        # Cleanup resources
        if self.event_bus:
            await self.event_bus.stop()
        
        if self.event_store:
            # Log statistics
            try:
                stats = await self.event_store.get_statistics()
                logger.info(f"📝 Event store statistics: {stats}")
            except Exception as e:
                logger.warning(f"Could not retrieve statistics: {e}")
        
        if self.pg_pool:
            await self.pg_pool.disconnect()
            logger.info("✓ PostgreSQL connection closed")
        
        logger.info("✅ Shutdown complete")
    
    async def _register_handlers(self) -> None:
        """Register event handlers."""
        async def handle_order_created(event: OrderCreatedEvent):
            """Handler for order created events."""
            logger.info(f"📩 Order created: {event.order_id} - "
                       f"{event.side.value} {event.quantity} {event.symbol}")
            # No need to manually store - DualEventBus does it automatically!
        
        self.event_bus.subscribe(OrderCreatedEvent, handle_order_created)
        logger.info("🔔 Event handlers registered")
    
    async def _system_check(self) -> None:
        """Perform system health check."""
        logger.info("🔍 Running system checks...")
        
        try:
            # Test order creation
            test_order = Order.create_market_order(
                symbol=Symbol("AAPL"),
                quantity=100,
                side=OrderSide.BUY
            )
            
            # Test event publishing
            await self.event_bus.publish(OrderCreatedEvent(
                event_id=f"test-{datetime.utcnow().isoformat()}",
                timestamp=datetime.utcnow(),
                version=1,
                order_id=str(test_order.id),
                symbol=test_order.symbol.ticker,
                quantity=Decimal(str(test_order.quantity)),
                price=None,
                order_type=test_order.order_type,
                side=test_order.side,
                account_id=None,
                metadata={}
            ))
            
            logger.info("✅ System check passed")
            
        except Exception as e:
            logger.error(f"❌ System check failed: {e}")
            raise
    
    async def run(self) -> None:
        """Run the main application loop."""
        try:
            await self.startup()
            
            logger.info("-" * 60)
            logger.info("💡 Press Ctrl+C to shutdown")
            logger.info("-" * 60)
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
            logger.info("🛑 Shutdown signal received, stopping...")
            
        except asyncio.CancelledError:
            logger.info("🔥 Task cancelled, initiating shutdown...")
        except Exception as e:
            logger.error(f"❌ Fatal error: {e}", exc_info=True)
            raise
        finally:
            try:
                await asyncio.wait_for(self.shutdown(), timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("⚠️ Shutdown timed out after 5 seconds")
            except Exception as e:
                logger.error(f"Error during shutdown: {e}")


def setup_signal_handlers(app: TradingSystemApp, loop: asyncio.AbstractEventLoop):
    """Set up signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"📡 Received signal {signum}")
        loop.call_soon_threadsafe(app._shutdown_event.set)
        for task in asyncio.all_tasks(loop):
            loop.call_soon_threadsafe(task.cancel)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)


def main() -> None:
    """Entry point for the application."""
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "ALGORITHMIC TRADING SYSTEM" + " " * 17 + "║")
    print("║" + " " * 17 + "PostgreSQL Event Store" + " " * 19 + "║")
    print("╚" + "═" * 58 + "╝")
    
    app = TradingSystemApp()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    setup_signal_handlers(app, loop)
    
    try:
        loop.run_until_complete(app.run())
    except KeyboardInterrupt:
        logger.info("⌨️ Keyboard interrupt received")
    except Exception as e:
        logger.error(f"❌ Application crashed: {e}", exc_info=True)
        raise
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.close()
            logger.info("🔒 Event loop closed")
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")


if __name__ == "__main__":
    main()