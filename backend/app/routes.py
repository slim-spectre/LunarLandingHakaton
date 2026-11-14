from collections.abc import Callable
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.exceptions import RequestValidationError
from starlette.concurrency import run_in_threadpool

from app.core.problems import ErrorEnvelope
from app.requests import Category, NowRequest
from app.resources import get_resources
from app.results import NowResult
from app.storage import Repository, get_repository


async def no_get_body(request: Request):
    if request.method == "GET":
        async for chunk in request.stream():
            if chunk:
                raise RequestValidationError([{"type": "unexpected_body", "loc": ("body",)}])


def query_fields(*allowed):
    def validate(request: Request):
        errors = [
            {"type": "extra_forbidden", "loc": ("query", name)}
            for name in request.query_params
            if name not in allowed
        ]
        errors.extend(
            {"type": "extra_forbidden", "loc": ("query", name)}
            for name in allowed
            if len(request.query_params.getlist(name)) > 1
        )
        if errors:
            raise RequestValidationError(errors)

    return validate


router = APIRouter(
    prefix="/api/v1",
    dependencies=[Depends(no_get_body)],
    responses={
        status: {"model": ErrorEnvelope} for status in (400, 404, 409, 410, 422, 429, 500, 502, 503)
    },
)
Repo = Annotated[Repository, Depends(get_repository)]


@router.get("/sites", dependencies=[Depends(query_fields("category", "limit", "offset"))])
def list_sites(
    repository: Repo,
    category: Category | None = None,
    limit: Annotated[int, Query(ge=1)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return repository.list_sites(category, limit, offset)


@router.get("/sites/{site_id}", dependencies=[Depends(query_fields())])
def get_site(site_id: str, repository: Repo):
    return repository.site(site_id)


def get_csa_fetcher():
    from app.resources import fetch_resources

    return fetch_resources


@router.get("/resources/csa", dependencies=[Depends(query_fields("limit"))])
def csa_resources(
    repository: Repo,
    fetcher: Annotated[Callable, Depends(get_csa_fetcher)],
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
):
    return get_resources(repository, limit, fetcher)


@router.post("/ephemeris/now", status_code=202, dependencies=[Depends(query_fields())])
async def submit_now(payload: NowRequest, request: Request, repository: Repo):
    return await run_in_threadpool(
        repository.submit,
        payload,
        request.state.request_id,
        submitted=await request.json(),
    )


@router.get("/jobs/{job_id}", dependencies=[Depends(query_fields())])
def job_status(job_id: UUID, repository: Repo):
    return repository.status(str(job_id))


@router.get(
    "/jobs/{job_id}/result", response_model=NowResult, dependencies=[Depends(query_fields())]
)
def job_result(job_id: UUID, repository: Repo):
    return repository.result(str(job_id))
