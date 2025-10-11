"""
Basic metrics collection for system observability.

METRICS TYPES EXPLAINED:
========================

1. COUNTER: Monotonically increasing
   Example: total_orders_processed
   - Starts at 0
   - Only increments (never decreases)
   - Useful for: totals, counts, cumulative values
   - Math: rate of change = counter derivative
   
2. GAUGE: Can increase or decrease
   Example: queue_size, active_connections
   - Current value at this moment
   - Can go up and down
   - Useful for: current state, capacity
   
3. HISTOGRAM: Distribution of values
   Example: request_latency
   - Records many values
   - Calculate percentiles (p50, p95, p99)
   - Useful for: understanding distribution
   
4. RATE: Derived metric
   Example: messages_per_second
   - Count in time window / time
   - Useful for: throughput, frequency
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, Optional
from collections import deque

@dataclass
class MetricsCollector:
    """
    Collect and aggregate metrics for monitoring.

    DESIGN DECISIONS:
    - In-memory storage (fast, but lost on restart)
    - Time window (60 seconds default, configurable)
    - Simple API (increment, gauge, historgram)

    Later we'll integrate with:
    - Prometheus (pull-based metrics)
    - CloudWatch (AWS metrics)
    - Grafana (visualization)
    """

    def __init__(self):
        # COUNTERS: Total counts (only increase)
        # {metric_name: total_value}
        self._counters = Dict[str, float] = {}

        # GAUGES: Current values (can increase/decrease)
        # {metric_name: current_value}
        self._gauges = Dict[str, float] = {}

        # HISTOGRAMS: Time-series data for percentiles
        # {metric_name: deque[(timestamp, value)]}
        self._metrics = Dict[str, deque] = {}

    def increment(self, name: str, value: float = 1.0):
        """
        Increment a counter.
        
        Use for:
        - Total events processed
        - Total errors occurred
        - Total orders placed
        
        Example:
        collector.increment("orders.created")
        collector.increment("bytes.received", value=1024)
        """
        if name not in self._counters:
            self._counters[name] = 0
        self._counters[name] += value

    def gauge(self, name: str, value: float):
        """
        Set a gauge value (current state).
        
        Use for:
        - Queue size
        - Active connections
        - Memory usage
        - CPU percentage
        
        Example:
        collector.gauge("queue.size", queue.qsize())
        collector.gauge("connections.active", len(connections))
        """
        self._gauges[name] = value

    def histogram(self, name: str, value: float):
        """
        Record a histogram value.
        
        Use for:
        - Request latency
        - Message size
        - Processing time
        
        Later calculate:
        - p50 (median)
        - p95 (95th percentile)
        - p99 (99th percentile)
        
        Example:
        start = time.time()
        process_message()
        latency = time.time() - start
        collector.histogram("processing.latency", latency)
        """
        if name not in self._metrics:
            self._metrics[name] = deque()
        
        self._metrics[name].append({
            'timestamp': datetime.utcnow(),
            'value': value
        })
    
    def get_counter(self, name: str) -> float:
        """Get current counter value."""
        return self._counters.get(name, 0.0)
    
    def get_gauge(self, name: str) -> float:
        """Get current gauge value."""
        return self._gauges.get(name, 0.0)
    
    def get_rate(self, name: str, seconds: int = 60) -> float:
        """
        Calculate rate (events per second).
        
        CALCULATION:
        rate = count_in_window / window_duration
        
        Example:
        If 300 messages in last 60 seconds:
        rate = 300 / 60 = 5 messages/second
        """
        if name not in self._metrics:
            return 0.0
        
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        
        # Count values after cutoff
        count = sum(
            1 for item in self._metrics[name]
            if item['timestamp'] > cutoff
        )
        
        return count / seconds if seconds > 0 else 0.0
    
    def get_summary(self) -> Dict:
        """
        Get summary of all metrics.
        
        Returns dictionary with:
        - counters: All counter values
        - gauges: All gauge values
        - rates: Calculated rates for metrics
        
        Use for:
        - Health check endpoint
        - Admin dashboard
        - Debugging
        """
        return {
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "rates": {
                name: self.get_rate(name)
                for name in self._metrics.keys()
            }
        }
    
    def print_summary(self):
        """Print human-readable metrics summary."""
        print("\n" + "=" * 60)
        print("METRICS SUMMARY")
        print("=" * 60)
        
        if self._counters:
            print("\nCounters (Total):")
            for name, value in self._counters.items():
                print(f"  {name}: {value:.0f}")
        
        if self._gauges:
            print("\nGauges (Current):")
            for name, value in self._gauges.items():
                print(f"  {name}: {value:.2f}")
        
        if self._metrics:
            print("\nRates (per second):")
            for name in self._metrics.keys():
                rate = self.get_rate(name)
                print(f"  {name}: {rate:.2f}/s")
        
        print("=" * 60 + "\n")


# SINGLETON PATTERN
# =================
# Single global instance for entire application
# Alternative: Dependency injection (better for testing)

_metrics: Optional[MetricsCollector] = None

def get_metrics() -> MetricsCollector:
    """
    Get global metrics collector instance.
    
    SINGLETON PATTERN:
    - Create once on first call
    - Reuse same instance afterward
    - Ensures all metrics go to same collector
    
    Usage:
    from trading_system.shared_kernel.metrics import get_metrics
    
    metrics = get_metrics()
    metrics.increment("orders.created")
    """
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics