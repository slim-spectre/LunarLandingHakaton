from alembic import context
from sqlalchemy import MetaData

from app.core.config import get_settings
from app.core.database import get_engine

target_metadata = MetaData()

if context.is_offline_mode():
    context.configure(
        url=get_settings().database_url, target_metadata=target_metadata, literal_binds=True
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    with get_engine().connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
