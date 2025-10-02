"""
Base Event Classes for Event-Driven Architecture.

This module provides the foundation for all domain events in our trading system.
Events are immutable records of things that have happened in the system.

Key Concepts:
- Events represent PAST facts (OrderCreated, not CreateOrder)
- Events are immutable (can't change history)
- Events carry all data needed for processing (self-contained)
"""

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import (
    Dict, List, Callable, Type, TypeVar, Optional, 
    Awaitable, Any, Set
)
from dataclasses import dataclass, field
from datetime import datetime

# Logging setup - will write to console and/or file
# __name__ gives us hierarchical logger names like 'trading_system.shared_kernel.events'
logger = logging.getLogger(__name__)

# TypeVar creates a generic type placeholder
# 'bound' means EventType must be a subclass of BaseEvent
# This allows us to write type-safe generic functions
EventType = TypeVar('EventType', bound='BaseEvent')


@dataclass(frozen=True)
class BaseEvent:
    """
    Base class for all domain events.
    
    The @dataclass decorator is a powerful Python feature that:
    1. Auto-generates __init__ method from class attributes
    2. Auto-generates __repr__ for nice string representation
    3. Auto-generates __eq__ for equality comparison
    4. Auto-generates __hash__ if frozen=True (for use in sets/dicts)
    
    frozen=True means all fields are immutable after creation
    
    NOTE: No default values here to avoid inheritance issues with frozen dataclasses.
    Child classes will need to provide all values explicitly.
    """
    
    # No defaults to avoid "non-default argument follows default argument" error
    # in child classes when using frozen dataclass inheritance
    event_id: str
    timestamp: datetime
    version: int
    
    @classmethod
    def create(cls, **kwargs) -> 'BaseEvent':
        """
        Factory method to create events with sensible defaults.
        
        This allows us to create events without always specifying event_id, timestamp, etc.
        """
        # Add defaults if not provided
        if 'event_id' not in kwargs:
            kwargs['event_id'] = str(uuid.uuid4())
        if 'timestamp' not in kwargs:
            kwargs['timestamp'] = datetime.utcnow()
        if 'version' not in kwargs:
            kwargs['version'] = 1
        
        return cls(**kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert event to dictionary for serialization.
        
        This method is crucial for:
        1. Sending events over network (JSON)
        2. Storing events in database
        3. Logging events
        
        The -> dict syntax is a type hint indicating return type
        """
        return {
            'event_id': self.event_id,
            'event_type': self.__class__.__name__,  # Gets the actual class name
            'timestamp': self.timestamp.isoformat(),  # Convert to ISO string
            'version': self.version,
            **self._get_payload()  # ** unpacks dict into key-value pairs
        }
    
    def _get_payload(self) -> dict:
        """
        Template method pattern - subclasses override this.
        
        Leading underscore (_) indicates "internal" method:
        - Not part of public API
        - Subclasses can override
        - Users shouldn't call directly
        
        This is Python's convention for "protected" methods
        (Python doesn't have true private/protected like Java/C#)
        """
        return {}
    
    @classmethod  # This decorator makes it a class method
    def from_dict(cls, data: dict) -> 'BaseEvent':
        """
        Deserialize event from dictionary.
        
        @classmethod vs @staticmethod:
        - @classmethod receives the class as first argument (cls)
        - @staticmethod receives no implicit first argument
        - Use @classmethod when you need to create instances (factory pattern)
        
        The 'BaseEvent' in quotes is a forward reference
        (needed because the class isn't fully defined yet)
        """
        # Create a copy to avoid modifying original
        event_data = data.copy()
        
        # Remove fields that aren't constructor parameters
        event_data.pop('event_type', None)  # None = default if key doesn't exist
        
        # Convert ISO timestamp string back to datetime object
        if 'timestamp' in event_data:
            event_data['timestamp'] = datetime.fromisoformat(event_data['timestamp'])
        
        # cls() creates an instance of whatever class this method was called on
        # If called on OrderCreatedEvent, cls will be OrderCreatedEvent
        return cls(**event_data)  # ** unpacks dict as keyword arguments


# Type alias for semantic clarity
# This doesn't create a new type, just an alternative name
# Helps communicate intent: DomainEvent vs InfrastructureEvent
DomainEvent = BaseEvent