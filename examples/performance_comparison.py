"""Performance comparison: In-Memory vs SQS Event Bus"""

import asyncio
import time
from dataclasses import dataclass
from typing import List
import statistics

from trading_system.infrastructure.messaging.sqs_client import SQSClient


@dataclass
class PerformanceResult:
    approach: str
    num_messages: int
    total_time: float
    avg_latency: float
    min_latency: float
    max_latency: float
    p95_latency: float
    p99_latency: float
    
    @property
    def throughput(self) -> float:
        return self.num_messages / self.total_time
    
    def __str__(self) -> str:
        return f"""
{self.approach}:
  Messages: {self.num_messages}
  Total time: {self.total_time:.2f}s
  Avg latency: {self.avg_latency*1000:.2f}ms
  Min latency: {self.min_latency*1000:.2f}ms
  Max latency: {self.max_latency*1000:.2f}ms
  P95 latency: {self.p95_latency*1000:.2f}ms
  P99 latency: {self.p99_latency*1000:.2f}ms
  Throughput: {self.throughput:.0f} msg/sec
"""


async def test_sqs_performance(num_messages: int = 100) -> PerformanceResult:
    latencies: List[float] = []
    
    async with SQSClient(endpoint_url="http://localhost:4566") as sqs:
        queue_name = "perf-test-queue"
        await sqs.create_queue(queue_name)
        await sqs.purge_queue(queue_name)
        await asyncio.sleep(1)
        
        start_time = time.time()
        
        for i in range(num_messages):
            msg_start = time.time()
            await sqs.send_message(queue_name, {"message_id": i, "data": "test"})
            latencies.append(time.time() - msg_start)
        
        total_time = time.time() - start_time
        latencies.sort()
        
        return PerformanceResult(
            approach="SQS (LocalStack)",
            num_messages=num_messages,
            total_time=total_time,
            avg_latency=statistics.mean(latencies),
            min_latency=min(latencies),
            max_latency=max(latencies),
            p95_latency=latencies[int(len(latencies) * 0.95)],
            p99_latency=latencies[int(len(latencies) * 0.99)]
        )


async def test_inmemory_performance(num_messages: int = 100) -> PerformanceResult:
    latencies: List[float] = []
    events: List[dict] = []
    
    start_time = time.time()
    
    for i in range(num_messages):
        msg_start = time.time()
        events.append({"message_id": i, "data": "test"})
        latencies.append(time.time() - msg_start)
    
    total_time = time.time() - start_time
    latencies.sort()
    
    return PerformanceResult(
        approach="In-Memory",
        num_messages=num_messages,
        total_time=total_time,
        avg_latency=statistics.mean(latencies),
        min_latency=min(latencies),
        max_latency=max(latencies),
        p95_latency=latencies[int(len(latencies) * 0.95)],
        p99_latency=latencies[int(len(latencies) * 0.99)]
    )


async def main():
    print("=" * 70)
    print("Performance Comparison: In-Memory vs SQS")
    print("=" * 70)
    
    num_messages = 100
    print(f"\nTesting with {num_messages} messages...\n")
    
    inmemory_result = await test_inmemory_performance(num_messages)
    print(inmemory_result)
    
    sqs_result = await test_sqs_performance(num_messages)
    print(sqs_result)
    
    print("=" * 70)
    print("Comparison & Analysis:")
    print("=" * 70)
    
    slowdown_factor = sqs_result.avg_latency / inmemory_result.avg_latency
    print(f"\nSQS is {slowdown_factor:.0f}x slower than in-memory")
    print(f"- In-memory: {inmemory_result.avg_latency*1000:.3f}ms")
    print(f"- SQS: {sqs_result.avg_latency*1000:.2f}ms")
    
    print(f"\nBut SQS provides:")
    print("  ✅ Durability (survives crashes)")
    print("  ✅ Scalability (multiple consumers)")
    print("  ✅ Reliability (automatic retries)")
    print("  ✅ Decoupling (services independent)")
    print("\nThe trade-off is worth it for production systems!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())