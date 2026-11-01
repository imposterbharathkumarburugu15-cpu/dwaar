# Phase 4 Known Limitations & Production Prerequisites

## Limitations in Local Development Mode

1. **In-Memory Redis Fallback:**
   - In environments where Redis daemon is offline, PRAMANA seamlessly uses `InMemoryFallbackCoordination`.
   - *Limitation:* In-memory coordination state is local to each process and does not share locks across separate physical machine nodes until real Redis is connected.
2. **Synchronous Celery Fallback:**
   - When the `celery` package is absent or Celery worker daemons are not running, `FallbackCelery` executes tasks synchronously within the caller thread.
   - *Production Prerequisite:* In production Kubernetes clusters, separate worker pods must be started using the commands defined in `docker-compose.yml` and `k8s/workers-deployment.yaml`.
3. **Local Storage Default:**
   - By default, documents are stored in local persistent directories (`LocalStorageAdapter`).
   - *Production Prerequisite:* For multi-node cloud clusters spanning multiple zones, `S3StorageAdapter` with AWS S3, Google Cloud Storage, or MinIO should be configured via `PRAMANA_S3_ENDPOINT`.
4. **SQLite Concurrency in Windows File Systems:**
   - SQLite files on Windows lock during certain schema-altering operations. For enterprise concurrent production, PostgreSQL is mandatory.

