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
    - Deque for efficient FIFO (O(1) append/pop)
    - Simple API (increment, gauge, histogram)
    
    WHY DEQUE FOR TIME-SERIES DATA?
    ================================
    Performance comparison (1 million operations):
    
    LIST:
      append to end:    0.1s  ✅ (fast)
      pop from start:   30s   ❌ (very slow - shifts all items!)
    
    DEQUE:
      append to end:    0.1s  ✅ (fast)
      popleft():        0.1s  ✅ (fast - no shifting!)
    
    Our access pattern:
      Time ──────────────────────────────>
      deque: [old, old, old, NEW, NEW]
              ↑                    ↑
          remove old          add new
          (popleft)           (append)
          O(1) ✅             O(1) ✅
    
    Later we'll integrate with:
    - Prometheus (pull-based metrics)
    - CloudWatch (AWS metrics)
    - Grafana (visualization)
    """
    
    def __init__(self):
        # COUNTERS: Total counts (only increase)
        # {metric_name: total_value}
        self._counters: Dict[str, float] = {}
        
        # GAUGES: Current values (can increase/decrease)
        # {metric_name: current_value}
        self._gauges: Dict[str, float] = {}
        
        # HISTOGRAMS: Time-series data for percentiles
        # WHY DEQUE? (Double-Ended Queue)
        # ================================
        # deque vs list performance:
        # - deque.append(x):      O(1) ✅  vs  list.append(x):      O(1) ✅
        # - deque.appendleft(x):  O(1) ✅  vs  list.insert(0, x):   O(n) ❌
        # - deque.popleft():      O(1) ✅  vs  list.pop(0):         O(n) ❌
        #
        # Our use case (time-series):
        # 1. Add new metrics to RIGHT (most recent):  deque.append() → O(1)
        # 2. Remove old metrics from LEFT (oldest):   deque.popleft() → O(1)
        # 3. Both operations are INSTANT, even with millions of items!
        #
        # With regular list:
        # - Adding is fast: list.append() → O(1) ✅
        # - Removing is SLOW: list.pop(0) → O(n) ❌ (shifts all elements!)
        #
        # Example timeline:
        #   deque: [oldest, ..., ..., newest] 
        #           ↑                    ↑
        #       popleft()            append()
        #       (remove old)      (add new)
        #       O(1) ✅           O(1) ✅
        #
        # {metric_name: deque[(timestamp, value), ...]}
        self._metrics: Dict[str, deque] = {}
    
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
            # Initialize deque for this metric
            # deque = Double-Ended Queue (fast on both ends)
            self._metrics[name] = deque()
        
        # Add to RIGHT end (newest data) - O(1) operation
        # deque structure: [old, ..., ..., NEW] ← append here
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
        
        HOW DEQUE HELPS:
        ================
        Time window filtering is efficient because:
        - Old items are at the LEFT (front) of deque
        - New items are at the RIGHT (back) of deque
        - We can easily ignore old items or remove them with popleft() - O(1)
        
        Timeline visualization:
        deque: [OLD_item1, OLD_item2, NEW_item3, NEW_item4]
                ↑                      ↑
                Too old (skip)         Recent (count)
        
        With regular list, we'd either:
        1. Filter inefficiently: O(n) scan
        2. Remove old items: list.pop(0) → O(n) per removal (shifts everything!)
        """
        if name not in self._metrics:
            return 0.0
        
        # Calculate cutoff time
        cutoff = datetime.utcnow() - timedelta(seconds=seconds)
        
        # Count values after cutoff
        # Old items (before cutoff) are at the front, easy to skip
        count = sum(
            1 for item in self._metrics[name]
            if item['timestamp'] > cutoff
        )
        
        return count / seconds if seconds > 0 else 0.0
    
    def cleanup_old_data(self, name: str, max_age_seconds: int = 60):
        """
        Remove metrics older than max_age_seconds.
        
        DEQUE ADVANTAGE EXAMPLE:
        ========================
        This is WHERE deque SHINES!
        
        deque: [item1(60s), item2(30s), item3(10s), item4(5s)]
                ↑                                    ↑
                OLD (remove with popleft())          NEW (keep)
        
        Operation:
        - while oldest item is too old:
        -     deque.popleft()  ← O(1) removal!
        
        With list:
        - while oldest item is too old:
        -     list.pop(0)      ← O(n) removal! (shifts all items left)
        
        For 1000 old items to remove:
        - deque: 1000 × O(1) = O(1000) = very fast ✅
        - list:  1000 × O(n) = O(1000 × 1000) = extremely slow ❌
        """
        if name not in self._metrics:
            return
        
        cutoff = datetime.utcnow() - timedelta(seconds=max_age_seconds)
        
        # Remove old items from LEFT (oldest items first)
        # Each popleft() is O(1) - instant removal!
        while (self._metrics[name] and 
               self._metrics[name][0]['timestamp'] < cutoff):
            self._metrics[name].popleft()  # Remove oldest - O(1)!
    
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
        
        NOTE: Rate calculation iterates through deque items
        This is efficient because:
        - Modern deques are implemented as doubly-linked lists of blocks
        - Iteration is O(n) but memory-efficient
        - No copying or shifting of data
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
    
    PERFORMANCE TIP - Periodic Cleanup:
    ==================================
    For long-running applications, periodically cleanup old data
    to prevent unbounded memory growth:
    
    # Every minute, cleanup data older than 60 seconds
    while True:
        await asyncio.sleep(60)
        for metric_name in metrics._metrics.keys():
            metrics.cleanup_old_data(metric_name, max_age_seconds=60)
    
    Why this works well with deque:
    - cleanup_old_data() uses popleft() - O(1) per removal
    - Even removing 1000s of old items is near-instant
    - With list.pop(0), this would be very slow!
    """
    global _metrics
    if _metrics is None:
        _metrics = MetricsCollector()
    return _metrics