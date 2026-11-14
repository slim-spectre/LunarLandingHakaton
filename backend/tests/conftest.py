from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.pool import StaticPool

from app.main import create_app
from app.storage import Repository, get_repository, metadata, sites


@pytest.fixture
def stage_clock():
    return [datetime(2026, 11, 14, 12, 0, tzinfo=UTC)]


@pytest.fixture
def stage_repo(stage_clock):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(
            insert(sites),
            [
                {
                    "id": "test-apollo",
                    "name": "Synthetic Apollo",
                    "category": "apollo",
                    "latitude": 0.0,
                    "longitude": 23.0,
                    "description": "Test fixture only",
                    "source_url": "https://example.org/fixture",
                    "quickmap_url": None,
                    "terrain_region_id": None,
                },
                {
                    "id": "test-artemis",
                    "name": "Synthetic Artemis",
                    "category": "artemis",
                    "latitude": -89.44,
                    "longitude": -137.9,
                    "description": "Test fixture only",
                    "source_url": "https://example.org/fixture",
                    "quickmap_url": None,
                    "terrain_region_id": None,
                },
            ],
        )
    yield Repository(engine, clock=lambda: stage_clock[0])
    engine.dispose()


@pytest.fixture
def stage_client(stage_repo):
    app = create_app()
    app.dependency_overrides[get_repository] = lambda: stage_repo
    with TestClient(app) as client:
        yield client
