"""
Debugging Techniques and Tips for Python development
"""

import logging
from typing import Any
from unittest import result

# Configure logging for debugging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def debug_with_print(data: Any) -> Any:
    """
    Simple debugging with print statements.

    Quick and dirty but effective for simple cases.
    """
    print(f"DEBUG: Type={type(data)}, Value={data}")
    return data

def debug_with_logging(order_id: str, status: str) -> None:
    """
    Better debugging with logging.

    Advantages over print:
    - Can be turned on/off with log levels
    - Includes timestamps automatically
    - Can write to files
    - Can include stack traces 
    """
    logger.debug(f"Processing order {order_id}")
    logger.info(f"Order {order_id} status changed to {status}")

    try:
        # Some operation
        result = 10 / 0
    except Exception as e:
        logger.error(f"Error processing order {order_id}", exc_info=True)


def debug_with_breakpoint():
    """
    Using Python's built-in breakpoint() function.

    Added in Python 3.7, drops into an debugger.
    """
    data = {"symbol": "AAPL", "price": 150.50}

    # This will pause execution and open debugger
    # breakpoint()  # Uncomment to use

    # In debugger, you can:
    # -p data (print variable)
    # -pp data (pretty print)
    # -l (list code)
    # -n (next line)
    # -c (continue)
    # -h (help)

    return data


def debug_with_assertions(price: float) -> float:
    """
    Using assertions for debugging.

    Assertions check conditions and raise AssertionError if false.
    Useful for catching bugs early.
    """
    # Check preconditions
    assert price > 0, f"Price must be positive, got {price}"
    assert isinstance(price, (int, float)), f"Price must be numeric, got {type(price)}"

    # Do calculation
    tax = price * 0.1
    total = price + tax

    # Check postconditions
    assert total > price, "Total should be greater than price"

    return total


# VS Code debugging shortcuts to remember:
"""
F5 - Start debugging
F10 - Step over (next line)
F11 - Step into (enter function)
Shift+F11 - Step out (exit function)
F9 - Toggle breakpoint
Shift+F5 - Stop debugging

Debugging panel shows:
- Variables: Current values in scope
- Watch: Expressions to monitor
- Call Stack: Function call hierarchy
- Breakpoints: All set breakpoints
"""