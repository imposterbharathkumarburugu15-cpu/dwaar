# Docker Infrastructure & Deployment Guide

## Architecture

PRAMANA provides production-ready multi-stage Docker builds:
1. `docker/Dockerfile.backend`: Multi-stage non-root Python 3.12 container with `libpq` and curl healthchecks.
2. `docker/Dockerfile.frontend`: Multi-stage Node 22 build producing an optimized Nginx static asset reverse proxy container.
3. `docker-compose.yml`: Local full-stack cluster configuration.

## Docker Compose Services

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: pramana
      POSTGRES_USER: pramana
      POSTGRES_PASSWORD: ${PRAMANA_DB_PASSWORD:-pramana_secret_2026}
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes
    volumes:
      - redis_data:/data

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    environment:
      PRAMANA_DB_URL: postgresql://pramana:${PRAMANA_DB_PASSWORD:-pramana_secret_2026}@postgres:5432/pramana
      PRAMANA_REDIS_URL: redis://redis:6379/0

  worker-documents:
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    command: celery -A pramana.distributed.celery_app worker -Q document_processing -c 4

  worker-verification:
    build:
      context: ..
      dockerfile: docker/Dockerfile.backend
    command: celery -A pramana.distributed.celery_app worker -Q ai_verification,forensic_analysis -c 2

  frontend:
    build:
      context: ..
      dockerfile: docker/Dockerfile.frontend
    ports:
      - "80:80"
```

## Running the Cluster Locally

```bash
cd pramana
docker compose up -d
docker compose ps
```

