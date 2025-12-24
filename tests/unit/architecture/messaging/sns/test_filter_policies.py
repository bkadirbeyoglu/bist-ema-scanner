"""
Unit tests for SNS Filter Policy builders.

Tests the fluent builder API for creating SNS filter policies.
"""

import pytest

from trading_system.architecture.messaging.sns.filter_policies import FilterPolicyBuilder


class TestFilterPolicyBuilder:
    """Tests for FilterPolicyBuilder."""

    def test_exact_match_single_value(self) -> None:
        """Test filtering for exact string match."""
        policy = (
            FilterPolicyBuilder()
            .exact_match("symbol", "AAPL")
            .build()
        )

        assert policy == {"symbol": ["AAPL"]}

    def test_exact_match_multiple_values(self) -> None:
        """Test filtering for any of multiple values (OR logic)."""
        policy = (
            FilterPolicyBuilder()
            .exact_match("symbol", "AAPL", "GOOGL", "MSFT")
            .build()
        )

        assert policy == {"symbol": ["AAPL", "GOOGL", "MSFT"]}

    def test_prefix_match(self) -> None:
        """Test filtering by string prefix."""
        policy = (
            FilterPolicyBuilder()
            .prefix("symbol", "US-")
            .build()
        )

        assert policy == {"symbol": [{"prefix": "US-"}]}

    def test_numeric_range(self) -> None:
        """Test filtering by numeric range."""
        policy = (
            FilterPolicyBuilder()
            .numeric_range("price", gte=100, lt=200)
            .build()
        )

        # SNS uses a specific format for numeric comparisons
        expected = {"price": [{"numeric": [">=", 100, "<", 200]}]}
        assert policy == expected

    def test_numeric_greater_than(self) -> None:
        """Test filtering for values above threshold."""
        policy = (
            FilterPolicyBuilder()
            .numeric_range("price", gt=100)
            .build()
        )

        assert policy == {"price": [{"numeric": [">", 100]}]}

    def test_exists_true(self) -> None:
        """Test filtering for attribute existence."""
        policy = (
            FilterPolicyBuilder()
            .exists("high_priority", True)
            .build()
        )

        assert policy == {"high_priority": [{"exists": True}]}

    def test_anything_but(self) -> None:
        """Test filtering to exclude specific values."""
        policy = (
            FilterPolicyBuilder()
            .anything_but("symbol", "TEST", "DEMO")
            .build()
        )

        assert policy == {"symbol": [{"anything-but": ["TEST", "DEMO"]}]}

    def test_combined_filters_use_and_logic(self) -> None:
        """Test that multiple filters combine with AND logic."""
        policy = (
            FilterPolicyBuilder()
            .exact_match("symbol", "AAPL")
            .exact_match("event_type", "PriceUpdatedEvent")
            .build()
        )

        assert policy == {
            "symbol": ["AAPL"],
            "event_type": ["PriceUpdatedEvent"],
        }

    def test_or_values_within_same_attribute(self) -> None:
        """
        Test OR logic within a single attribute.
        
        Multiple values for the same attribute means "match ANY of these".
        """
        policy = (
            FilterPolicyBuilder()
            .exact_match("event_type", "OrderCreatedEvent", "OrderFilledEvent")
            .build()
        )

        assert policy == {
            "event_type": ["OrderCreatedEvent", "OrderFilledEvent"],
        }

    def test_chained_builder_returns_same_instance(self) -> None:
        """Verify builder methods return self for chaining."""
        builder = FilterPolicyBuilder()

        result = builder.exact_match("symbol", "AAPL")

        assert result is builder

    def test_empty_policy(self) -> None:
        """Test that empty builder produces empty policy (no filtering)."""
        policy = FilterPolicyBuilder().build()

        assert policy == {}