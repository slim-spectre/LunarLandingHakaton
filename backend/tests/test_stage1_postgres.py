import os
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select
from sqlalchemy.pool import NullPool
from test_stage1_jobs import REQUEST, controlled

from app.core.config import get_settings
from app.core.database import get_engine
from app.requests import NowRequest
from app.storage import Repository, jobs
from app.worker import HORIZONS_LOCK, run_once

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_repo(monkeypatch, stage_clock):
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL test database")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    get_engine.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")
    engine = create_engine(url, poolclass=NullPool)
    yield Repository(engine, clock=lambda: stage_clock[0])
    engine.dispose()
    get_engine().dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


def test_versioned_seed_and_durable_job_cache_on_postgresql(pg_repo):
    catalog = pg_repo.list_sites("apollo", 2, 1)
    assert catalog["total"] == 6 and len(catalog["items"]) == 2
    assert pg_repo.site("shackleton-connecting-ridge")["longitude"] == -137.9
    first = pg_repo.submit(NowRequest.model_validate(REQUEST), str(uuid4()), submitted=REQUEST)[
        "job_id"
    ]
    assert run_once(pg_repo, controlled)
    assert pg_repo.result(first)["meta"]["data_status"] == "fresh"
    second = pg_repo.submit(NowRequest.model_validate(REQUEST), str(uuid4()), submitted=REQUEST)[
        "job_id"
    ]
    assert run_once(pg_repo, lambda value: pytest.fail("A cache hit must not call astronomy"))
    assert pg_repo.result(second)["meta"]["data_status"] == "cached"
    with pg_repo.engine.connect() as connection:
        assert connection.scalar(select(jobs.c.submitted).where(jobs.c.id == first)) == REQUEST


def test_global_provider_slot_and_claim_fencing_on_postgresql(pg_repo, stage_clock):
    with pg_repo.provider_lock(HORIZONS_LOCK) as first:
        assert first
        with Repository(pg_repo.engine).provider_lock(HORIZONS_LOCK) as second:
            assert not second
    job_id = pg_repo.submit(NowRequest.model_validate(REQUEST), str(uuid4()), submitted=REQUEST)[
        "job_id"
    ]
    old = pg_repo.claim(5)
    assert old["id"] == job_id
    assert Repository(pg_repo.engine, pg_repo.clock).claim(5) is None
    stage_clock[0] += timedelta(seconds=6)
    new = pg_repo.claim(5)
    assert new["lease_token"] != old["lease_token"]
    assert pg_repo.finish(new, result=controlled(new["normalized"]))
    assert not pg_repo.finish(old, error={"code": "stale"})
    assert pg_repo.status(job_id)["status"] == "succeeded"
