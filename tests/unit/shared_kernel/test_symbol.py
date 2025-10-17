""" Tests for Symbol value object """

import pytest
from trading_system.shared_kernel.value_objects.symbol import Symbol


class TestSymbol:
    """ Test suite for Symbol value object """

    def test_symbol_creation(self):
        """ Test creating a valid symbol """
        symbol = Symbol("AAPL")
        assert symbol.ticker == "AAPL"
        assert str(symbol) == "AAPL"

    def test_symbol_normalization(self):
        """ Test that symbols are normalized to uppercase """
        symbol = Symbol("aapl")
        assert symbol.ticker == "AAPL" # Should be uppercase

    def test_symbol_validation(self):
        """ Test symbopl validation rules """
        # Valid symbols
        Symbol("AAPL")  # Normal ticker
        Symbol("BRK.B") # Ticker with dot (Berkshire Hathaway Class B)

        # Invalid symbols
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            Symbol("")

        with pytest.raises(ValueError, match="Symbol too long"):
            Symbol("VERYLONGTICKERSYMBOL")

        

        
