"""
Domain-specific exceptions with rich context.

Benefits over generic exceptions:
- Specific error handling
- Rich context for debugging
- Better API responses
"""

from decimal import Decimal

class TradingSystemError(Exception):
    """ Base exception for all domain errors """

    def __init__(self, message: str, code: str = None):
        super().__init__(message)
        self.code = code or self.__class__.__name__


class InsufficientFundsError(TradingSystemError):
    """ Not enough funds for operation """

    def __init__(self, required: Decimal, available: Decimal, currency: str = "USD"):
        self.required = required
        self.available = available
        self.shortfall = required - available

        message = (
            f"Insufficient funds: required {currency} {required:.2f}, "
            f"available {currency} {available:.2f}"
        )
        super().__init__(message, code="INSUFFICIENT FUNDS")


class PositionNotFoundError(TradingSystemError):
    """ Position doesn't exist """

    def __init__(self, symbol: str):
        self.symbol = symbol
        super().__init__(f"No position found for: {symbol}", code="POSITION NOT FOUND")


class InvalidQuantityError(TradingSystemError):
    """ Invalid quantity for operation """

    def __init__(self, quantity: int, reason: str):
        self.quantity = quantity
        super().__init__(f"Invalid quantity {quantity}: {reason}", code="INVALID QUANTITY")