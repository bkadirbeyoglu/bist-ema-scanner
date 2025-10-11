"""
Structured logging configuration for production observability.

LOGGING ARCHITECTURE:
====================

Components:
1. JSONFormatter - Converts LogRecord to JSON
2. ContextVar - Stores correlation ID (async-safe)
3. log_context - Context manager for scoped IDs
4. setup_logging - Configures handlers and formatters

Flow:
logger.info("msg", extra={"key": "val"})
  → LogRecord created
  → JSONFormatter.format() called
  → Adds correlation_id from ContextVar
  → Adds custom fields from extra={}
  → Converts to JSON string
  → Handler writes to console/file
"""

import logging
import json
from datetime import datetime
from contextvars import ContextVar
from typing import Dict, Any, Optional
import uuid

# CONTEXT VARIABLES (Async-Safe Storage)
# =======================================
# 
# Problem: Thread-local storage doesn't work with async
# - asyncio uses single thread for many coroutines
# - Thread-local would share data across all coroutines
# 
# Solution: ContextVar (async-safe)
# - Each async task has own context
# - Values isolated between tasks
# - Automatically inherited by child tasks
#
# Example:
# async def task1():
#     correlation_id.set("abc")
#     await other_function()  # Sees "abc"
# 
# async def task2():
#     correlation_id.set("xyz")
#     await other_function()  # Sees "xyz"
correlation_id: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)

class JSONFormatter(logging.Formatter):
    """
    Format log records as JSON for structured logging.

    WHAT IT DOES:
    Converts Python LogRecord → JSON string
    
    LogRecord (Python object):
    {
        name: "trading_system.orders",
        levelname: "INFO",
        msg: "Order created",
        created: 1234567890.123,
        ...
    }
    
    JSON output (string):
    {
        "timestamp": "2024-01-15T10:30:00.123",
        "level": "INFO",
        "logger": "trading_system.orders",
        "message": "Order created",
        "correlation_id": "abc-123",
        "order_id": "ORDER-001"
    }
    
    WHY JSON?
    - Machine-readable (Elasticsearch, CloudWatch Insights)
    - Structured data (not just text)
    - Easy to parse and query
    - Standard format (works with all log aggregators)
    """
    def format(self, record: logging.LogRecord) -> str:
        """
        Convert LogRecord to JSON string.
        
        PROCESS:
        1. Build base log entry (timestamp, level, message)
        2. Add correlation ID from ContextVar
        3. Add exception info if present
        4. Add custom fields from logger.info(..., extra={})
        5. Convert to JSON string
        
        record.created: Unix timestamp (float)
        record.levelname: "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
        record.name: Logger name (usually module path)
        record.getMessage(): Formatted message with args
        """
        # Step 1: Build base log entry
        log_entry: Dict[str, Any] = {
            # ISO 8601 timestamp with timezone
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),

            # Log level as string
            "level": record.levelname,

            # Logger name (hierarchical: parent.child.grandchild)
            "logger": record.name,

            # The actual log message
            "message": record.getMessage(),

            # Source code location (for debugging)
            "file": record.pathname,
            "line": record.lineno,
            "function": record.funcName
        }

        # Step 2: Add correlation ID if present
        # Get from ContextVar (async-safe storage)
        corr_id = correlation_id.get()
        if corr_id:
            log_entry["correlation_id"] = corr_id

        # Step 3: Add exception info if present
        # record.exc_info is tuple: (type, value, traceback) or None
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,    # Exception class name
                "message": str(record.exc_info[1]),     # Exception message
                "traceback": self.formatException(record.exc_info)  # Full stack-trace
            }

        # Step 4: Add custom fields from extra={}
        # logger.info("msg", extra={"order_id": "123"})
        #                            ^^^^^^^^^^^^^^^^
        #                            These become record attributes
        
        # Standard LogRecord attributes (skip these)
        standard_attrs = {
            'name', 'msg', 'args', 'created', 'filename', 'funcName',
            'levelname', 'levelno', 'lineno', 'module', 'msecs',
            'message', 'pathname', 'process', 'processName',
            'relativeCreated', 'thread', 'threadName', 'exc_info',
            'exc_text', 'stack_info'
        }
    
        # Add only custom fields
        for key, value in record.__dict__.items():
            if key not in standard_attrs:
                log_entry[key] = value

        # Step 5: Convert to JSON string
        # ensure_ascii=False: Allow unicode (€, 中文, etc.)
        # default=str: Convert non-serializable objects to string
        return json.dumps(log_entry, ensure_ascii=False, default=str)
    
    
