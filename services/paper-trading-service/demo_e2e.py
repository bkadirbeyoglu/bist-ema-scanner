#!/usr/bin/env python3
"""
End-to-End Demo for Paper Trading Service.

Demonstrates the complete workflow:
1. Create a paper trading session
2. Start the session
3. Execute trades
4. View portfolio and P&L
5. View trade history
6. Stop the session

Run with: poetry run python demo_e2e.py
"""

import asyncio
import sys

import httpx


BASE_URL = "http://localhost:8002"
API_URL = f"{BASE_URL}/api/v1"


def print_header(title: str) -> None:
    print("\n" + "=" * 60 + f"\n  {title}\n" + "=" * 60)

def print_success(msg: str) -> None:
    print(f"✅ {msg}")

def print_error(msg: str) -> None:
    print(f"❌ {msg}")


# =============================================================================
# DEMO STEPS
# =============================================================================

async def check_health(client: httpx.AsyncClient) -> bool:
    """Check if the service is healthy."""
    try:
        response = await client.get(f"{API_URL}/health", timeout=5.0)
        if response.status_code == 200:
            data = response.json()
            print_success(f"Service healthy - {data['active_sessions']} active sessions")
            return True
        return False
    except httpx.ConnectError:
        print_error("Connection refused - is the service running?")
        print("   Start with: docker compose up -d")
        return False
    except httpx.TimeoutException:
        print_error("Connection timeout")
        return False


async def create_session(client: httpx.AsyncClient) -> str | None:
    """Create a new paper trading session."""
    print_header("1. CREATE SESSION")
    
    response = await client.post(
        f"{API_URL}/sessions",
        json={
            "initial_cash": "100000.00",
            "commission": "1.00",
            "slippage_percent": "0.0005",
        },
    )
    
    if response.status_code != 201:
        print_error(f"Failed to create session: {response.text}")
        return None
    
    data = response.json()
    print_success(f"Created session: {data['session_id']}")
    print(f"   Initial cash: ${float(data['initial_cash']):,.2f}")
    print(f"   State: {data['state']}")
    
    return data["session_id"]


async def start_session(client: httpx.AsyncClient, session_id: str) -> bool:
    """Start the session."""
    print_header("2. START SESSION")
    
    response = await client.post(f"{API_URL}/sessions/{session_id}/start")
    
    if response.status_code != 200:
        print_error(f"Failed to start session: {response.text}")
        return False
    
    data = response.json()
    print_success(f"Session started - State: {data['state']}")
    return True


async def execute_trades(client: httpx.AsyncClient, session_id: str) -> None:
    """Execute a series of trades."""
    print_header("3. EXECUTE TRADES")
    
    trades = [
        {"symbol": "AAPL", "side": "BUY", "quantity": 100, "market_price": "150.00"},
        {"symbol": "GOOGL", "side": "BUY", "quantity": 50, "market_price": "140.00"},
        {"symbol": "MSFT", "side": "BUY", "quantity": 75, "market_price": "380.00"},
        {"symbol": "AAPL", "side": "SELL", "quantity": 50, "market_price": "155.00"},
    ]
    
    for trade in trades:
        response = await client.post(
            f"{API_URL}/sessions/{session_id}/orders",
            json=trade,
        )
        
        if response.status_code != 200:
            print_error(f"Trade failed: {response.text}")
            continue
        
        result = response.json()
        if result["success"]:
            side = "BUY " if trade["side"] == "BUY" else "SELL"
            print(f"   {side} {trade['quantity']:>4} {trade['symbol']:<5} "
                  f"@ ${float(result['executed_price']):>7.2f} "
                  f"(slippage: ${float(result['slippage']):.2f})")


async def show_portfolio(client: httpx.AsyncClient, session_id: str) -> None:
    """Display portfolio snapshot."""
    print_header("4. PORTFOLIO SNAPSHOT")
    
    response = await client.get(f"{API_URL}/sessions/{session_id}/portfolio")
    
    if response.status_code != 200:
        print_error(f"Failed to get portfolio: {response.text}")
        return
    
    p = response.json()
    
    print(f"\n   💰 Cash:              ${float(p['cash']):>12,.2f}")
    print(f"   📊 Positions Value:   ${float(p['positions_value']):>12,.2f}")
    print(f"   ─────────────────────────────────────")
    print(f"   📈 Total Value:       ${float(p['total_value']):>12,.2f}")
    print()
    print(f"   📉 Unrealized P&L:    ${float(p['unrealized_pnl']):>12,.2f}")
    print(f"   💵 Realized P&L:      ${float(p['realized_pnl']):>12,.2f}")
    print(f"   ─────────────────────────────────────")
    print(f"   💎 Total P&L:         ${float(p['total_pnl']):>12,.2f} "
          f"({float(p['return_percent']):+.2f}%)")
    
    if p["positions"]:
        print(f"\n   📋 Open Positions:")
        for pos in p["positions"]:
            icon = "📈" if float(pos["unrealized_pnl"]) >= 0 else "📉"
            print(f"      {pos['symbol']:<5} {pos['quantity']:>4} shares "
                  f"@ ${float(pos['entry_price']):>7.2f} → "
                  f"${float(pos['current_price']):>7.2f} | "
                  f"P&L: ${float(pos['unrealized_pnl']):>8.2f} {icon}")


async def show_trades(client: httpx.AsyncClient, session_id: str) -> None:
    """Display trade history."""
    print_header("5. TRADE HISTORY")
    
    response = await client.get(f"{API_URL}/sessions/{session_id}/trades")
    
    if response.status_code != 200:
        print_error(f"Failed to get trades: {response.text}")
        return
    
    trades = response.json()
    
    print(f"\n   Total trades: {len(trades)}")
    print(f"\n   Recent trades:")
    
    for trade in trades[:5]:
        side = "BUY " if trade["side"] == "BUY" else "SELL"
        ts = trade["timestamp"][:19]
        print(f"      {ts} | {side} {trade['quantity']:>4} "
              f"{trade['symbol']:<5} @ ${float(trade['price']):>7.2f}")


async def stop_session(client: httpx.AsyncClient, session_id: str) -> None:
    """Stop the session."""
    print_header("6. STOP SESSION")
    
    response = await client.post(f"{API_URL}/sessions/{session_id}/stop")
    
    if response.status_code != 200:
        print_error(f"Failed to stop session: {response.text}")
        return
    
    data = response.json()
    print_success(f"Session stopped - Final state: {data['state']}")


# =============================================================================
# MAIN
# =============================================================================

async def main() -> int:
    """Run the complete demo."""
    print("\n" + "=" * 60)
    print("  📊 PAPER TRADING SERVICE - END-TO-END DEMO")
    print("=" * 60)
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check health
        if not await check_health(client):
            return 1
        
        # Create session
        session_id = await create_session(client)
        if not session_id:
            return 1
        
        # Start session
        if not await start_session(client, session_id):
            return 1
        
        # Execute trades
        await execute_trades(client, session_id)
        
        # Show portfolio
        await show_portfolio(client, session_id)
        
        # Show trades
        await show_trades(client, session_id)
        
        # Stop session
        await stop_session(client, session_id)
    
    print_header("DEMO COMPLETE")
    print("\n🎉 All operations completed successfully!")
    print(f"\n   Session ID: {session_id}")
    print(f"   API Docs:   {BASE_URL}/docs")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))