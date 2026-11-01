"""Celery Distributed Application & Queue Configuration.

Implements Module 3 of Phase 4:
- Multiple specialized worker queues for independent horizontal scaling.
- Configurable broker and result backends via Redis.
- Eager mode and in-process fallback when Celery or Redis is uninstalled/offline.
- Strict task serialization (JSON only, no pickle).
"""

import os
import uuid

# Redis broker URL
REDIS_BROKER_URL = os.getenv("PRAMANA_CELERY_BROKER_URL", os.getenv("PRAMANA_REDIS_URL", "redis://localhost:6379/1"))
REDIS_RESULT_URL = os.getenv("PRAMANA_CELERY_RESULT_URL", os.getenv("PRAMANA_REDIS_URL", "redis://localhost:6379/2"))

# Queue definitions
QUEUE_DOCUMENT_PROCESSING = "document_processing"
QUEUE_AI_VERIFICATION = "ai_verification"
QUEUE_FORENSIC_ANALYSIS = "forensic_analysis"
QUEUE_RISK_SCORING = "risk_scoring"
QUEUE_CERTIFICATE_VERIFICATION = "certificate_verification"
QUEUE_REPORT_GENERATION = "report_generation"
QUEUE_NOTIFICATIONS = "notifications"

try:
    from celery import Celery as RealCelery

    celery_app = RealCelery(
        "pramana",
        broker=REDIS_BROKER_URL,
        backend=REDIS_RESULT_URL,
    )
    celery_app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,
        task_soft_time_limit=240,
        worker_prefetch_multiplier=1,
        task_routes={
            "pramana.distributed.tasks.process_document_pipeline": {"queue": QUEUE_DOCUMENT_PROCESSING},
            "pramana.distributed.tasks.scrutinize_application_async": {"queue": QUEUE_AI_VERIFICATION},
            "pramana.distributed.tasks.analyze_forensics_async": {"queue": QUEUE_FORENSIC_ANALYSIS},
            "pramana.distributed.tasks.compute_risk_score_async": {"queue": QUEUE_RISK_SCORING},
            "pramana.distributed.tasks.verify_certificate_async": {"queue": QUEUE_CERTIFICATE_VERIFICATION},
            "pramana.distributed.tasks.sync_crl_async": {"queue": QUEUE_CERTIFICATE_VERIFICATION},
            "pramana.distributed.tasks.generate_compliance_report_async": {"queue": QUEUE_REPORT_GENERATION},
        },
    )
    if os.getenv("PRAMANA_CELERY_EAGER", "true").lower() in ("true", "1", "yes"):
        celery_app.conf.update(
            task_always_eager=True,
            task_eager_propagates=True,
        )

except ImportError:
    # Resilient fallback when celery package is not installed in local development
    class MockAsyncResult:
        def __init__(self, task_id: str, result: any = None):
            self.id = task_id
            self.status = "SUCCESS"
            self.result = result

        def get(self, *args, **kwargs):
            return self.result

    class FallbackCelery:
        def __init__(self, *args, **kwargs):
            self.conf = {}

        def task(self, *dargs, **dkwargs):
            def decorator(fn):
                class BoundTask:
                    def __init__(self, func):
                        self.func = func
                        self.name = func.__name__
                        self.max_retries = dkwargs.get("max_retries", 3)

                    def delay(self, *args, **kwargs):
                        task_id = f"task_{uuid.uuid4().hex[:12]}"
                        # Create mock request context
                        request_obj = type("Req", (), {"id": task_id, "retries": 0})()
                        bound_self = type("Self", (), {
                            "request": request_obj,
                            "max_retries": self.max_retries,
                            "retry": lambda exc=None, **kw: None,
                        })()
                        res = self.func(bound_self, *args, **kwargs)
                        return MockAsyncResult(task_id, res)

                    def apply_async(self, args=None, kwargs=None, **opts):
                        return self.delay(*(args or ()), **(kwargs or {}))

                    def __call__(self, *args, **kwargs):
                        task_id = f"task_{uuid.uuid4().hex[:12]}"
                        request_obj = type("Req", (), {"id": task_id, "retries": 0})()
                        bound_self = type("Self", (), {
                            "request": request_obj,
                            "max_retries": self.max_retries,
                            "retry": lambda exc=None, **kw: None,
                        })()
                        return self.func(bound_self, *args, **kwargs)

                return BoundTask(fn)
            return decorator

    celery_app = FallbackCelery("pramana")
