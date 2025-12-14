"""
Order Service Configuration.

Uses pydantic-settings for environment variable loading.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Order Service settings loaded from environment variables.
    
    All settings can be overridden via environment variables.
    Prefix: ORDER_ (e.g., ORDER_PORT=8002)
    """

    # Service Identity
    service_name: str = "order-service"
    version: str = "1.0.0"
    environment: Literal["development", "staging", "production"] = "development"

    # Server configuration
    host: str = "0.0.0.0"
    port: int = 8002        # Different from market-data-service (8001)

    # AWS/LocalStack configuration
    aws_region: str = "us-east-1"
    aws_endpoint_url: str = "http://localstack:4566"
    aws_access_key_id: str = "test"
    aws_secret_acces_key: str = "test"

    # SQS queue names
    sqs_order_evetns_queue: str = "order-events"
    sqs_market_data_queue: str = "market-data-prices"

    # Service URLs (for HTTP calls between services)
    market_data_service_url: str = "http://market-data-service:8001"

    # Saga configuration
    saga_timeout_seconds: int = 30
    saga_max_retries: int = 3

    # Logging
    log_level: str = "INFO"

    class Config:
        """Pydantic configuration"""
        env_prefix = "ORDER_"
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance (singleton pattern).

    Using @lru_cache makes this a singleton - same instance returned on every call. 
    Clear with get_settings.cache_clear() in tests.
    """
    return Settings()


