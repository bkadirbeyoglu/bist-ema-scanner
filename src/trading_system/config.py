"""
Configuration management for the trading system.

Uses environment variables with sensible defaults.
Follows the 12-factor app methodology.

PYTHON MODULE: os
=================
Provides operating system interface
- os.getenv(): Read environment variables
- os.path: File path operations
- os.environ: Environment variable dictionary
"""
import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum


class Environment(Enum):
    """
    Deployment environment.
    
    PYTHON FEATURE: Enum
    ====================
    Enumeration - a set of symbolic names bound to unique values
    
    Usage:
    env = Environment.DEVELOPMENT
    if env == Environment.PRODUCTION:
        enable_security()
    
    Benefits over strings:
    - Type safety (IDE autocomplete)
    - Can't typo "produktion"
    - Clear set of valid values
    """
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TESTING = "testing"


@dataclass
class DatabaseConfig:
    """
    Database configuration.
    
    PYTHON FEATURE: @dataclass
    ==========================
    Decorator that auto-generates:
    - __init__() method
    - __repr__() method (string representation)
    - __eq__() method (equality comparison)
    
    Without @dataclass, you'd write:
    class DatabaseConfig:
        def __init__(self, url, pool_size, ...):
            self.url = url
            self.pool_size = pool_size
            # ... etc
    
    With @dataclass, Python generates all this boilerplate!
    """
    url: str = "postgresql://localhost:5432/trading"
    pool_size: int = 10
    max_overflow: int = 20
    echo: bool = False  # SQL query logging


@dataclass
class TradingConfig:
    """Trading system configuration."""
    max_positions: int = 50
    max_order_value: float = 100000.0
    max_daily_trades: int = 100
    enable_short_selling: bool = False


@dataclass
class RiskConfig:
    """Risk management configuration."""
    max_portfolio_exposure: float = 0.3
    max_position_size: float = 0.1
    stop_loss_percentage: float = 0.02
    enable_risk_checks: bool = True


@dataclass
class Config:
    """
    Main configuration class for the trading system.
    
    This class aggregates all configuration sections and
    provides methods for loading from environment variables.
    
    PYTHON FEATURE: field()
    =======================
    Used with @dataclass for complex default values
    field(default_factory=dict) creates NEW dict per instance
    
    Why needed?
    # This is WRONG (shared mutable default):
    features: Dict = {}  # All instances share same dict!
    
    # This is RIGHT:
    features: Dict = field(default_factory=dict)  # Each gets own dict
    """
    
    # Environment
    env: Environment = Environment.DEVELOPMENT
    
    # Sub-configurations
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    
    # API Keys
    alpha_vantage_key: Optional[str] = None
    polygon_key: Optional[str] = None
    
    # Logging
    log_level: str = "INFO"
    log_format: str = "json"  # "json" or "text"
    
    # Feature flags
    features: Dict[str, bool] = field(default_factory=lambda: {
        "websocket_enabled": True,
        "paper_trading": True,
        "backtesting": False,
    })
    
    @classmethod
    def from_env(cls) -> "Config":
        """
        Load configuration from environment variables.
        
        Environment variables override defaults.
        Prefix: TRADING_* for all variables.
        
        PYTHON DECORATOR: @classmethod
        ===============================
        Creates a method bound to the class, not an instance
        First parameter is cls (the class) not self (instance)
        Used for alternative constructors
        
        Usage:
        config = Config.from_env()  # Calls classmethod
        # vs
        config = Config()           # Calls __init__
        config.some_method()        # Calls instance method
        """
        # Determine environment
        env_str = os.getenv("TRADING_ENV", "development")
        try:
            env = Environment(env_str.lower())
        except ValueError:
            env = Environment.DEVELOPMENT
        
        # Create config with environment-specific defaults
        config = cls(env=env)
        
        # Load database config
        config.database.url = os.getenv(
            "DATABASE_URL",
            config.database.url
        )
        config.database.pool_size = int(
            os.getenv("DATABASE_POOL_SIZE", "10")
        )
        config.database.echo = env == Environment.DEVELOPMENT
        
        # Load trading config
        config.trading.max_positions = int(
            os.getenv("TRADING_MAX_POSITIONS", "50")
        )
        config.trading.max_order_value = float(
            os.getenv("TRADING_MAX_ORDER_VALUE", "100000")
        )
        
        # Load risk config
        config.risk.enable_risk_checks = os.getenv(
            "TRADING_ENABLE_RISK_CHECKS", "true"
        ).lower() == "true"
        
        # Load API keys
        config.alpha_vantage_key = os.getenv("ALPHA_VANTAGE_KEY")
        config.polygon_key = os.getenv("POLYGON_KEY")
        
        # Load logging config
        config.log_level = os.getenv("LOG_LEVEL", "INFO")
        config.log_format = os.getenv("LOG_FORMAT", "json")
        
        # Load feature flags
        if os.getenv("TRADING_WEBSOCKET_ENABLED"):
            config.features["websocket_enabled"] = os.getenv(
                "TRADING_WEBSOCKET_ENABLED", "true"
            ).lower() == "true"
        
        return config
    
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.env == Environment.PRODUCTION
    
    def is_development(self) -> bool:
        """Check if running in development."""
        return self.env == Environment.DEVELOPMENT
    
    def validate(self) -> None:
        """
        Validate configuration.
        
        Raises:
            ValueError: If configuration is invalid
        """
        # Production-specific validations
        if self.is_production():
            if not self.alpha_vantage_key:
                raise ValueError(
                    "ALPHA_VANTAGE_KEY required in production"
                )
            if self.database.url.startswith("postgresql://localhost"):
                raise ValueError(
                    "Cannot use localhost database in production"
                )
            if not self.risk.enable_risk_checks:
                raise ValueError(
                    "Risk checks must be enabled in production"
                )
        
        # General validations
        if self.trading.max_order_value <= 0:
            raise ValueError("max_order_value must be positive")
        
        if self.risk.max_portfolio_exposure > 1.0:
            raise ValueError(
                "max_portfolio_exposure cannot exceed 100%"
            )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "env": self.env.value,
            "database": {
                "url": self.database.url.replace(
                    r'(?<=://)([^:]+):([^@]+)(?=@)',
                    'xxx:xxx'
                ),  # Mask credentials
                "pool_size": self.database.pool_size,
            },
            "trading": {
                "max_positions": self.trading.max_positions,
                "max_order_value": self.trading.max_order_value,
            },
            "risk": {
                "enable_risk_checks": self.risk.enable_risk_checks,
            },
            "features": self.features,
        }


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """
    Get the global configuration instance.
    
    PYTHON KEYWORD: global
    ======================
    The 'global' keyword tells Python to use a variable from 
    the module level (global scope) rather than creating a 
    new local variable.
    
    Without 'global':
        def func():
            _config = Config()  # Creates NEW local variable
            # Original _config at module level unchanged!
    
    With 'global':
        def func():
            global _config
            _config = Config()  # Modifies module-level _config
            # Now accessible everywhere in the module
    
    This implements the Singleton pattern - we only create
    one Config instance and reuse it everywhere.
    
    Returns:
        Config: The configuration instance
    """
    global _config  # Use the module-level _config variable
    
    if _config is None:
        # First time called - create and validate config
        _config = Config.from_env()
        _config.validate()
    
    # Return the existing config (Singleton pattern)
    return _config