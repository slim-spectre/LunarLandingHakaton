import os

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.database import check_database, get_engine
from app.main import create_app


@pytest.mark.integration
def test_health_checks_real_postgresql(monkeypatch):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to explicitly enable the PostgreSQL integration test")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    try:
        check_database()
        with TestClient(create_app()) as client:
            assert client.get("/api/v1/health").status_code == 200
    finally:
        get_engine().dispose()
        get_engine.cache_clear()
        get_settings.cache_clear()
