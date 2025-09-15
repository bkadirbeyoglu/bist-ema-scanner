"""
Test-Driven Development: We write tests BEFORE implementation.
This is the RED phase - tests will fail initially, and that's expected!
"""

from decimal import Decimal
import pytest

# These imports will fail initially - that's the TDD way
from trading_system.domain.value_objects.price import Price


class TestPrice:
    """ Test suite for Price value object """
    def test_price_creation_with_valid_value(self):
        """ Test that we can create a price with a valid decimal value """
        # Arrange & Act
        price = Price(Decimal("100.50"))

        # Assert
        assert price.value == Decimal("100.50")
        assert str(price) == "$100.50"

    def test_price_immutability(self):
        """ 
        Test that price is immutable (cannot be changed after creation).
        This is important for value objects - they should be immutable.
        """
        price = Price(Decimal("100.50"))

        # Trying to change the value should raise an error
        with pytest.raises(AttributeError):
            price.value = Decimal("200.00")

    def test_price_equality(self):
        """ 
        Test that two prices with the same value are equal.
        Value objects are defined by their values, not by identity. 
        """
        price1 = Price(Decimal("100.50"))
        price2 = Price(Decimal("100.50"))
        price3 = Price(Decimal("100.51"))

        assert price1 == price2     # Same value = equal
        assert price1 != price3     # Different value = not equal

    def test_price_cannot_be_negative(self):
        """ Test that price validates and rejects negative values """
        with pytest.raises(ValueError, match="Price cannot be negative"):
            Price(Decimal("-10.00"))

    def test_price_accepts_different_types(self):
        """ Test that price can be created from int, float, or string """
        price_from_int = Price(100)
        price_from_float = Price(100.50)
        price_from_string = Price("100.50")
        
        assert price_from_int.value == Decimal("100")
        assert price_from_float.value == Decimal("100.50")
        assert price_from_string.value == Decimal("100.50")