from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"connect_timeout": 2, "options": "-c statement_timeout=2000"},
        hide_parameters=True,
    )


def check_database() -> None:
    with get_engine().connect() as connection:
        if connection.execute(text("SELECT 1")).scalar_one() != 1:
            raise RuntimeError("Unexpected database health result")
