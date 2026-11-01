# Production Deployment Guide

## Prerequisites & Architecture
- Kubernetes 1.28+ cluster or Docker Swarm.
- PostgreSQL 16+ instance with connection pooling.
- Redis 7+ cluster (sentinel or cluster mode).
- S3-compatible Object Storage (AWS S3 or MinIO).

## Manifest Structure
- `k8s/base/deployment.yaml`: FastAPI stateless API servers with liveness/readiness probes.
- `k8s/base/celery-worker.yaml`: Dedicated background document processing workers.
- `k8s/base/service.yaml`: ClusterIP service with Prometheus annotations.
- `k8s/base/ingress.yaml`: Ingress with cert-manager TLS termination.
- `k8s/base/hpa.yaml`: Horizontal Pod Autoscaler scaling from 3 to 20 replicas based on CPU and request latency.

