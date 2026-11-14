import hashlib
import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    delete,
    insert,
    null,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.astronomy import normalize_longitude
from app.core.database import get_engine
from app.core.problems import APIProblem
from app.requests import CatalogSite, NowRequest, canonical_time

MODEL_VERSION = "geometric-now-v1"
metadata = MetaData()
json_type = JSON().with_variant(JSONB(), "postgresql")
sites = Table(
    "sites",
    metadata,
    Column("id", String, primary_key=True),
    Column("name", String, nullable=False),
    Column("category", String, nullable=False),
    Column("latitude", Float, nullable=False),
    Column("longitude", Float, nullable=False),
    Column("description", String, nullable=False),
    Column("source_url", String, nullable=False),
    Column("quickmap_url", String),
    Column("terrain_region_id", String),
    CheckConstraint("latitude >= -90 AND latitude <= 90"),
    CheckConstraint("longitude >= -180 AND longitude < 180"),
    CheckConstraint("category IN ('artemis','apollo','clps','international')"),
)
jobs = Table(
    "observation_jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("kind", String, nullable=False),
    Column("status", String, nullable=False),
    Column("request_id", String(36), nullable=False),
    Column("submitted", json_type, nullable=False),
    Column("normalized", json_type, nullable=False),
    Column("cache_key", String(64), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("result", json_type),
    Column("error", json_type),
    Column("lease_token", String(36)),
    Column("lease_expires_at", DateTime(timezone=True)),
    Column("attempts", Integer, nullable=False),
    Column("result_expires_at", DateTime(timezone=True)),
    CheckConstraint("kind = 'now'"),
    CheckConstraint("status IN ('queued','running','succeeded','failed')"),
)
Index("ix_jobs_queue", jobs.c.status, jobs.c.created_at)
Index("ix_jobs_lease", jobs.c.status, jobs.c.lease_expires_at)
Index("ix_jobs_expiry", jobs.c.result_expires_at)
observation_cache = Table(
    "observation_cache",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("payload", json_type, nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)
Index("ix_observation_cache_expiry", observation_cache.c.expires_at)
resource_cache = Table(
    "resource_cache",
    metadata,
    Column("key", String, primary_key=True),
    Column("payload", json_type, nullable=False),
    Column("fetched_at", DateTime(timezone=True), nullable=False),
)


def utcnow():
    return datetime.now(UTC)


def as_utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def iso(value):
    return as_utc(value).isoformat().replace("+00:00", "Z") if value else None


def request_key(normalized):
    scientific = {
        key: normalized[key]
        for key in (
            "target_time",
            "observer_height_m",
            "visibility_margin_deg",
            "horizon_mode",
            "model_version",
        )
    }
    scientific.update(
        {key: normalized["site"][key] for key in ("latitude", "longitude", "surface_elevation_m")}
    )
    return hashlib.sha256(json.dumps(scientific, sort_keys=True).encode()).hexdigest()


class Repository:
    def __init__(self, engine, clock=utcnow):
        self.engine = engine
        self.clock = clock

    def site(self, site_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(sites).where(sites.c.id == site_id)).mappings().first()
        if row is None:
            raise APIProblem(404, "SITE_NOT_FOUND", "Site was not found")
        return dict(row)

    def list_sites(self, category, limit, offset):
        from sqlalchemy import func

        predicate = sites.c.category == category if category else True
        with self.engine.connect() as conn:
            total = conn.scalar(select(func.count()).select_from(sites).where(predicate))
            items = (
                conn.execute(
                    select(sites).where(predicate).order_by(sites.c.id).limit(limit).offset(offset)
                )
                .mappings()
                .all()
            )
        return {
            "items": [dict(row) for row in items],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def resolve(self, request: NowRequest, submitted=None):
        if request.horizon_mode != "geometric":
            raise APIProblem(
                422,
                "TERRAIN_UNAVAILABLE",
                "Terrain mode is unavailable in Stage 1",
                [
                    {"field": "horizon_mode", "reason": "no_data"},
                ],
            )
        if isinstance(request.site, CatalogSite):
            record = self.site(request.site.site_id)
            site = {
                "site_id": record["id"],
                **{k: record[k] for k in ("name", "latitude", "longitude")},
            }
        else:
            site = {"site_id": None, **request.site.model_dump()}
        site["latitude"] = float(site["latitude"])
        site["longitude"] = normalize_longitude(float(site["longitude"]))
        # Geometric height is relative to Horizons' reference surface, not a measured DEM.
        site.update(surface_elevation_m=0.0, observer_height_m=request.observer_height_m)
        return {
            "site": site,
            "target_time": canonical_time(
                submitted["target_time"] if submitted else iso(request.target_time)
            ),
            "observer_height_m": request.observer_height_m,
            "visibility_margin_deg": request.visibility_margin_deg,
            "horizon_mode": request.horizon_mode,
            "model_version": MODEL_VERSION,
        }

    def submit(self, request, request_id, submitted=None):
        normalized = self.resolve(request, submitted)
        job_id = str(uuid4())
        with self.engine.begin() as conn:
            conn.execute(
                insert(jobs).values(
                    id=job_id,
                    kind="now",
                    status="queued",
                    request_id=request_id,
                    submitted=submitted
                    if submitted is not None
                    else request.model_dump(mode="json"),
                    normalized=normalized,
                    cache_key=request_key(normalized),
                    created_at=self.clock(),
                    attempts=0,
                )
            )
        return {
            "job_id": job_id,
            "kind": "now",
            "status": "queued",
            "status_url": f"/api/v1/jobs/{job_id}",
            "result_url": f"/api/v1/jobs/{job_id}/result",
        }

    def job(self, job_id):
        with self.engine.connect() as conn:
            row = conn.execute(select(jobs).where(jobs.c.id == str(job_id))).mappings().first()
        if row is None:
            raise APIProblem(404, "JOB_NOT_FOUND", "Job was not found")
        return dict(row)

    def status(self, job_id):
        job = self.job(job_id)
        return {
            "job_id": job["id"],
            "kind": job["kind"],
            "status": job["status"],
            **{key: iso(job[key]) for key in ("created_at", "started_at", "finished_at")},
            "result_url": f"/api/v1/jobs/{job_id}/result",
            "error": job["error"],
        }

    def result(self, job_id):
        job = self.job(job_id)
        if job["result_expires_at"] and as_utc(job["result_expires_at"]) <= self.clock():
            raise APIProblem(410, "JOB_EXPIRED", "Job result has expired")
        if job["status"] == "failed":
            raise APIProblem(409, "JOB_FAILED", "Job execution failed", job["error"]["details"])
        if job["status"] != "succeeded":
            raise APIProblem(409, "JOB_NOT_READY", "Job result is not ready")
        return job["result"]

    @contextmanager
    def provider_lock(self, key):
        with self.engine.connect() as conn:
            acquired = True
            if conn.dialect.name == "postgresql":
                from sqlalchemy import text

                acquired = bool(
                    conn.scalar(text("SELECT pg_try_advisory_lock(:key)"), {"key": key})
                )
            try:
                yield acquired
            finally:
                if acquired and conn.dialect.name == "postgresql":
                    conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})

    def claim(self, lease_seconds):
        now = self.clock()
        with self.engine.begin() as conn:
            conn.execute(
                update(jobs)
                .where(
                    jobs.c.status == "running",
                    jobs.c.lease_expires_at <= now,
                )
                .values(status="queued", started_at=None, lease_token=None, lease_expires_at=None)
            )
            expired_jobs = (
                select(jobs.c.id)
                .where(
                    jobs.c.result_expires_at <= now,
                    jobs.c.result.is_not(None),
                )
                .limit(100)
            )
            conn.execute(update(jobs).where(jobs.c.id.in_(expired_jobs)).values(result=null()))
            expired_cache = (
                select(observation_cache.c.key)
                .where(
                    observation_cache.c.expires_at <= now,
                )
                .limit(100)
            )
            conn.execute(
                delete(observation_cache).where(observation_cache.c.key.in_(expired_cache))
            )
            row = (
                conn.execute(
                    select(jobs)
                    .where(jobs.c.status == "queued")
                    .order_by(jobs.c.created_at, jobs.c.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            token = str(uuid4())
            conn.execute(
                update(jobs)
                .where(jobs.c.id == row["id"])
                .values(
                    status="running",
                    started_at=now,
                    lease_token=token,
                    lease_expires_at=now + timedelta(seconds=lease_seconds),
                    attempts=row["attempts"] + 1,
                )
            )
            return {**dict(row), "lease_token": token}

    def cache_result(self, key):
        with self.engine.connect() as conn:
            return conn.scalar(
                select(observation_cache.c.payload).where(
                    observation_cache.c.key == key,
                    observation_cache.c.expires_at > self.clock(),
                )
            )

    def upsert(self, conn, table, key, **values):
        statement = (pg_insert if conn.dialect.name == "postgresql" else sqlite_insert)(table)
        conn.execute(
            statement.values(key=key, **values).on_conflict_do_update(
                index_elements=[table.c.key],
                set_=values,
            )
        )

    def finish(self, job, *, result=None, error=None, cache_seconds=3600, retention_days=7):
        now = self.clock()
        with self.engine.begin() as conn:
            updated = conn.execute(
                update(jobs)
                .where(
                    jobs.c.id == job["id"],
                    jobs.c.status == "running",
                    jobs.c.lease_token == job["lease_token"],
                    jobs.c.lease_expires_at > now,
                )
                .values(
                    status="failed" if error else "succeeded",
                    result=result,
                    error=error,
                    finished_at=now,
                    lease_token=None,
                    lease_expires_at=None,
                    result_expires_at=now + timedelta(days=retention_days) if result else None,
                )
            )
            if updated.rowcount and result and result["meta"]["data_status"] == "fresh":
                self.upsert(
                    conn,
                    observation_cache,
                    job["cache_key"],
                    payload=result,
                    expires_at=now + timedelta(seconds=cache_seconds),
                )
            return updated.rowcount == 1

    def resource(self, key):
        with self.engine.connect() as conn:
            row = (
                conn.execute(select(resource_cache).where(resource_cache.c.key == key))
                .mappings()
                .first()
            )
        return dict(row) if row else None

    def save_resource(self, key, payload, fetched_at):
        with self.engine.begin() as conn:
            self.upsert(conn, resource_cache, key, payload=payload, fetched_at=fetched_at)


def get_repository():
    return Repository(get_engine())
