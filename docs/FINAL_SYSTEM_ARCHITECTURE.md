# PRAMANA — Final System Architecture

## Architecture Diagram & Component Topology

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            PRESENTATION LAYER                                │
│   React 19 + TypeScript + Vite + Tailwind CSS + Lucide Icons + Three.js     │
│   (Officer Scrutiny, Trust Dashboard, Offline Tablet Workspace, Simulation)  │
└──────────────────────────────────────┬───────────────────────────────────────┘
                                       │ HTTPS / WSS / REST
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                             API GATEWAY LAYER                                │
│   FastAPI + Correlation Tracing + Token Bucket Throttling + SSRF Guard      │
│   (Admin, Applications, Integrations, Offline Field, Drishti, Trust API)    │
└──────────────┬───────────────────────┬───────────────────────┬───────────────┘
               │                       │                       │
               ▼                       ▼                       ▼
┌─────────────────────────┐ ┌─────────────────────────┐ ┌──────────────────────┐
│   INTELLIGENCE ENGINES  │ │  GOVERNMENT INTEGRATION │ │ TRUST INFRASTRUCTURE │
│ - Devanagari OCR        │ │ - API Setu Adapter      │ │ - Ed25519 Checkpoints│
│ - YOLOX Model Inspection│ │ - DigiLocker / NAD Pull │ │ - AES-256-GCM Keystore│
│ - C2PA Content Provenanc│ │ - 12-Step Gov Pipeline  │ │ - Hardware HSM / KMS │
│ - Cross-Doc Consistency │ │ - Purpose-Bound Consent │ │ - Merkle Audit Chain │
│ - 6D Explainable Risk   │ │ - CCA Trust Validator   │ │ - Offline JWS Signing│
│ - Regulatory RAG & Diff │ │ - Outbound Circuit Brek.│ │ - X.509 CRL / OCSP   │
└──────────────┬──────────┘ └──────────┬──────────────┘ └──────────┬───────────┘
               │                       │                           │
               ▼                       ▼                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                    DISTRIBUTED BACKEND & DATA LAYER                          │
│   PostgreSQL 16 (Multi-Tenant) / SQLite WAL + Redis 7 (Coordination & Lock)  │
│   Celery 5 Workers (Async 12-Stage Pipeline) + S3 / MinIO Object Storage     │
└──────────────────────────────────────────────────────────────────────────────┘
```

