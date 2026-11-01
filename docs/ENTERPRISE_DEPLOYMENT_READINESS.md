# PRAMANA — Enterprise Deployment Readiness

## Production Topology & Cloud Compatibility
PRAMANA is engineered for deployment across major container orchestration and cloud environments.

## Deployment Artifacts
- **Docker**:
  - Multi-stage `Dockerfile` optimizing build size and running as unprivileged `appuser`.
  - `docker-compose.yml` for unified local staging of Web API, PostgreSQL, Redis, and Celery Worker.
- **Kubernetes**:
  - `k8s/base/`: Modular manifests for Deployment, Service, ConfigMap, Ingress, PersistentVolumeClaim, and HorizontalPodAutoscaler.
- **Observability**:
  - Prometheus `/api/v1/metrics` exporter.
  - Correlation ID propagation (`X-Correlation-ID`, `X-Request-ID`) across distributed services.
- **Disaster Recovery**:
  - Automated point-in-time snapshot orchestrator with SHA-256 manifest integrity verification.

