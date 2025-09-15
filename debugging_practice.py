"""
Practice debugging with these intentionally buggy examples.
Set breakpoints and step through to find the issues.
"""

from decimal import Decimal
from typing import List, Optional


# Bug 1: Mutable default argument
class Portfolio:
    """
    BUG: Default mutable argument causes shared state!

    Debugging steps:
    1. Set breakpoint on line: def __init__
    2. Create two Portfolio instances
    3. Add poition to first portfolio
    4. Check second portfolio - it has the position too!

    Why does this happen?
    - Default arguments are evaluated once when the function is defined
    - All instances share the same list object
    """

    def __init__(self, positions: List[str] = []):      # BUG HERE!
        self.positions = positions

    def add_position(self, symbol: str):
        self.positions.append(symbol)

# FIXED VERSION
class PortfolioFixed:
    """ Fixed version using None as default """
    def __init__(self, positions: Optional[List[str]] = None):
        # Create new list if None provided
        self.positions = positions if positions is not None else []

    def add_position(self, symbol: str):
        self.positions.append(symbol)


# BUG 2: Integer division instead of float
def calculate_average_price(prices: List[Decimal]) -> Decimal:
    """
    BUG: Integer division loses precision'

    Debugging:
    1. Set breakpoint on return statement
    2. Check values of total and count
    3. Step through and see result
    """
    total = sum(prices)
    count = len(prices)

    # BUG: Using // (integer division) instead of /
    return total // count   # Should be / not //


# BUG 3: Modifying list while iterating
def remove_cancelled_orders(orders: List[dict]) -> List[dict]:
    """
    BUG: Modifying list while iterating causes skipped elements!

    Debugging:
    1. Set breakpoint inside loop
    2. Watch how index changes as items are removed
    3. Notice some items are skipped
    """

    for i, order in enumerate(orders):
        if order['status'] == 'CANCELLED':
            orders.remove(order)    # BUG: Modifying list being iterated!

    return orders

# FIXED VERSION
def remove_cancelled_orders_fixed(orders: List[dict]) -> List[dict]:
    """ Fixed version using list comprehension """
    # Create new list instead of modifying original
    return [order for order in orders if order['status'] != 'CANCELLED']


# BUG 4: Variable scope issue
def process_trades(trades: List[dict]) -> dict:
    """
    BUG: Variable defined inside conditional might not exist!

    Debugging:
    1. Set breakpoint at return statement
    2. Run with empty trade list
    3. See NameError: 'result' is not defined
    """
    for trade in trades:
        if trade['status'] == 'EXECUTED':
            result = {'total': trade['amount']}     # Only defined if condition met

    return result       # BUG: result might not be defined!

# FIXED VERSION
def process_trades_fixed(trades: List[dict]) -> dict:
    """ Fixed version with proper initialization """
    result = {'total': 0}       # Initialize before loop

    for trade in trades:
        if trade['status'] == 'EXECUTED':
            result['total'] += trade['amount']

    return result


# Test the bugs
def test_debugging_examples():
    """ Run this to see the bugs in action """

    print("Testing Bug 1: Mutable default argument")
    p1 = Portfolio()
    p2 = Portfolio()
    p1.add_position("AALP")
    print(f"P1 positions: {p1.positions}")
    print(f"P2 positions: {p2.positions}")      # Oops! P2 has AAPL too!

    print("\nTesting Bug 2: Integer division")
    prices = [Decimal('100'), Decimal('101'), Decimal('103')]
    avg = calculate_average_price(prices)
    print(f"Average price: {avg}")              # Should be 101.33, but shows 101

    print("\nTesting Bug 3: Modifying list while iterating")
    orders = [
        {'id': 1, 'status': 'FILLED'},
        {'id': 2, 'status': 'CANCELLED'},
        {'id': 3, 'status': 'CANCELLED'},
        {'id': 4, 'status': 'PENDING'},
    ]
    result = remove_cancelled_orders(orders.copy())
    print(f"Remaining orders: {result}")        # Might have unexpected results

    print("\nTesting Bug 4: Variable scope")
    try:
        trades = []     # Empty list
        result = process_trades(trades)
        print(f"Result: {result}")
    except NameError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_debugging_examples()