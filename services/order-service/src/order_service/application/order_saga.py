"""
Order Placement Saga.

Orchestrates the multi-step process of placing an order.
This implements the ORCHESTRATION pattern where the saga controls
the flow and calls each service in sequence.

SAGA STEPS:
═══════════
1. Validate Order     - Check order parameters are valid
2. Get Market Price   - Fetch current price from Market Data Service
3. Check Risk Limits  - Validate against risk parameters
4. Reserve Funds      - Lock required capital in portfolio
5. Submit Order       - Send to execution venue (broker)

Each step that modifies state has a compensation action.
"""

import asyncio
import logging
import random
import uuid
from decimal import Decimal
from typing import Any

import httpx

from order_service.config import get_settings
from order_service.domain.entities import Order, OrderStatus
from order_service.application.saga import Saga

logger = logging.getLogger(__name__)


class OrderPlacementSaga(Saga):
    """
    Saga for placing a new order.
    
    CONTEXT ACCUMULATION:
    ═════════════════════
    
    The context grows as each step adds data:
    
    INITIAL:           order_id, symbol, quantity, account_id
                              │
    After validate:           │ (no additions - validation only)
                              ▼
    After get_price:  + current_price, estimated_value
                              │
                              ▼
    After check_risk: + risk_allocation_id
                              │
                              ▼
    After reserve:    + reserved_funds
                              │
                              ▼
    After submit:     + broker_order_id
    
    WHY THIS MATTERS: Compensation uses these IDs to undo each step!
    """

    def __init__(self, order: Order):
        """
        Initialize saga for a specific order.
        
        Args:
            order: The order to process
        """
        super().__init__(saga_id=order.id)
        self.order = order
        self._settings = get_settings()

        # Define all saga steps
        self._define_steps()

    def _define_steps(self) -> None:
        """Define all saga steps with their compensations."""

        # Step 1: Validate Order
        # No compensation - validation has no side effects
        self.add_step(
            name="validate_order",
            forward=self._validate_order,
            compensate=None
        )

        # Step 2: Get Market Price
        # No compensation - reading data has not side effects
        self.add_step(
            name="get_market_price",
            forward=self._get_market_price,
            compensate=None
        )

        # Step 3: Check Risk Limits
        # Compensation: Release risk allocation
        self.add_step(
            name="check_risk_limits",
            forward=self._check_risk_limits,
            compensate=self._release_risk_reservation
        )

        # Step 4: Reserve Funds
        # Compensation: Release reserved funds
        self.add_step(
            name="reserve_funds",
            forward=self._reserve_funds,
            compensate=self._release_funds
        )

        # Step 5: Submit Order
        # Compensation: Attempt to cancel the order
        self.add_step(
            name="submit_order",
            forward=self._submit_order,
            compensate=self._cancel_order
        )

    def build_initial_context(self) -> dict[str, Any]:
        """
        Create initial saga context from order.
        
        The context flows through all steps and accumulates
        data needed for execution and compensation.
        """
        return {
            # From the order
            "order_id": self.order.id,
            "symbol": self.order.symbol,
            "side": self.order.side.value,
            "order_type": self.order.order_type.value,
            "quantity": str(self.order.quantity),
            "limit_price": str(self.order.limit_price) if self.order.limit_price else None,
            "account_id": self.order.account_id,
            
            # Will be populated by steps (used for compensation)
            "current_price": None,
            "estimated_value": None,
            "risk_allocation_id": None,
            "reserved_funds": None,
            "broker_order_id": None
        }
        
    # =========================================================================
    # STEP 1: Validate Order
    # =========================================================================
    
    async def _validate_order(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Validate order parameters.
        
        This is LOCAL validation - no external service calls.
        No compensation needed because there are no side effects.
        
        WHY IS THIS ASYNC?
        ──────────────────
        This method doesn't await anything, yet it's marked async. Reasons:
        
        1. UNIFORM INTERFACE: All saga steps must match the signature:
           Callable[[dict], Awaitable[dict]]
           The saga engine does `await step.forward(context)` for ALL steps.
        
        2. SIMPLICITY: The saga executor doesn't need to check if a step is
           sync or async - it just awaits everything uniformly.
        
        3. FUTURE-PROOFING: If we later need to validate symbols against an
           external registry (API call), this method is already async.
        
        Python handles this gracefully - an async function that doesn't await
        anything simply returns immediately when awaited.
        """
        logger.info(f"[Step 1] Validating order {context['order_id']}")
        
        # Symbol validation
        symbol = context["symbol"]
        if not symbol or len(symbol) > 10:
            raise ValueError(f"Invalid symbol: '{symbol}'")
        
        # Quantity validation
        quantity = Decimal(context["quantity"])
        if quantity <= 0:
            raise ValueError(f"Quantity must be positive, got: {quantity}")
        
        if quantity > Decimal("1000000"):
            raise ValueError(f"Quantity {quantity} exceeds maximum of 1,000,000")
        
        # Limit price validation for limit orders
        order_type = context["order_type"]
        limit_price = context.get("limit_price")
        
        if order_type in ("LIMIT", "STOP_LIMIT") and not limit_price:
            raise ValueError(f"{order_type} order requires limit_price")
        
        if limit_price:
            limit_price_decimal = Decimal(limit_price)
            if limit_price_decimal <= 0:
                raise ValueError(f"Limit price must be positive: {limit_price}")
        
        # Update order status
        self.order.transition_to(OrderStatus.VALIDATED)
        
        logger.info(f"[Step 1] Order {context['order_id']} validated ✓")
        return context
    
    # =========================================================================
    # STEP 2: Get Market Price
    # =========================================================================

    async def _get_market_price(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Fetch current market price from Market Data Service.
        
        Uses HTTP to call the Market Data Service REST API.
        No compensation needed - reading data has no side effects.
        
        WHY HTTPX (not requests or aiohttp)?
        ────────────────────────────────────
        • requests: Sync-only, would block the event loop in async code
        • aiohttp: Async but more complex API, requires explicit session management
        • httpx: Best of both worlds:
          - Native async support (AsyncClient)
          - Familiar requests-like API
          - Simple context manager pattern
          - Built-in timeout handling
          - Modern, well-maintained
        """
        symbol = context["symbol"]
        logger.info(f"[Step 2] Fetching price for {symbol}")

        try:
            async with httpx.AsyncClient() as client:
                url = f"{self._settings.market_data_service_url}/prices/{symbol}"

                response = await client.get(url, timeout=5.0)

                if response.status_code == 200:
                    data = response.json()
                    current_price = Decimal(str(data["price"]))
                    logger.info(f"[Step 2] Got price for {symbol}: ${current_price}")
                elif response.status_code == 404:
                    # Symbol not found - use mock price for development
                    logger.warning(f"[Step 2] Price not found for {symbol}, using mock")
                    current_price = Decimal("150.00")
                else:
                    raise Exception(f"Market Data Service error: {response.status_code}")
                
        except httpx.ConnectError:
            # Market Data Service not available - use mock for development
            logger.warning("[Step 2] Market Data Service unavailable, using mock price")
            current_price = Decimal("150.00")
        
        # Calculate estimated order value
        quantity = Decimal(context["quantity"])
        estimated_value = current_price * quantity

         # Update context with new data
        context["current_price"] = str(current_price)
        context["estimated_value"] = str(estimated_value)
        
        # Update order
        self.order.estimated_value = estimated_value
        
        logger.info(
            f"[Step 2] Order value: {quantity} × ${current_price} = ${estimated_value} ✓"
        )
        
        return context
    
    # =========================================================================
    # STEP 3: Check Risk Limits
    # =========================================================================

    async def _check_risk_limits(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Validate order against risk limits.
        
        In production: Would call a Risk Service
        For now: Simulated with local validation
        
        Compensation: Release the risk allocation
        """
        logger.info(f"[Step 3] Checking risk limits for order {context['order_id']}")
        
        estimated_value = Decimal(context["estimated_value"])

        # Simulated risk checks (would call Risk Service in production)

        # Check 1: Single order size limit
        max_order_value = Decimal("100000")  # $100k max per order
        if estimated_value > max_order_value:
            raise ValueError(
                f"Order value ${estimated_value} exceeds limit ${max_order_value}"
            )
        
        # Check 2: Position concentration (simulated)
        # In production: Check total position in this symbol
        
        # Check 3: Daily trading limit (simulated)
        # In production: Check cumulative daily volume

        # Reserve risk allocation (simulated)
        risk_allocation_id = f"RISK-{context['order_id'][:8]}"
        context["risk_allocation_id"] = risk_allocation_id

        # Update order status
        self.order.transition_to(OrderStatus.RISK_CHECKED)

        logger.info(f"[Step 3] Risk check passed, allocation: {risk_allocation_id} ✓")

        return context
    
    async def _release_risk_reservation(self, context: dict[str, Any]) -> None:
        """
        COMPENSATION: Release risk allocation.
        
        Called if a later step fails after risk was approved.
        
        NOTE: This should be IDEMPOTENT - safe to call multiple times.
        """
        risk_allocation_id = context.get("risk_allocation_id")

        if risk_allocation_id:
            logger.info(
                f"[Compensate] Releasing risk allocation {risk_allocation_id}"
            )
            # In production: Call Risk Service to release allocation
            # The call should be idempotent - if already released, return success
        else:
            logger.info("[Compensate] No risk allocation to release")

    # =========================================================================
    # STEP 4: Reserve Funds
    # =========================================================================

    async def _reserve_funds(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Reserve funds in portfolio for order execution.
        
        In production: Would call Portfolio Service
        For now: Simulated with local tracking
        
        Compensation: Release the reserved funds
        """
        logger.info(f"[Step 4] Reserving funds for order {context['order_id']}")
        
        estimated_value = Decimal(context["estimated_value"])

        # Add buffer for slippage and commission (2%)
        buffer_percentage = Decimal("1.02")
        reserved_funds = estimated_value * buffer_percentage

        # Simulate fund check (would call Portfolio Service in production)
        simulated_available_balance = Decimal("500000")     # $500k available

        if reserved_funds > simulated_available_balance:
            raise ValueError(
                f"Insufficient funds: need ${reserved_funds}, "
                f"have ${simulated_available_balance}"
            )
        
        # Record reservation
        context["reserved_funds"] = str(reserved_funds)

        # Update order
        self.order.reserved_funds = reserved_funds
        self.order.transition_to(OrderStatus.FUNDS_RESERVED)

        logger.info(f"[Step 4] Reserved ${reserved_funds} ✓")
        
        return context
    
    async def _release_funds(self, context: dict[str, Any]) -> None:
        """
        COMPENSATION: Release reserved funds.
        
        Called if a later step fails after funds were reserved.
        
        NOTE: This should be IDEMPOTENT - safe to call multiple times.
        """
        reserved_funds = context.get("reserved_funds")
        
        if reserved_funds:
            logger.info(f"[Compensate] Releasing ${reserved_funds}")
            # In production: Call Portfolio Service to release funds
            # The call should be idempotent
            self.order.reserved_funds = None
        else:
            logger.info("[Compensate] No funds to release")
    
    # =========================================================================
    # STEP 5: Submit Order
    # =========================================================================

    async def _submit_order(self, context: dict[str, Any]) -> dict[str, Any]:
        """
        Submit order to execution venue (broker/exchange).
        
        In production: Would call Execution Service or Broker API
        For now: Simulated
        
        Compensation: Attempt to cancel the submitted order
        """
        logger.info(f"[Step 5] Submitting order {context['order_id']}")

        # Generate broker order ID
        broker_order_id = f"BROKER-{uuid.uuid4().hex[:8].upper()}"

        # Simulate potential broker rejection (5% chance)
        if random.random() < 0.05:
            raise Exception("Broker rejected: Market closed or insufficient liquidity")
        
        # Record broker ID
        context["broker_order_id"] = broker_order_id
        
        # Update order status
        self.order.transition_to(OrderStatus.SUBMITTED)
        
        # Simulate fill (instant for demo - real would be async)
        await asyncio.sleep(0.1)  # Simulate network latency
        
        # Mark as filled
        fill_price = Decimal(context["current_price"])
        self.order.filled_quantity = self.order.quantity
        self.order.average_fill_price = fill_price
        self.order.transition_to(OrderStatus.FILLED)
        
        logger.info(
            f"[Step 5] Order FILLED at ${fill_price}, broker ID: {broker_order_id} ✓"
        )
        
        return context
    
    async def _cancel_order(self, context: dict[str, Any]) -> None:
        """
        COMPENSATION: Attempt to cancel submitted order.
        
        Note: This is BEST-EFFORT. If the order was already filled,
        we cannot cancel it (would need a separate reversal process).
        
        NOTE: This should be IDEMPOTENT - safe to call multiple times.
        """
        broker_order_id = context.get("broker_order_id")
        
        if broker_order_id:
            logger.info(f"[Compensate] Attempting to cancel {broker_order_id}")
            
            # In production: Call Broker API to cancel
            # Should handle "already filled" gracefully
            
            # Only cancel if not yet filled
            if self.order.status == OrderStatus.SUBMITTED:
                self.order.transition_to(
                    OrderStatus.CANCELLED,
                    reason="Saga compensation"
                )
                logger.info("[Compensate] Order cancelled")
            else:
                logger.warning(
                    f"[Compensate] Cannot cancel - order status is {self.order.status}"
                )
        else:
            logger.info("[Compensate] No broker order to cancel")