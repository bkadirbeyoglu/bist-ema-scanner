"""
Notification repository implementations.

Provides storage for notifications. The in-memory implementation
is suitable for development and testing.
"""

import asyncio
from collections import Counter
from typing import Protocol

from notification_service.domain.entities import Notification
from notification_service.domain.value_objects import NotificationId
from notification_service.domain.value_objects import NotificationStatus


class NotificationRepository(Protocol):
    """
    Protocol for notification repository.
    
    Uses Protocol (structural subtyping) - any class with these
    methods can be used as a repository.
    """

    async def save(self, notification: Notification) -> None:
        """Save notification to storage."""
        ...

    async def get_by_id(self, notification_id: NotificationId) -> Notification:
        """Get notification by ID."""
        ...

    async def list_all(self, limit: int = 100) -> list[Notification]:
        """List notifications, newest first."""
        ...

    async def count_by_status(self) -> dict[NotificationStatus, int]:
        """Count notifications by status."""
        ...


class InMemoryNotificationRepository:
    """
    Thread-safe in-memory notification repository.
    
    Uses asyncio.Lock for async-safe access.
    Suitable for development and testing.
    """
    
    def __init__(self) -> None:
        """Initialize empty repository."""
        self._notifications: dict[NotificationId, Notification] = {}
        self._lock = asyncio.Lock()

    async def save(self, notification: Notification) -> None:
        """Save notification to storage."""
        async with self._lock:
            self._notifications[notification.id] = notification

    async def get_by_id(self, notification_id: NotificationId) -> Notification:
        """Get notification by ID."""
        async with self._lock:
            return self._notifications.get(notification_id)
        
    async def list_all(self, limit: int = 100) -> list[Notification]:
        """List notifications, newest first."""
        async with self._lock:
            notifications = list(self._notifications.values())
            notifications.sort(key=lambda n: n.created_at, reverse=True)
            return notifications[:limit]
        
    async def count_by_status(self) -> dict[NotificationStatus, int]:
        """Count notifications by status."""
        async with self._lock:
            status_counts = Counter(n.status for n in self._notifications.values())
            return dict(status_counts)
        
    async def clear(self) -> None:
        """Clear all notifications (for testing)."""
        async with self._lock:
            self._notifications.clear()

    def __len__(self) -> int:
        """Return number of stored notifications."""
        return len(self._notifications)