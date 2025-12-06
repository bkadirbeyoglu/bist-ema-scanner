"""
Market Data Service Configuration.

Loads settings from environment variables using pydantic-settings.
See DEEP DIVE section at end of file for detailed explanations.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Literal
from functools import lru_cache


class Settings(BaseSettings):
    """
    Service configuration loaded automatically from environment variables.
    
    Example:
        $ export MARKET_DATA_PORT=9000
        $ python -c "from config import get_settings; print(get_settings().port)"
        9000  # Environment overrides default!
    """
    
    # ──────────────────────────────────────────────────────────────────────────
    # Service Identity
    # ──────────────────────────────────────────────────────────────────────────
    
    service_name: str = Field(
        default="market-data-service",
        description="Service identifier for logging and discovery"
    )
    
    service_version: str = Field(
        default="1.0.0",
        description="Semantic version of the service"
    )
    
    # Literal restricts to specific values - see DEEP DIVE below
    environment: Literal["development", "staging", "production"] = Field(
        default="development",
        description="Deployment environment"
    )
    
    # ──────────────────────────────────────────────────────────────────────────
    # Server Configuration
    # ──────────────────────────────────────────────────────────────────────────
    
    host: str = Field(
        default="0.0.0.0",
        description="Host to bind the server to"
    )
    
    port: int = Field(
        default=8001,
        ge=1,       # ge = "greater than or equal to"
        le=65535,   # le = "less than or equal to"
        description="Port number for the service (different from main API!)"
    )
    
    # ──────────────────────────────────────────────────────────────────────────
    # AWS/SQS Configuration
    # ──────────────────────────────────────────────────────────────────────────
    
    aws_region: str = Field(
        default="us-east-1",
        description="AWS region for SQS"
    )
    
    # str | None is Python 3.10+ syntax for Optional[str]
    aws_endpoint_url: str | None = Field(
        default="http://localstack:4566",
        description="LocalStack endpoint for development. None for real AWS."
    )
    
    sqs_price_queue_name: str = Field(
        default="market-data-prices",
        description="SQS queue name for price updates"
    )
    
    # ──────────────────────────────────────────────────────────────────────────
    # Data Source Configuration
    # ──────────────────────────────────────────────────────────────────────────
    
    data_source: Literal["mock", "alpha_vantage", "yahoo"] = Field(
        default="mock",
        description="Which data source to use for prices"
    )
    
    alpha_vantage_api_key: str | None = Field(
        default=None,
        description="Alpha Vantage API key (required if data_source='alpha_vantage')"
    )
    
    price_update_interval_ms: int = Field(
        default=1000,
        ge=100,
        le=60000,
        description="How often to fetch/generate price updates (milliseconds)"
    )
    
    # ──────────────────────────────────────────────────────────────────────────
    # Logging Configuration
    # ──────────────────────────────────────────────────────────────────────────
    
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO",
        description="Logging verbosity level"
    )
    
    log_json: bool = Field(
        default=True,
        description="Output logs as JSON (production) or plain text (development)"
    )
    
    # ──────────────────────────────────────────────────────────────────────────
    # Pydantic Settings Configuration
    # ──────────────────────────────────────────────────────────────────────────
    
    model_config = SettingsConfigDict(
        env_prefix="MARKET_DATA_",  # MARKET_DATA_PORT, MARKET_DATA_LOG_LEVEL, etc.
        env_file=".env",            # Also load from .env file
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"              # Don't fail on unknown env vars
    )
    
    # Helper methods
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.environment == "development"
    
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment == "production"


@lru_cache()
def get_settings() -> Settings:
    """
    Get cached settings instance (singleton pattern).
    
    First call creates Settings, subsequent calls return cached instance.
    Use get_settings.cache_clear() in tests to reset.
    """
    return Settings()


# ══════════════════════════════════════════════════════════════════════════════
# DEEP DIVE: Understanding the Python Features Used Above
# ══════════════════════════════════════════════════════════════════════════════
#
# This section explains the NEW Python features introduced in this file.
# Skip if you're comfortable with them, or read for deeper understanding.
#
# ──────────────────────────────────────────────────────────────────────────────
# FEATURE 1: pydantic-settings (BaseSettings)
# ──────────────────────────────────────────────────────────────────────────────
#
# pydantic-settings is a SEPARATE package from pydantic (install separately).
# It provides BaseSettings, which AUTOMATICALLY loads values from environment.
#
# COMPARISON WITH pydantic.BaseModel:
# ┌─────────────────────────────────────────────────────────────────────────────┐
# │                                                                             │
# │  pydantic.BaseModel                  pydantic_settings.BaseSettings         │
# │  ─────────────────────               ────────────────────────────────       │
# │                                                                             │
# │  class User(BaseModel):              class Settings(BaseSettings):          │
# │      name: str                           port: int = 8000                   │
# │      age: int                                                               │
# │                                      # If MARKET_DATA_PORT=9000 in env:     │
# │  u = User(name="Alice", age=30)      s = Settings()                         │
# │  # You MUST pass data explicitly     # port is 9000, loaded automatically!  │
# │                                                                             │
# │  USE FOR:                            USE FOR:                               │
# │  • API request/response schemas      • Application configuration            │
# │  • Database models                   • Secrets (API keys, passwords)        │
# │  • Data transfer objects             • Environment-specific settings        │
# │                                                                             │
# └─────────────────────────────────────────────────────────────────────────────┘
#
# HOW ENVIRONMENT LOADING WORKS:
#
#   1. Field name: port
#   2. Convert to uppercase: PORT
#   3. Add prefix (if configured): MARKET_DATA_PORT
#   4. Check environment for MARKET_DATA_PORT
#   5. If found, use it; otherwise use default
#
# VALIDATION AT STARTUP:
#
#   settings = Settings()  # ← All validation happens HERE
#
#   If MARKET_DATA_PORT="not_a_number":
#   ValidationError: Input should be a valid integer
#
#   This "fail fast" catches config errors at startup, not at runtime!
#
# ──────────────────────────────────────────────────────────────────────────────
# FEATURE 2: Literal Type Hint
# ──────────────────────────────────────────────────────────────────────────────
#
# Literal restricts a variable to SPECIFIC values (not just any str/int).
#
# WITHOUT Literal:
#   environment: str = "development"
#   environment = "developmnet"  # Typo - no error!
#   environment = "banana"       # Nonsense - no error!
#
# WITH Literal:
#   environment: Literal["development", "staging", "production"]
#   environment = "developmnet"  # Type checker ERROR!
#   environment = "banana"       # Pydantic ValidationError at runtime!
#
# USE CASES:
# • Configuration modes (dev/staging/prod)
# • Status fields ("pending", "completed", "failed")
# • Log levels ("DEBUG", "INFO", "WARNING", "ERROR")
# • Any field with a known, fixed set of valid values
#
# ──────────────────────────────────────────────────────────────────────────────
# FEATURE 3: @lru_cache() for Singleton Pattern
# ──────────────────────────────────────────────────────────────────────────────
#
# @lru_cache() memoizes function results. Since get_settings() has NO arguments,
# it caches the single result forever → singleton pattern!
#
# EXECUTION FLOW:
#
#   # First call:
#   settings = get_settings()
#   # 1. Check cache → empty
#   # 2. Call function → Settings() created
#   # 3. Store in cache
#   # 4. Return Settings instance
#
#   # Second call:
#   settings = get_settings()
#   # 1. Check cache → found!
#   # 2. Return cached instance (function body NEVER runs again)
#
# WHY USE THIS OVER CLASS-BASED SINGLETON?
#
#   # Class-based singleton (verbose, error-prone):
#   class Settings:
#       _instance = None
#       def __new__(cls):
#           if cls._instance is None:
#               cls._instance = super().__new__(cls)
#           return cls._instance
#
#   # @lru_cache singleton (simple, Pythonic):
#   @lru_cache()
#   def get_settings() -> Settings:
#       return Settings()
#
# BENEFITS:
# • Simpler code
# • Works with FastAPI's Depends() for dependency injection
# • Thread-safe by default
# • Easy to reset in tests: get_settings.cache_clear()
#
# ══════════════════════════════════════════════════════════════════════════════