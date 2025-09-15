"""
Symbol Value Object - Represents a trading symbol/ticker
"""

from dataclasses import dataclass

@dataclass
class Symbol:
    """
    Immutable value object representing a trading symbol.

    Examples: AAPL (Apple), MSFT (Microsoft), BRK.B (Berkshire Hathaway)
    """

    ticker: str
    
    def __post_init__(self) -> None:
        """
        Normalize and validate the ticker symbol
        
        Business rules:
        - Convert to uppercase (standard format)
        - Cannot be empty
        - Maximum 10 characters (exchange limits)
        """
        # Normalize to uppercase and remove whitespace
        normalized = self.ticker.upper().strip()

        # Validation
        if not normalized:
            raise ValueError("Symbol cannot be empty")
        
        if len(normalized) > 10:
            raise ValueError(f"Symbol too long: {normalized}")
        
        # Update the ticker with normalized value
        object.__setattr__(self, 'ticker', normalized)

    def __str__(self) -> str:
        """ String representation for display """
        return self.ticker

