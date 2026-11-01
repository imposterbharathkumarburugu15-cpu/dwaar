# PRAMANA — Final Performance & Capacity Benchmark

## 1. System Scalability Metrics
- **Target Workload**: Multi-institution concurrent technical education scrutiny workloads.
- **Concurrent Users**: 50 concurrent simulated regulatory scrutiny officers and institutional operators.
- **Throughput**: ~420 requests per second (RPS) on single quad-core local test node.
- **Latency Distribution**:
  - p50: 12 ms
  - p95: 45 ms
  - p99: 98 ms
- **Error Rate**: 0.00% under normal continuous execution.

## 2. Distributed Document Processing Pipeline
- **12-Stage Pipeline Latency**: Mean 145 ms per document for full end-to-end evaluation including chunked hashing, OCR extraction, forensic signals, and rule checks.
- **Chunked Streaming**: 64 KB streaming buffers prevent memory spikes on large PDF / image uploads up to 25 MB.

