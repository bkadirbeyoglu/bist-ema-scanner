"""
Base Event Classes for Event-Driven Architecture.

This module provides the foundation for all domain events in our trading system.
Events are immutable records of things that have happened in the system.

Key Concepts:
- Events represent PAST facts (OrderCreated, not CreateOrder)
- Events are immutable (can't change history)
- Events carry all data needed for processing (self-contained)
- Events relate to aggregates (entities in DDD)
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

logger = logging.getLogger(__name__)

# TypeVar for type-safe generic functions
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
    (events should never change once created - immutability principle)
    
    Attributes:
        event_id: Unique identifier for this event
        aggregate_id: ID of the aggregate (entity) this event relates to
        occurred_at: When the event occurred (timezone-aware datetime)
    
    NOTE: No default values here to avoid inheritance issues with frozen dataclasses.
    Child classes will need to provide all values explicitly.
    """
    
    # Core DDD event fields
    event_id: str
    aggregate_id: str
    occurred_at: datetime
    
    @classmethod
    def create(cls, aggregate_id: str, **kwargs) -> 'BaseEvent':
        """
        Factory method to create events with sensible defaults.
        
        This allows us to create events without always specifying event_id, occurred_at, etc.
        
        Args:
            aggregate_id: Required - the ID of the aggregate this event relates to
            **kwargs: Additional event-specific fields
        """
        # Add defaults if not provided
        if 'event_id' not in kwargs:
            kwargs['event_id'] = str(uuid.uuid4())
        if 'occurred_at' not in kwargs:
            kwargs['occurred_at'] = datetime.utcnow()
        
        return cls(aggregate_id=aggregate_id, **kwargs)
    
    def to_dict(self) -> dict:
        """
        Convert event to dictionary for serialization.
        
        This method is crucial for:
        1. Sending events over network (JSON)
        2. Storing events in database
        3. Logging events
        """
        return {
            'event_id': self.event_id,
            'aggregate_id': self.aggregate_id,
            'event_type': self.__class__.__name__,
            'occurred_at': self.occurred_at.isoformat(),
            **self._get_payload()
        }
    
    def _get_payload(self) -> dict:
        """
        Template method pattern - subclasses override this.
        
        Returns event-specific data fields (excluding base fields).
        
        Leading underscore (_) indicates "internal" method:
        - Not part of public API
        - Subclasses can override
        - Users shouldn't call directly
        """
        return {}
    
    @classmethod
    def from_dict(cls, data: dict) -> 'BaseEvent':
        """
        Deserialize event from dictionary.
        
        @classmethod vs @staticmethod:
        - @classmethod receives the class as first argument (cls)
        - @staticmethod receives no implicit first argument
        - Use @classmethod when you need to create instances (factory pattern)
        
        Args:
            data: Dictionary containing event data
            
        Returns:
            Instance of the event class
        """
        # Create a copy to avoid modifying original
        event_data = data.copy()
        
        # Remove fields that aren't constructor parameters
        event_data.pop('event_type', None)
        
        # Convert ISO timestamp string back to datetime object
        if 'occurred_at' in event_data:
            event_data['occurred_at'] = datetime.fromisoformat(event_data['occurred_at'])
        
        return cls(**event_data)


# Type alias for semantic clarity
DomainEvent = BaseEvent