class log_context:
    """
    Context manager for scoped correlation IDs.
    
    WHAT IT DOES:
    Sets correlation ID for a block of code,
    automatically cleans up afterward.
    
    USAGE:
    with log_context(order_id="123"):
        logger.info("Processing order")  # Has correlation_id
        await process_order()
        logger.info("Order complete")     # Same correlation_id
    # correlation_id automatically cleared here
    
    WHY CONTEXT MANAGER?
    - Automatic cleanup (even if exception)
    - Scoped (doesn't affect outer code)
    - Nestable (can create sub-contexts)
    
    IMPLEMENTATION PATTERN:
    __enter__: Set up (set correlation_id)
    __exit__: Clean up (reset correlation_id)
    """

    def __init__(self, **kwargs):
        """
        Initialize context with correlation ID.
        
        Can provide:
        - correlation_id="abc-123" (use specific ID)
        - No correlation_id (generates UUID)
        - Other kwargs (stored but not used yet)
        
        Examples:
        with log_context():  # Auto-generates UUID
        with log_context(correlation_id="abc-123"):  # Use specific ID
        with log_context(request_id="req-456"):  # Future: add to logs
        """
        # Get or generate correlation ID
        self.correlation_id = kwargs.pop('correlation_id', str(uuid.uuid4()))

        # Store other context (for future use)
        self.context = kwargs

        # Token for cleanup (ContextVar.set() returns token)
        self.token = None

    def __enter__(self):
        """
        Enter context: Set correlation ID.

        Called when entering 'with' block.

        ContextVar.set() returns token:
        - Token represents previous value
        - Used later to restore(in __exit__)
        - Enables proper testing

        Example:
        # Outside: correlation_id = None
        with log_context(correlation_id="outer"):
            # Here: correlation_id = "outer"
            with log_context(correlation_id="inner"):
                # Here: correlation_id = "inner"
            # Here: correlation_id = "outer" (restored!)
        # Here: correlation_id = None (restored!)
        """
        self._token = correlation_id.set(self.correlation_id)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Exit context: Reset correlation ID.
        
        Called when exiting 'with' block.
        Runs even if exception raised inside block.
        
        Parameters (exception info):
        - exc_type: Exception class or None
        - exc_val: Exception instance or None
        - exc_tb: Traceback or None
        
        Return value:
        - False/None: Propagate exception (normal)
        - True: Suppress exception (rare)
        """
        # Reset to previous value using token
        if self._token is not None:
            correlation_id.reset(self._token)
        
        # Don't suppress exceptions (return False/None)
        return False
    
def setup_logging(
        level: str = "INFO",
        log_file: Optional[str] = None,
        json_format: bool = True
):
    """
    Configure application-wide logging.
    
    CALL ONCE at application startup:
    
    # Development
    setup_logging(level="DEBUG", json_format=False)
    
    # Production
    setup_logging(level="INFO", log_file="/var/log/app.log", json_format=True)
    
    WHAT IT CONFIGURES:
    1. Root logger level (minimum severity to capture)
    2. Formatters (JSON or text)
    3. Handlers (where logs go: console, file)
    4. Removes existing handlers (clean slate)
    
    LOG LEVELS (in order):
    DEBUG    - Detailed info for diagnosing
    INFO     - General informational messages
    WARNING  - Something unexpected but handled
    ERROR    - Error occurred, needs attention
    CRITICAL - Severe error, system may fail
    
    If level="WARNING", only WARNING/ERROR/CRITICAL are captured.
    """
    # Get root logger (parent of all loggers)
    root_logger = logging.getLogger()

    # Set minimum level
    root_logger.setLevel(level)

    # Clear existing handlers (prevents duplicates)
    root_logger.handlers = []

    # Choose formatter based on environment
    if json_format:
        # Production: JSON (machine-readable)
        formatter = JSONFormatter()
    else:
        # Development: Text (human-readable)
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    # Choose handler (stdout)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

def get_logger(name: str) -> logging.Logger:
    """
    Get logger with hierarchical name.
    
    NAMING CONVENTION:
    Use module name: __name__
    
    # In file: trading_system/orders/service.py
    logger = get_logger(__name__)
    # Creates logger: "trading_system.orders.service"
    
    HIERARCHY:
    trading_system              (root)
      └── orders                (child)
            └── service         (grandchild)
    
    BENEFITS:
    1. Can configure by level:
       logging.getLogger("trading_system.orders").setLevel("DEBUG")
       
    2. Can filter by module:
       jq '.logger | startswith("trading_system.orders")' app.log
       
    3. Clear source in logs:
       {"logger": "trading_system.orders.service", ...}
    """
    return logging.getLogger(name)
