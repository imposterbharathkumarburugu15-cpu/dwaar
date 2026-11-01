# Centralized Observability & Monitoring

## Prometheus Exporter Architecture

PRAMANA exposes a real-time Prometheus metrics scraper endpoint at `/api/v1/metrics`. It collects telemetry without locking application request processing:

### Core Metric Categories

1. **HTTP Throughput & Error Rate:**
   - `pramana_http_requests_total{method="POST",endpoint="/api/v1/applications/process",status="200"}`
   - `pramana_http_request_duration_seconds_sum` & `pramana_http_request_duration_seconds_count`
2. **Distributed Tasks:**
   - `pramana_tasks_dispatched_total{task="process_document_pipeline",queue="document_processing"}`
   - `pramana_async_tasks_by_status{status="COMPLETED"}`
   - `pramana_async_tasks_by_status{status="RETRYING"}`
3. **Infrastructure Health Gauges:**
   - `pramana_database_connected{dialect="postgresql"}`
   - `pramana_database_latency_milliseconds`
   - `pramana_redis_connected{mode="REDIS_CONNECTED"}`
4. **Build & Version Metadata:**
   - `pramana_system_info{version="1.0.0",phase="4",service="pramana-api"} 1`

## Structured Logging & Redaction Filter

Logs are emitted using structured JSON formatting:
- Every HTTP request carries `X-Correlation-ID` / `X-Request-ID` across downstream services.
- Automatic redaction filters scrub passwords, secret keys, private PEM keys, and authorization bearer tokens before emission.

