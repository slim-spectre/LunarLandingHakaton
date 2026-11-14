import argparse
import logging
import multiprocessing
import signal
import time
from copy import deepcopy

from app.astronomy import (
    HorizonsError,
    HorizonsHttpError,
    HorizonsProvider,
    HorizonsTransportError,
    calculate_geometric_observation,
)
from app.core.config import get_settings
from app.core.problems import APIProblem
from app.requests import canonical_time
from app.results import NowResult
from app.storage import MODEL_VERSION, get_repository, iso, utcnow

LOGGER = logging.getLogger(__name__)
HORIZONS_LOCK = 740101


def execute_observation(normalized):
    settings = get_settings()
    point = calculate_geometric_observation(
        latitude=normalized["site"]["latitude"],
        longitude=normalized["site"]["longitude"],
        target_time=normalized["target_time"],
        observer_height_m=normalized["observer_height_m"],
        visibility_margin_deg=normalized["visibility_margin_deg"],
        provider=HorizonsProvider(timeout=settings.horizons_timeout_seconds, max_retries=1),
    )
    if canonical_time(point.timestamp) != normalized["target_time"]:
        raise APIProblem(
            502, "PROVIDER_TIME_MISMATCH", "Astronomy service changed the requested time"
        )
    if not point.sources:
        raise APIProblem(502, "PROVIDER_ERROR", "Astronomy service returned no provenance")
    return {
        "site": normalized["site"],
        "point": point.model_dump(),
        "meta": {
            "model_version": MODEL_VERSION,
            "generated_at": iso(utcnow()),
            "data_status": "fresh",
            "horizon_mode": "geometric",
            "time_resolution_minutes": None,
            "terrain_dataset_id": None,
            "sources": [s.to_contract_source() for s in point.sources],
        },
    }


def calculation_error(exc):
    if isinstance(exc, APIProblem):
        return exc
    if isinstance(exc, HorizonsTransportError) or (
        isinstance(exc, HorizonsHttpError) and exc.status_code in (429, 503, 504)
    ):
        return APIProblem(503, "ASTRONOMY_UNAVAILABLE", "Astronomy provider is unavailable")
    if isinstance(exc, HorizonsError | ValueError):
        return APIProblem(
            502, "PROVIDER_ERROR", "Astronomy provider returned an invalid observation"
        )
    return APIProblem(500, "INTERNAL_ERROR", "Observation execution failed")


def _child(normalized, sender):
    try:
        sender.send((execute_observation(normalized), None))
    except Exception as exc:
        problem = calculation_error(exc)
        sender.send((None, (problem.status, problem.code, problem.message, problem.details)))
    finally:
        sender.close()


def isolated_execution(normalized):
    settings = get_settings()
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    child = context.Process(target=_child, args=(normalized, sender), daemon=True)
    child.start()
    sender.close()
    try:
        if not receiver.poll(settings.observation_timeout_seconds):
            raise APIProblem(
                503, "ASTRONOMY_TIMEOUT", "Observation exceeded its execution deadline"
            )
        try:
            result, error = receiver.recv()
        except EOFError as exc:
            raise APIProblem(
                503, "WORKER_INTERRUPTED", "Observation executor stopped unexpectedly"
            ) from exc
        if error:
            raise APIProblem(*error)
        return result
    finally:
        receiver.close()
        if child.is_alive():
            child.terminate()
        child.join(timeout=5)
        if child.is_alive():
            child.kill()
            child.join(timeout=5)


def run_once(repository, executor=isolated_execution):
    settings = get_settings()
    with repository.provider_lock(HORIZONS_LOCK) as acquired:
        if not acquired:
            return False
        job = repository.claim(settings.observation_timeout_seconds + 30)
        if job is None:
            return False
        try:
            result = repository.cache_result(job["cache_key"])
            if result is not None:
                result = deepcopy(result)
                result["site"] = job["normalized"]["site"]
                result["meta"]["data_status"] = "cached"
            else:
                result = executor(job["normalized"])
            result = NowResult.model_validate(result).model_dump(mode="json")
            repository.finish(
                job,
                result=result,
                cache_seconds=settings.observation_cache_seconds,
                retention_days=settings.result_retention_days,
            )
        except Exception as exc:
            repository.finish(
                job,
                error=calculation_error(exc).error(job["request_id"]),
                retention_days=settings.result_retention_days,
            )
    return True


def main():
    parser = argparse.ArgumentParser(description="Durable single-observation PostgreSQL worker")
    parser.add_argument("--once", action="store_true", help="Process at most one job, then exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    repository = get_repository()
    stopping = False

    def stop(signum, frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    while not stopping:
        try:
            worked = run_once(repository)
        except Exception:
            LOGGER.error("Worker database operation failed; queued jobs remain durable")
            worked = False
        if args.once:
            break
        if not worked:
            time.sleep(1)


if __name__ == "__main__":
    main()
