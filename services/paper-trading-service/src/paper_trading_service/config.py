"""
Paper Trading Service Configuration.
"""

from decimal import Decimal
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Service configuration from environment variables."""
    
    model_config = SettingsConfigDict(
        env_prefix="PAPER_TRADING_",
        env_file=".env",
        case_sensitive=False,
    )
    
    # Service identity
    service_name: str = "paper-trading-service"
    
    # Trading defaults
    default_initial_cash: Decimal = Decimal("100000.00")
    default_slippage_bps: int = 5
    default_commission_per_share: Decimal = Decimal("0.005")
    min_commission: Decimal = Decimal("1.00")
    
    # Memory limits
    max_journal_entries: int = 10000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance (singleton pattern)."""
    return Settings()