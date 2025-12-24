"""
SNS Filter Policy Builder.

Provides a fluent API for building SNS filter policies.
Filter policies allow subscribers to receive only messages
that match specific criteria, reducing unnecessary processing.
"""

from typing import Any
from typing import Self


class FilterPolicyBuilder:
    """
    Fluent builder for SNS filter policies.
    
    SNS filter policies are JSON documents that specify which messages
    a subscriber should receive. This builder provides a clean API
    for constructing these policies.
    
    Example:
        policy = (
            FilterPolicyBuilder()
            .exact_match("symbol", "AAPL", "GOOGL")
            .exact_match("event_type", "PriceUpdatedEvent")
            .build()
        )
        
        # Result:
        # {
        #     "symbol": ["AAPL", "GOOGL"],
        #     "event_type": ["PriceUpdatedEvent"]
        # }
    
    Logic Rules:
    - Multiple values for SAME attribute → OR (match any)
    - Multiple attributes → AND (must match all)
    """

    def __init__(self) -> None:
        """Initialize empty policy."""
        self._policy: dict[str, list[Any]] = {}

    def exact_match(self, attribute: str, *values: str) -> Self:
        """
        Filter for exact string matches.
        
        Args:
            attribute: The message attribute to filter on
            *values: One or more values to match (OR logic)
            
        Returns:
            Self for method chaining
            
        Example:
            .exact_match("symbol", "AAPL")  # Match AAPL
            .exact_match("symbol", "AAPL", "GOOGL")  # Match AAPL OR GOOGL
        """
        self._policy[attribute] = list(values)
        return self

    def prefix(self, attribute: str, prefix_value: str) -> Self:
        """
        Filter for strings starting with a prefix.
        
        Args:
            attribute: The message attribute to filter on
            prefix_value: The prefix to match
            
        Returns:
            Self for method chaining
            
        Example:
            .prefix("symbol", "US-")  # Match US-AAPL, US-GOOGL, etc.
        """
        self._policy[attribute] = [{"prefix": prefix_value}]
        return self

    def numeric_range(
        self,
        attribute: str,
        *,
        gt: float | None = None,
        gte: float | None = None,
        lt: float | None = None,
        lte: float | None = None,
    ) -> Self:
        """
        Filter for numeric values in a range.
        
        Args:
            attribute: The message attribute to filter on
            gt: Greater than (exclusive)
            gte: Greater than or equal (inclusive)
            lt: Less than (exclusive)
            lte: Less than or equal (inclusive)
            
        Returns:
            Self for method chaining
            
        Example:
            .numeric_range("price", gte=100, lt=200)  # 100 <= price < 200
            .numeric_range("quantity", gt=0)  # quantity > 0
            
        Note:
            Only one of gt/gte and one of lt/lte should be used.
        """
        conditions: list[Any] = []

        if gt is not None:
            conditions.extend([">", gt])
        elif gte is not None:
            conditions.extend([">=", gte])

        if lt is not None:
            conditions.extend(["<", lt])
        elif lte is not None:
            conditions.extend(["<=", lte])

        self._policy[attribute] = [{"numeric": conditions}]
        return self

    def exists(self, attribute: str, should_exist: bool = True) -> Self:
        """
        Filter based on attribute existence.
        
        Args:
            attribute: The message attribute to check
            should_exist: True to require attribute, False to require absence
            
        Returns:
            Self for method chaining
            
        Example:
            .exists("high_priority", True)  # Only messages with high_priority
            .exists("test_flag", False)  # Only messages WITHOUT test_flag
        """
        self._policy[attribute] = [{"exists": should_exist}]
        return self

    def anything_but(self, attribute: str, *excluded_values: str) -> Self:
        """
        Filter to EXCLUDE specific values.
        
        Args:
            attribute: The message attribute to filter on
            *excluded_values: Values to exclude
            
        Returns:
            Self for method chaining
            
        Example:
            .anything_but("symbol", "TEST", "DEMO")  # Exclude test symbols
        """
        self._policy[attribute] = [{"anything-but": list(excluded_values)}]
        return self

    def suffix(self, attribute: str, suffix_value: str) -> Self:
        """
        Filter for strings ending with a suffix.
        
        Args:
            attribute: The message attribute to filter on
            suffix_value: The suffix to match
            
        Returns:
            Self for method chaining
            
        Example:
            .suffix("email", "@company.com")  # Match internal emails
        """
        self._policy[attribute] = [{"suffix": suffix_value}]
        return self

    def build(self) -> dict[str, list[Any]]:
        """
        Build and return the filter policy.
        
        Returns:
            The complete filter policy dictionary
        """
        return self._policy.copy()


# =============================================================================
# Pre-built Filter Policies for Common Use Cases
# =============================================================================

class TradingFilters:
    """
    Pre-built filter policies for common trading scenarios.
    
    These provide ready-to-use filters for typical subscription patterns.
    """

    @staticmethod
    def price_updates_for_symbols(*symbols: str) -> dict[str, list[Any]]:
        """
        Filter for price updates of specific symbols.
        
        Args:
            *symbols: Stock symbols to receive updates for
            
        Returns:
            Filter policy dict
        """
        return (
            FilterPolicyBuilder()
            .exact_match("event_type", "PriceUpdatedEvent")
            .exact_match("symbol", *symbols)
            .build()
        )

    @staticmethod
    def all_order_events() -> dict[str, list[Any]]:
        """
        Filter for all order-related events.
        
        Returns:
            Filter policy dict
        """
        return (
            FilterPolicyBuilder()
            .exact_match(
                "event_type",
                "OrderCreatedEvent",
                "OrderFilledEvent",
                "OrderCancelledEvent",
                "OrderRejectedEvent",
            )
            .build()
        )

    @staticmethod
    def exclude_test_symbols() -> dict[str, list[Any]]:
        """
        Filter to exclude test/demo symbols.
        
        Returns:
            Filter policy dict
        """
        return (
            FilterPolicyBuilder()
            .anything_but("symbol", "TEST", "DEMO", "SANDBOX", "PAPER")
            .build()
        )

    @staticmethod
    def high_value_orders(min_value: float) -> dict[str, list[Any]]:
        """
        Filter for orders above a value threshold.
        
        Args:
            min_value: Minimum order value
            
        Returns:
            Filter policy dict
        """
        return (
            FilterPolicyBuilder()
            .exact_match("event_type", "OrderFilledEvent")
            .numeric_range("trade_value", gte=min_value)
            .build()
        )

    @staticmethod
    def signals_for_strategy(strategy_id: str) -> dict[str, list[Any]]:
        """
        Filter for signals from a specific strategy.
        
        Args:
            strategy_id: The strategy to receive signals from
            
        Returns:
            Filter policy dict
        """
        return (
            FilterPolicyBuilder()
            .exact_match("event_type", "SignalGeneratedEvent")
            .exact_match("strategy_id", strategy_id)
            .build()
        )