"""
Notification Service configuration.

Uses pydantic-settings for environment-based configuration
with validation and type coercion.
"""

from functools import lru_cache
from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict


# =============================================================================
# Constants - Domain knowledge that doesn't change per environment
# =============================================================================
# These are Final because they're architectural decisions, not configuration.
# Using Final[str] tells type checkers these should never be reassigned.

SERVICE_NAME: Final[str] = "notification-service"

# Queue name - must match what init-aws.sh creates
SQS_QUEUE_NOTIFICATIONS: Final[str] = "notifications"

# SNS topic name - must match Day 11's topic
SNS_TOPIC_ORDER_EVENTS: Final[str] = "order-events"


class Settings(BaseSettings):
    """
    Environment-based configuration with validation.
    
    pydantic-settings automatically reads from environment variables,
    with the prefix specified in model_config. For example:
    - NOTIFICATION_SERVICE_AWS_ENDPOINT_URL -> aws_endpoint_url
    - NOTIFICATION_SERVICE_LOG_LEVEL -> log_level
    
    Attributes:
        aws_endpoint_url: LocalStack URL for local development (None for real AWS)
        aws_region: AWS region for SNS/SQS
        log_level: Logging verbosity
        api_host: Host to bind the API server
        api_port: Port for the API server
        consumer_enabled: Whether to start the SQS consumer
        consumer_poll_interval: Seconds between queue polls
        default_recipient: Default email for notifications (demo)
    """
    
    model_config = SettingsConfigDict(
        env_prefix="NOTIFICATION_SERVICE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
    
    # AWS Configuration
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_region: str = "us-east-1"
    
    # Logging
    log_level: str = "INFO"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8003
    
    # Consumer Configuration
    consumer_enabled: bool = True
    consumer_poll_interval: float = 1.0  # seconds
    
    # Notification defaults (for demo)
    default_recipient: str = "trader@example.com"
    enable_email: bool = True
    enable_slack: bool = True
    enable_sms: bool = False
    enable_push: bool = False


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Get cached settings instance.
    
    Uses lru_cache to ensure we only parse environment variables once.
    """
    return Settings()