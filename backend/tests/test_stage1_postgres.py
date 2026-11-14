import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from threading import Event
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
from app.resources import get_resources
from app.storage import Repository, iso, jobs
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


def test_parallel_csa_cold_cache_requests_share_one_refresh_on_postgresql(
    pg_repo, stage_clock, monkeypatch
):
    started, release, contended = Event(), Event(), Event()
    waiter = Repository(pg_repo.engine, pg_repo.clock)
    original_lock = waiter.provider_lock
    calls = []

    @contextmanager
    def observed_lock(key):
        with original_lock(key) as acquired:
            if not acquired:
                contended.set()
            yield acquired

    def fetch():
        calls.append(1)
        started.set()
        assert release.wait(5), "Timed out releasing the controlled CSA fetch"
        return {"items": [], "fetched_at": iso(stage_clock[0])}

    monkeypatch.setattr(waiter, "provider_lock", observed_lock)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(get_resources, pg_repo, 1, fetch)
        try:
            assert started.wait(3), "The controlled CSA fetch did not start"
            second = pool.submit(get_resources, waiter, 10, fetch)
            assert contended.wait(3), "The second request did not observe the active refresh"
            with pytest.raises(TimeoutError):
                second.result(timeout=0.05)
        finally:
            release.set()
        fresh, cached = first.result(timeout=5), second.result(timeout=5)
    assert calls == [1]
    assert fresh["data_status"] == "fresh" and cached["data_status"] == "cached"
    assert fresh["items"] == cached["items"] == []
    assert fresh["fetched_at"] == cached["fetched_at"]
