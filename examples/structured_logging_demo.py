"""Demonstration of structured logging."""

import asyncio
from trading_system.shared_kernel.logging_config import setup_logging, get_logger, log_context

logger = get_logger(__name__)


async def process_order(order_id: str):
    """Process order with structured logging."""
    with log_context(order_id=order_id):
        logger.info("order_processing_started", extra={"quantity": 100})
        await asyncio.sleep(0.1)
        logger.info("order_validated")
        await asyncio.sleep(0.1)
        logger.info("order_submitted", extra={"exchange": "NASDAQ"})


async def main():
    setup_logging(level="DEBUG", log_file="demo.log", json_format=True)
    
    await process_order("ORDER-123")
    await process_order("ORDER-456")
    
    print("\nCheck demo.log for JSON formatted logs!")


if __name__ == "__main__":
    asyncio.run(main())