"""
Production-grade Money value object with showcasing Python best practices.

This implementation demonstrates:
1. @dataclass for reduced boilerplate
2. Immutability with frozen=True
3. Operator overloading for natural syntax
4. Properties for computed values
5. Type hints for better tooling
6. Class methods for alternative constructors
"""

from dataclasses import dataclass
from decimal import Decimal, getcontext, ROUND_HALF_UP
from typing import Union, ClassVar
from functools import total_ordering

# MODULE-LEVEL DECIMAL CONFIGURATION
# Affects all Decimal operations in this module
getcontext().prec = 28  # Sufficient for any financial calculation
getcontext().rounding = ROUND_HALF_UP  # Standard for finance

@total_ordering     # Generates all comparisons from __eq__ and __lt__
@dataclass(frozen=True)
class Money:
    """ 
    Immutable Money value object with complete operator support.

    DESIGN DECISIONS:
    1. Why immutable (frozen=True)?
        - Thread-safe without locks
        - Can be used as dict keys
        - Prevents accidental modification
        - Follows value object pattern

    2. Why operator overloading?
        - Nautal syntax: total = price + tax + shipping
        - Reduces errors from method confusion
        - Follows Python conventions

    3. Why Decimal over float?
        - Exact decimal representation
        - Configurable precision
        - Required for compliance
    """

    # INSTANCE ATTRIBUTES with type hints
    amount: Decimal
    currency: str = "USD"  # Default parameter

    # CLASS VARIABLE: Shared across all instances
    # ClassVar tells type checkers this isn't an instance attribute
    SUPPORTED_CURRENCIES: ClassVar[set[str]] = {"USD", "EUR", "GBP", "TRY"}

    def __post_init__(self) -> None:
        """ 
        Post-initialization validation and normalization.

        Called automatically after __init__ by dataclass.
        This is where we enforce business rules.
        """
        # Ensure Decimal type (convert if needed)
        if not isinstance(self.amount, Decimal):
            # ALWAYS convert through string to preserve precision
            object.__setattr__(self, 'amount', Decimal(str(self.amount)))

        # Normalize currency to uppercase
        normalized_currency = self.currency.upper()
        object.__setattr__(self, 'currency', normalized_currency)

        # Validate currency
        if normalized_currency not in self.SUPPORTED_CURRENCIES:
            raise ValueError(f"Unsupported currency: {normalized_currency}. "
                                f"Supported: {', '.join(sorted(self.SUPPORTED_CURRENCIES))}")
        
        # Apply currency-specific precision
        if normalized_currency == "JPY":
            # Japanese Yen has no fractional units
            precision = Decimal("1")
        else:
            # Most currencies have 2 decimal places
            precision = Decimal("0.01")

        # quantize() rounds to specified precision
        quantized = self.amount.quantize(precision)
        object.__setattr__(self, 'amount', quantized)

    # ====================== ARITHMETIC OPERATORS ======================

    def __add__(self, other: 'Money') -> 'Money':
        """
        Addition: money1 + money2

        Makes financial calculations natural and readable.
        """
        if not isinstance(other, Money):
            return NotImplemented       # Let Python try other.__radd__
            
        if self.currency != other.currency:
            raise ValueError("Cannot add different currencies: ")
                                 
        return Money(self.amount + other.amount, self.currency)

    def __radd__(self, other: Union['Money', int]) -> 'Money':
        """ Right addition: Enables sum([money1, money2, money3]) 
            
        Python's sum() starts with 0, so we handle that case.    
        """
        if other == 0:   # Support sum() function
            return self
        return self.__add__(other)
        
    def __sub__(self, other: 'Money') -> 'Money':
        """ Subtraction: money1 - money2 """
        if not isinstance(other, Money):
            return NotImplemented
            
        if self.currency != other.currency:
            raise ValueError("Cannot subtract different currencies.")

        return Money(self.amount - other.amount, self.currency)

    def __mul__(self, scalar: Union[int, float, Decimal]) -> 'Money':
        """ Multiplication: money * quantity """
        if isinstance(scalar, (int, float, Decimal)):
            return Money(self.amount * Decimal(str(scalar)), self.currency)
        return NotImplemented

    def __rmul__(self, scalar: Union[int, float, Decimal]) -> 'Money':
        """ Right multiplication: quantity * money """
        return self.__mul__(scalar)
    
    def __truediv__(self, divisor: Union[int, float, Decimal, 'Money']) -> Union['Money', Decimal]:
        """
        Division with context-dependent return type:
        - money / scalar -> Money
        - money / money -> Decimal (dimensionless ratio)
        """
        if isinstance(divisor, Money):
            if self.currency != divisor.currency:
                raise ValueError("Cannot divide different currencies")
            return self.amount / divisor.amount     # Returns decimal
        elif isinstance(divisor, (int, float, Decimal)):
            if divisor == 0:
                raise ZeroDivisionError()
            return Money(self.amount / Decimal(str(divisor)), self.currency)
            
        return NotImplemented
        

    # ====================== COMPARISON OPERATORS ======================
    def __eq__(self, other: object) -> bool:
        """ Equality based on value, not identity """
        if not isinstance(other, Money):
            return False
        return self.amount == other.amount and self.currency == other.currency
        
    def __lt__(self, other: 'Money') -> bool:
        """ Less than (other comparisons generated by @total_ordering)"""
        if not isinstance(other, Money):
            return NotImplemented
            
        if self.currency != other.currency:
            raise ValueError("Cannot compare different currencies")
            
        return self.amount < other.amount
        
    def __hash__(self) -> int:
        """ Hash for use in sets/dicts """
        return hash((self.amount, self.currency))
        

    # ====================== PROPERTIES ======================

    @property
    def is_positive(self) -> bool:
        """ Check if positive - accessed like attribute, not method """
        return self.amount > 0
        
    @property
    def is_negative(self) -> bool:
        return self.amount < 0
        
    @property
    def is_zero(self) -> bool:
        return self.amount == 0
        
    # ====================== CLASS METHODS ======================

    @classmethod
    def zero(cls, currency: str = "USD") -> 'Money':
        """ Factory method for zero money """
        return cls(Decimal("0"), currency)
        
    def __str__(self) -> str:
        """ User-friendly representation """
        if self.currency == "USD":
            return f"${self.amount:,.2f}"
        if self.currency == "EUR":
               return f"€{self.amount:,.2f}"
        if self.currency == "GBP":
            return f"£{self.amount:,.2f}"
        if self.currency == "TRY":
            return f"₺{self.amount:,.2f}"

    def __repr__(self):
        """ Developer-friendly representation """
        return f"Money(Decimal('{self.amount}'), '{self.currency}')"