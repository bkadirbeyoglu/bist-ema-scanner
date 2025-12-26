"""
Notification Service FastAPI application.

This module sets up the FastAPI application with:
- Dependency injection via app.dependency_overrides
- SQS consumer lifecycle management
- Structured logging configuration
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import structlog
from fastapi import FastAPI

from notification_service.api.router import router, get_notification_service as router_get_service
from notification_service.api.schemas import HealthResponse
from notification_service.application.notification_service import NotificationApplicationService
from notification_service.application.templates import TemplateRegistry
from notification_service.config import SERVICE_NAME, get_settings
from notification_service.domain.value_objects import NotificationChannel
from notification_service.infrastructure.notification_repository import InMemoryNotificationRepository
from notification_service.infrastructure.sqs_consumer import NotificationEventHandler
from notification_service.infrastructure.sqs_consumer import SQSConsumer

# =============================================================================
# Logging Configuration
# =============================================================================


def configure_logging() -> None:
    """Configure structured logging."""
    settings = get_settings()
    
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    logging.basicConfig(
        format="%(message)s",
        level=getattr(logging, settings.log_level.upper()),
    )


# =============================================================================
# Dependency Injection - Completing the Placeholder Pattern
# =============================================================================
#
# This is STEP 2 of the placeholder pattern explained in router.py.
# Here we create the REAL dependencies and wire them up.
#
# WHY MODULE-LEVEL SINGLETONS?
# ----------------------------
# We need shared state that persists across requests:
#
#   Request 1: POST /notifications → saves to repository
#   Request 2: GET /notifications  → reads from SAME repository
#
# If we created a new repository for each request, data would be lost!
#
#   # BAD - each request gets a fresh (empty) repository:
#   def get_service():
#       return NotificationApplicationService(
#           repository=InMemoryNotificationRepository()  # New each time!
#       )
#
#   # GOOD - all requests share the same repository:
#   _repository = None  # Module-level singleton
#   
#   def get_repository():
#       global _repository
#       if _repository is None:
#           _repository = InMemoryNotificationRepository()
#       return _repository  # Same instance every time
#
# HOW THE OVERRIDE WORKS (see end of this file):
# ----------------------------------------------
# We use FastAPI's dependency_overrides mechanism:
#
#   # At top of main.py, we import:
#   from notification_service.api.router import get_notification_service as router_get_service
#   
#   # After creating the app, we override:
#   app.dependency_overrides[router_get_service] = get_notification_service
#
# This tells FastAPI: "When you see Depends(router_get_service), call our
# get_notification_service function instead."
#
# WHY NOT DIRECT MODULE REPLACEMENT?
# Direct replacement (router_module.get_notification_service = ...) doesn't
# work because FastAPI captures function references at route definition time,
# not at request time. dependency_overrides is checked at request time.
#
# SINGLETON PATTERN EXPLAINED:
# ----------------------------
#   _repository: ... | None = None   # Start with None
#   
#   def get_repository():
#       global _repository           # Access module-level variable
#       if _repository is None:      # First call? Create it.
#           _repository = InMemoryNotificationRepository()
#       return _repository           # Return same instance always
#
# The "global" keyword is needed because we're ASSIGNING to _repository.
# Without it, Python would create a local variable instead.

_repository: InMemoryNotificationRepository | None = None
_consumer: SQSConsumer | None = None
_consumer_task: asyncio.Task | None = None


def get_repository() -> InMemoryNotificationRepository:
    """Get the singleton repository instance."""
    global _repository
    if _repository is None:
        _repository = InMemoryNotificationRepository()
    return _repository


def get_notification_service() -> NotificationApplicationService:
    """
    Dependency provider for NotificationApplicationService.
    
    This function is used to override the placeholder in router.py
    via FastAPI's dependency_overrides mechanism.
    """
    return NotificationApplicationService(
        repository=get_repository(),
        template_registry=TemplateRegistry(),
    )


# =============================================================================
# Application Lifecycle
# =============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager."""
    global _consumer, _consumer_task
    
    configure_logging()
    logger = structlog.get_logger()
    settings = get_settings()
    
    logger.info(
        "Starting Notification Service",
        service=SERVICE_NAME,
        consumer_enabled=settings.consumer_enabled,
    )
    
    # Start SQS consumer if enabled
    if settings.consumer_enabled:
        service = get_notification_service()
        handler = NotificationEventHandler(
            notification_service=service,
            default_channels=[NotificationChannel.EMAIL, NotificationChannel.SLACK],
            default_recipient=settings.default_recipient,
        )
        _consumer = SQSConsumer(handler=handler)
        _consumer_task = asyncio.create_task(_consumer.start())
        logger.info("SQS consumer started")
    
    yield
    
    # Shutdown
    if _consumer:
        await _consumer.stop()
        if _consumer_task:
            _consumer_task.cancel()
            try:
                await _consumer_task
            except asyncio.CancelledError:
                pass
        logger.info("SQS consumer stopped")
    
    logger.info("Notification Service shut down")


# =============================================================================
# FastAPI Application
# =============================================================================

app = FastAPI(
    title="Notification Service",
    description="Microservice for sending notifications based on trading events",
    version="0.1.0",
    lifespan=lifespan,
)

# =============================================================================
# Wire Up Dependency Injection (STEP 3 of the Placeholder Pattern)
# =============================================================================
#
# Here we complete the dependency injection by telling FastAPI to use our
# real implementation instead of the placeholder.
#
# WHY app.dependency_overrides?
# -----------------------------
# FastAPI's Depends() captures a reference to the function at route definition
# time (when router.py is imported). If we just replace the module attribute:
#
#   router_module.get_notification_service = real_function
#
# FastAPI STILL has the OLD reference to _get_service_placeholder!
#
# app.dependency_overrides solves this:
#
#   app.dependency_overrides[placeholder] = real_function
#
# FastAPI checks this dict at REQUEST TIME and uses the override.
#
# NOTE: We imported get_notification_service as router_get_service at the top
# of this file. That's the same function object that FastAPI captured in
# Depends(), so we use it as the key.
#

# Tell FastAPI: "When you see Depends(router_get_service), call get_notification_service instead"
app.dependency_overrides[router_get_service] = get_notification_service

# Include router
app.include_router(router)


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {
        "service": SERVICE_NAME,
        "docs": "/docs",
        "health": "/health",
    }


if __name__ == "__main__":
    import uvicorn
    
    settings = get_settings()
    uvicorn.run(
        "notification_service.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )