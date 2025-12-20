"""
Configuration for Paper Trading Service.

Uses pydantic-settings to load configuration from environment
variables with sensible defaults.
"""

from pydantic_settings import BaseSettings
from pydantic_settings import SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    Environment variables are prefixed with PAPER_TRADING_.
    Example: PAPER_TRADING_API_PORT=8002
    """
    
    # ========================================================================
    # DEFAULT TRADING SETTINGS (from Session 1)
    # ========================================================================
    default_initial_cash: float = 100000.0
    default_commission: float = 1.0
    default_slippage_percent: float = 0.0005
    
    # ========================================================================
    # API SETTINGS (Session 2)
    # ========================================================================
    api_host: str = "0.0.0.0"
    api_port: int = 8002
    cors_origins: list[str] = ["*"]  # In production, restrict this!
    
    # ========================================================================
    # SQS SETTINGS (Session 2 - Part 4)
    # ========================================================================
    sqs_endpoint_url: str = "http://localhost:4566"
    sqs_region: str = "us-east-1"
    signal_queue_name: str = "trading-signals"
    sqs_enabled: bool = True  # Set to False to disable SQS consumer
    
    # ========================================================================
    # PYDANTIC SETTINGS CONFIGURATION
    # ========================================================================
    model_config = SettingsConfigDict(
        env_prefix="PAPER_TRADING_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
    )