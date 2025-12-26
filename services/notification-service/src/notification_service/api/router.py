"""
REST API router for Notification Service.

Note: The dependency function (get_notification_service) is injected
via app.dependency_overrides in main.py. This allows the router to
remain decoupled from the specific implementation.
"""

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException, Query

from notification_service.api.schemas import HealthResponse
from notification_service.api.schemas import NotificationListResponse
from notification_service.api.schemas import NotificationResponse
from notification_service.api.schemas import NotificationStatsResponse
from notification_service.api.schemas import RecipientResponse
from notification_service.application.notification_service import NotificationApplicationService
from notification_service.config import SERVICE_NAME
from notification_service.domain.entities import Notification
from notification_service.domain.value_objects import NotificationId

router = APIRouter()

# =============================================================================
# Dependency Injection with Placeholder Pattern
# =============================================================================
#
# THE PROBLEM: Circular Imports
# -----------------------------
# We need the NotificationApplicationService in our routes, but:
#
#   main.py imports router.py (to register routes)
#   router.py imports main.py (to get the service instance)  <-- CIRCULAR!
#
#   # main.py
#   from notification_service.api.router import router  # Import router
#   app.include_router(router)
#
#   # router.py
#   from notification_service.api.main import notification_service  # FAILS!
#   # Python hasn't finished loading main.py yet!
#
# THE SOLUTION: Placeholder + Override Pattern
# --------------------------------------------
# 1. Define a placeholder function in router.py (this file)
# 2. Use Depends(placeholder) in route handlers
# 3. Override the placeholder with the real dependency in main.py
#
# HOW IT WORKS:
#
#   STEP 1 (router.py - this file):
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │ def _get_service_placeholder():                                     │
#   │     raise RuntimeError("Not configured!")  # Safety net             │
#   │                                                                     │
#   │ get_notification_service = _get_service_placeholder  # Assign       │
#   │                                                                     │
#   │ @router.get("/notifications")                                       │
#   │ async def list_notifications(                                       │
#   │     service = Depends(get_notification_service)  # Uses placeholder │
#   │ ):                                                                  │
#   └─────────────────────────────────────────────────────────────────────┘
#
#   STEP 2 (main.py - after app is created):
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │ # Define the REAL dependency function                               │
#   │ def get_notification_service():                                     │
#   │     return NotificationApplicationService(repository=get_repo())    │
#   │                                                                     │
#   │ # Replace the placeholder with our real function!                   │
#   │ import notification_service.api.router as router_module             │
#   │ router_module.get_notification_service = get_notification_service   │
#   │ #             ^^^^^^^^^^^^^^^^^^^^^^^^   ^^^^^^^^^^^^^^^^^^^^^^^    │
#   │ #             The placeholder            Our real function          │
#   └─────────────────────────────────────────────────────────────────────┘
#
#   STEP 3 (at request time):
#   ┌─────────────────────────────────────────────────────────────────────┐
#   │ # When a request hits /notifications:                               │
#   │ # 1. FastAPI sees Depends(get_notification_service)                 │
#   │ # 2. get_notification_service now points to our real function       │
#   │ # 3. Calls our function, returns NotificationApplicationService     │
#   └─────────────────────────────────────────────────────────────────────┘
#
# WHY THE PLACEHOLDER RAISES AN ERROR:
# If someone forgets to set up the override in main.py, the placeholder
# gets called and raises a clear error message. This is a "fail fast"
# pattern - better to crash immediately with a helpful message than
# to fail mysteriously later.
#
# ALTERNATIVE: app.dependency_overrides
# FastAPI also supports overriding via app.dependency_overrides dict:
#
#   app.dependency_overrides[placeholder] = get_notification_service
#
# Both approaches work. Direct module replacement is simpler for this case.

def _get_service_placeholder() -> NotificationApplicationService:
    """
    Placeholder dependency - overridden at runtime.
    
    This function is never actually called because main.py replaces
    get_notification_service with the real implementation.
    """
    raise RuntimeError(
        "Service dependency not configured. "
        "Ensure main.py replaces get_notification_service before starting."
    )

# This will be the actual dependency used - override in main.py
get_notification_service: Callable[[], NotificationApplicationService] = _get_service_placeholder


def notification_to_response(notification: Notification) -> NotificationResponse:
    """Convert domain Notification to API response."""
    return NotificationResponse(
        id=notification.id,
        notification_type=str(notification.notification_type),
        channel=str(notification.channel),
        recipient=RecipientResponse(
            address=notification.recipient.address,
            name=notification.recipient.name,
        ),
        subject=notification.subject,
        body=notification.body,
        status=str(notification.status),
        priority=str(notification.priority),
        created_at=notification.created_at,
        sent_at=notification.sent_at,
        metadata=notification.metadata,
        reference_id=notification.reference_id,
        error_message=notification.error_message,
    )


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        service=SERVICE_NAME,
    )


@router.get("/notifications", response_model=NotificationListResponse)
async def list_notifications(
    limit: int = Query(default=100, ge=1, le=1000),
    service: NotificationApplicationService = Depends(get_notification_service),
) -> NotificationListResponse:
    """List all notifications."""
    notifications = await service.list_notifications(limit=limit)
    
    return NotificationListResponse(
        notifications=[notification_to_response(n) for n in notifications],
        total=len(notifications),
    )


@router.get("/notifications/stats", response_model=NotificationStatsResponse)
async def get_notification_stats(
    service: NotificationApplicationService = Depends(get_notification_service),
) -> NotificationStatsResponse:
    """Get notification statistics."""
    status_counts = await service.get_stats()
    by_status = {str(k): v for k, v in status_counts.items()}
    
    return NotificationStatsResponse(
        total=sum(status_counts.values()),
        by_status=by_status,
    )


@router.get("/notifications/{notification_id}", response_model=NotificationResponse)
async def get_notification(
    notification_id: str,
    service: NotificationApplicationService = Depends(get_notification_service),
) -> NotificationResponse:
    """Get a specific notification by ID."""
    notification = await service.get_notification(NotificationId(notification_id))
    
    if notification is None:
        raise HTTPException(
            status_code=404,
            detail=f"Notification {notification_id} not found",
        )
    
    return notification_to_response(notification)