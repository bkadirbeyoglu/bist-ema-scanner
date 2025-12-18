#!/usr/bin/env python3
"""
Paper Trading Demo.

Run: poetry run python demo.py
"""

from decimal import Decimal

from paper_trading_service.domain.session import PaperTradingSession
from paper_trading_service.domain.order_simulator import OrderSide


def main() -> None:
    print("=" * 60)
    print("📈 PAPER TRADING DEMO")
    print("=" * 60)
    
    # Create session
    session = PaperTradingSession(initial_cash=Decimal("100000.00"))
    print(f"\n✅ Created session")
    print(f"   Initial cash: ${session.portfolio.cash:,.2f}")
    
    # Start trading
    session.start()
    print(f"\n▶️  Session started (state: {session.state.name})")
    
    # Execute trades
    trades = [
        ("AAPL", OrderSide.BUY, 100, Decimal("150.00")),
        ("GOOGL", OrderSide.BUY, 50, Decimal("140.00")),
        ("MSFT", OrderSide.BUY, 75, Decimal("380.00")),
        ("AAPL", OrderSide.SELL, 50, Decimal("155.00")),  # Partial sell
    ]
    
    print("\n📊 Executing trades:")
    print("-" * 60)
    
    for symbol, side, qty, price in trades:
        result = session.process_signal(symbol, side, qty, price)
        
        if result.filled:
            action = "BUY " if side == OrderSide.BUY else "SELL"
            cost_or_proceeds = result.fill_price * qty
            print(f"   {action} {qty:>3} {symbol:<5} @ ${result.fill_price:>7.2f} "
                  f"= ${cost_or_proceeds:>10,.2f} "
                  f"(slip: ${result.slippage:.2f}, comm: ${result.commission:.2f})")
    
    # Current prices (simulated market movement)
    current_prices = {
        "AAPL": Decimal("158.00"),   # Up from ~150
        "GOOGL": Decimal("145.00"),  # Up from 140
        "MSFT": Decimal("375.00"),   # Down from 380
    }
    
    # Get snapshot
    snapshot = session.snapshot(current_prices)
    
    print("\n" + "=" * 60)
    print("💰 PORTFOLIO SUMMARY")
    print("=" * 60)
    print(f"   Cash:              ${snapshot['cash']:>12,.2f}")
    print(f"   Positions Value:   ${snapshot['positions_value']:>12,.2f}")
    print(f"   ─────────────────────────────────────")
    print(f"   Total Value:       ${snapshot['total_value']:>12,.2f}")
    print()
    print(f"   Unrealized P&L:    ${snapshot['unrealized_pnl']:>12,.2f}")
    print(f"   Realized P&L:      ${snapshot['realized_pnl']:>12,.2f}")
    print(f"   ─────────────────────────────────────")
    print(f"   Total P&L:         ${snapshot['total_pnl']:>12,.2f} ({snapshot['return_percent']:+.2f}%)")
    
    print("\n📋 Open Positions:")
    print("-" * 60)
    
    for pos in snapshot["positions"]:
        icon = "📈" if pos["unrealized_pnl"] >= 0 else "📉"
        print(f"   {pos['symbol']:<5} {pos['quantity']:>4} shares "
              f"@ ${pos['entry_price']:>7.2f} → ${pos['current_price']:>7.2f} "
              f"| P&L: ${pos['unrealized_pnl']:>8.2f} {icon}")
    
    print(f"\n📒 Trade Journal:")
    print(f"   Total trades:    {session.journal.trade_count}")
    print(f"   Total volume:    ${session.journal.total_volume:,.2f}")
    print(f"   Total commission: ${session.journal.total_commission:.2f}")
    
    # Recent trades
    print("\n   Recent trades:")
    for trade in session.journal.get_recent(3):
        side_str = "BUY " if trade.side == OrderSide.BUY else "SELL"
        print(f"      {side_str} {trade.quantity} {trade.symbol} @ ${trade.price:.2f}")
    
    # Stop session
    session.stop()
    print(f"\n⏹️  Session stopped")
    print("=" * 60)


if __name__ == "__main__":
    main()