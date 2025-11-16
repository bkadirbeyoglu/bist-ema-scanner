"""Custom analyzers for detailed backtest analysis."""
from typing import Dict, Any
import backtrader as bt
import numpy as np
from uuid import uuid4


class TradingSystemAnalyzer(bt.Analyzer):
    """Comprehensive trading statistics analyzer."""
    
    def __init__(self):
        """Initialize statistics tracking."""
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_pnl = 0.0
        self.total_wins = 0.0
        self.total_losses = 0.0
    
    def notify_trade(self, trade):
        """Track trade completions."""
        if trade.isclosed:
            self.total_trades += 1
            pnl = trade.pnlcomm
            
            if pnl > 0:
                self.winning_trades += 1
                self.total_wins += pnl
            else:
                self.losing_trades += 1
                self.total_losses += abs(pnl)
            
            self.total_pnl += pnl
    
    def get_analysis(self) -> Dict[str, Any]:
        """Return trading statistics."""
        win_rate = self.winning_trades / self.total_trades if self.total_trades > 0 else 0.0
        
        avg_win = self.total_wins / self.winning_trades if self.winning_trades > 0 else 0.0
        avg_loss = self.total_losses / self.losing_trades if self.losing_trades > 0 else 0.0
        
        profit_factor = self.total_wins / self.total_losses if self.total_losses > 0 else 0.0
        
        return {
            'total_trades': self.total_trades,
            'winning_trades': self.winning_trades,
            'losing_trades': self.losing_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'profit_factor': profit_factor,
            'total_pnl': self.total_pnl,
        }


class DetailedTradeAnalyzer(bt.Analyzer):
    """Detailed trade-by-trade analysis with enhanced metrics."""
    
    def __init__(self):
        """Initialize trade tracking."""
        self.trade_history = []
        self.current_trades = {}
    
    def notify_order(self, order):
        """Track order execution for detailed trade analysis.
        
        Args:
            order: Order object with status and execution info
        """
        if order.status in [order.Completed]:
            # Order executed
            data_name = order.data._name
            
            if order.isbuy():
                # Opening position
                self.current_trades[data_name] = {
                    'entry_price': order.executed.price,
                    'entry_date': order.executed.dt,  # This is a float in Backtrader
                    'size': order.executed.size,
                }
            elif order.issell() and data_name in self.current_trades:
                # Closing position
                entry = self.current_trades[data_name]
                
                # Calculate trade metrics
                pnl = (order.executed.price - entry['entry_price']) * entry['size']
                pnl_percent = ((order.executed.price / entry['entry_price']) - 1) * 100
                
                # PYTHON: Backtrader datetime handling
                # IMPORTANT: order.executed.dt is a FLOAT (days since epoch), not datetime
                # So subtraction gives float, not timedelta
                # This is a quirk of Backtrader's internal date representation
                duration_days = order.executed.dt - entry['entry_date']
                
                self.trade_history.append({
                    'entry_date': entry['entry_date'],
                    'exit_date': order.executed.dt,
                    'entry_price': entry['entry_price'],
                    'exit_price': order.executed.price,
                    'size': entry['size'],
                    'pnl': pnl,
                    'pnl_percent': pnl_percent,
                    'duration': int(duration_days),  # Convert float days to int
                })
                
                # Clear current trade
                del self.current_trades[data_name]
    
    def get_analysis(self) -> Dict[str, Any]:
        """Return detailed trade statistics.
        
        NUMPY: Efficient array operations for statistics
        
        Returns:
            Dictionary with trade details and statistics
        """
        if not self.trade_history:
            return {
                'trades': [],
                'statistics': {
                    'avg_duration': 0,
                    'max_duration': 0,
                    'min_duration': 0,
                }
            }
        
        # Extract metrics using NumPy for efficiency
        durations = np.array([t['duration'] for t in self.trade_history])
        pnls = np.array([t['pnl'] for t in self.trade_history])
        
        return {
            'trades': self.trade_history,
            'statistics': {
                'avg_duration': float(np.mean(durations)),
                'max_duration': int(np.max(durations)),
                'min_duration': int(np.min(durations)),
                'avg_pnl': float(np.mean(pnls)),
                'max_pnl': float(np.max(pnls)),
                'min_pnl': float(np.min(pnls)),
            }
        }