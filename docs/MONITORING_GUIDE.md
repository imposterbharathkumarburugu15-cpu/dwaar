# Monitoring & Observability Guide

## Prometheus Metrics Exported
- `pramana_http_requests_total`: Total HTTP requests counter labeled by `method`, `endpoint`, `status`.
- `pramana_http_request_duration_seconds`: Request latency summary.
- `pramana_database_connected`: Gauge indicating database connectivity (1=healthy, 0=unhealthy).
- `pramana_database_latency_milliseconds`: Database round-trip query latency.
- `pramana_redis_connected`: Gauge indicating distributed coordinator status.
- `pramana_async_tasks_by_status`: Number of background Celery tasks partitioned by state.
- `pramana_system_info`: Build and release metadata.

