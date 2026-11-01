# PRAMANA Distributed System Architecture

## Architecture Overview

PRAMANA's distributed architecture is designed to support nationwide simultaneous institutional submissions, automated regulatory scrutiny, forensic document analysis, and cryptographic provenance verification.

```mermaid
graph TD
    subgraph Edge Layer
        ING[Kubernetes Ingress / Cloud Gateway]
        TLS[TLS Termination & HSTS]
    end

    subgraph Service Tier
        API1[FastAPI Node 1]
        API2[FastAPI Node 2]
        APIN[FastAPI Node N]
    end

    subgraph Coordination & Cache Tier
        REDIS[(Redis 7 Cluster / Standalone)]
        RL[Sliding Window Rate Limiter]
        LOCK[Distributed Lease Locks]
        CACHE[TTL Cache]
    end

    subgraph Background Asynchronous Processing
        CW_DOC[Celery Worker: document_processing]
        CW_VER[Celery Worker: ai_verification]
        CW_FOR[Celery Worker: forensic_analysis]
        CW_NOT[Celery Worker: notifications]
    end

    subgraph Persistence & Storage
        PG[(PostgreSQL 16 HA / Connection Pool)]
        OBJ[Object Storage Abstraction: Local / S3 / MinIO]
    end

    ING --> TLS --> API1 & API2 & APIN
    API1 & API2 & APIN --> REDIS
    API1 & API2 & APIN --> PG
    API1 & API2 & APIN --> OBJ
    API1 & API2 & APIN -. Task Dispatch .-> REDIS
    REDIS -. Task Queue .-> CW_DOC & CW_VER & CW_FOR & CW_NOT
    CW_DOC & CW_VER & CW_FOR & CW_NOT --> PG
    CW_DOC & CW_VER & CW_FOR & CW_NOT --> OBJ
```

## Core Principles

1. **Stateless API Replicas:** Authentication relies on signed HTTP-only session cookies and CSRF tokens verified against cryptographic signatures. Any API instance can handle any incoming request.
2. **Distributed Locks with Leases:** Application scrutiny operations acquire exclusive locks (`prm:lock:scrutiny:{app_id}`) with automatic TTL expiration to prevent race conditions during concurrent runs.
3. **Queue Segmentation:** Independent worker pools isolate high-frequency, compute-heavy tasks (OCR and forensics) from low-latency critical tasks (status polling and health checks).
4. **Resilient Local Fallbacks:** In standalone test environments, the system automatically falls back to in-memory coordination and eager task execution without crashing or requiring external daemon processes.

