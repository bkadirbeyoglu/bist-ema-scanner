"""
Price Value Object - Represents monetary value in our trading system.

Key Python concepts used:
1. @dataclass - Reduces boilerplate code for classes.
2. Type hints - Improves code readability and IDE support
3. __post_init__ - Validates data after initialization
4. @property - Creates read-only attributes
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Union


@dataclass(frozen=True)  # frozen=True makes the instance immutable
class Price:
    """
    Immutable value object representing a price.

    Why use @dataclass?
    - Automatically generates __init__, __repr__, __eq__ methods.
    - Reduces boilerplate code significantly
    - frozen=True ensures immutability (can't change after creation)

    Why use Decimal instead of float?
    - Float has precison issues (0.1 + 0.2 != 0.3 in float)
    - Decimal provides exact decimal arithmetic
    - Critical for financial calculations
    """

    value: Decimal  # Type hint: tells Python and IDEs this should be a Decimal

    def __post_init__(self):
        """
        Called automatically after __init__ by dataclass.
        Used for validation and type conversion.

        Why __post_init__?
        - Dataclass already created __init__ for us
        - We need additional validation/conversion logic
        - Runs after the object is initialized
        """
        # Convert to Decimal if needed (handles int, float, string inputs)
        if not isinstance(self.value, Decimal):
            # object.__setattr__ used because dataclass is frozen (immutable)
            # This is the only way to set attributes in a frozen dataclass
            object.__setattr__(self, "value", Decimal(str(self.value)))

        # Validate: prices can't be negative
        if self.value < 0:
            raise ValueError(f"Price cannot be negative: {self.value}")

    def __str__(self):
        """
        User-friendly string representation.
        Called by str(price) or print(price)

        Why override __str__?
        - Provides human-readable output
        - Better than default object representation
        """
        return f"${self.value:.2f}"
    
    def add(self, other: 'Price') -> 'Price':
        """
        Add two prices together, returning a new Price

        Why not modify self?
        - Value objects should be immutable
        - Operations return new instances
        - Prevents unexpected side effects
        """
        if not isinstance(other, Price):
            raise TypeError(f"Cannot add Price and {type(other).__name__}")
        return Price(self.value + other.value)
    
    def multiply(self, scalar: Union[int, float]) -> 'Price':
        """
        Multiply price by a scalar (for quantity calculations)

        Union[int, float] means the parameter can be either int or float.
        Type hints help IDEs provide better autocomplete and catch errors
        """

        return Price(self.value * Decimal(str(scalar)))
    
    @property  # Makes this method accessible like an attribute: price.as_float
    def as_float(self) -> float:
        """
        Get price as float (for APIs that require float )

        @property decorator:
        - Makes method accessible without parentheses
        - Read-only attribute (no setter defined)
        - Useful for computed values
        """
        return float(self.value)
    