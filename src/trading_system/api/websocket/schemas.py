"""
Pydantic schemas for WebSocket messages.

Message Types:
- Client → Server: subscribe, unsubscribe, ping
- Server → Client: subscribed, signal, market_data, error, pong
"""
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, Field, ConfigDict

# Import existing SignalType from strategies module (reuse, don't duplicate!)
from trading_system.strategies.signals import SignalType


class WSMessageType(str, Enum):
    """WebSocket message types."""
    # Client → Server
    SUBSCRIBE = "subscribe"
    UNSUBSCRIBE = "unsubscribe"
    PING = "ping"
    
    # Server → Client
    CONNECTED = "connected"
    SUBSCRIBED = "subscribed"
    UNSUBSCRIBED = "unsubscribed"
    PONG = "pong"
    ERROR = "error"
    
    # Trading Events
    SIGNAL = "signal"
    PERFORMANCE = "performance"
    MARKET_DATA = "market_data"


class SignalMessage(BaseModel):
    """Real-time trading signal notification."""
    type: WSMessageType = WSMessageType.SIGNAL
    strategy_id: str
    strategy_name: str
    symbol: str
    signal_type: SignalType  # Reusing existing enum from strategies module
    price: Decimal
    quantity: Optional[int] = None
    # default_factory=dict: Creates new empty dict for each instance (avoids mutable default)
    indicators: Dict[str, float] = Field(default_factory=dict)
    confidence: Optional[float] = None
    # default_factory=datetime.utcnow: Calls function at instance creation time
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Pydantic V2: model_config replaces class Config
    # json_encoders: Convert Decimal to string in JSON (Decimal not JSON-serializable)
    model_config = ConfigDict(json_encoders={Decimal: str})


class MarketDataMessage(BaseModel):
    """Real-time market data update."""
    type: WSMessageType = WSMessageType.MARKET_DATA
    symbol: str
    price: Decimal
    bid: Optional[Decimal] = None
    ask: Optional[Decimal] = None
    volume: Optional[int] = None
    change: Optional[Decimal] = None
    change_percent: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    model_config = ConfigDict(json_encoders={Decimal: str})