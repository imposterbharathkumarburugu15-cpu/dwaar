"""Tests for Government Integration Registry & Health Monitoring."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from pramana.db import Base
from pramana.integrations.models import GovernmentProvider
from pramana.integrations.registry import IntegrationRegistry, CANONICAL_PROVIDERS


@pytest.fixture
def db_session(tmp_path):
    db_file = tmp_path / "test_registry.db"
    engine = create_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_initialize_default_providers(db_session):
    registry = IntegrationRegistry()
    created = registry.initialize_default_providers(db_session)
    assert len(created) == len(CANONICAL_PROVIDERS)

    # Calling again should be idempotent
    second_run = registry.initialize_default_providers(db_session)
    assert len(second_run) == 0


def test_list_providers_and_filter(db_session):
    registry = IntegrationRegistry()
    registry.initialize_default_providers(db_session)

    all_providers = registry.list_providers(db_session)
    assert len(all_providers) >= 4

    apisetu_only = registry.list_providers(db_session, category="API_SETU")
    assert len(apisetu_only) == 1
    assert apisetu_only[0].id == "apisetu_national"


def test_update_provider_status(db_session):
    registry = IntegrationRegistry()
    registry.initialize_default_providers(db_session)

    updated = registry.update_provider_status(
        db_session,
        provider_id="apisetu_national",
        status="REAL_SANDBOX_CONNECTED",
        operator="admin_tester",
        reason="Sandbox API keys provisioned",
    )
    assert updated.connection_status == "REAL_SANDBOX_CONNECTED"
    assert updated.last_verified_at is not None


def test_test_connectivity(db_session):
    registry = IntegrationRegistry()
    registry.initialize_default_providers(db_session)

    res = registry.test_connectivity(db_session, "apisetu_national")
    assert res["status"] == "HEALTHY"
    assert res["mode"] == "SIMULATED_SANDBOX"
    assert "latency_ms" in res

