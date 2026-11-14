"""Stage 1 catalog, observation jobs and durable caches.

Revision ID: 0001_stage1
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001_stage1"
down_revision = None
branch_labels = None
depends_on = None

SEED_SITES = [
    {
        "id": "apollo-11",
        "name": "Apollo 11",
        "category": "apollo",
        "latitude": 0.67416,
        "longitude": 23.47314,
        "description": "Lunar module landing location in the NASA DE421 Mean Earth/Polar "
        "Axis catalog.",
        "source_url": "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "apollo-12",
        "name": "Apollo 12",
        "category": "apollo",
        "latitude": -3.0128,
        "longitude": -23.4219,
        "description": "Lunar module landing location in the NASA DE421 Mean Earth/Polar "
        "Axis catalog.",
        "source_url": "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "apollo-14",
        "name": "Apollo 14",
        "category": "apollo",
        "latitude": -3.64589,
        "longitude": -17.47194,
        "description": "Lunar module landing location in the NASA DE421 Mean Earth/Polar "
        "Axis catalog.",
        "source_url": "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "apollo-15",
        "name": "Apollo 15",
        "category": "apollo",
        "latitude": 26.13239,
        "longitude": 3.6333,
        "description": "Lunar module landing location in the NASA DE421 Mean Earth/Polar "
        "Axis catalog.",
        "source_url": "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "apollo-16",
        "name": "Apollo 16",
        "category": "apollo",
        "latitude": -8.9734,
        "longitude": 15.5011,
        "description": "Lunar module landing location in the NASA DE421 Mean Earth/Polar "
        "Axis catalog.",
        "source_url": "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "apollo-17",
        "name": "Apollo 17",
        "category": "apollo",
        "latitude": 20.1911,
        "longitude": 30.7723,
        "description": "Lunar module landing location in the NASA DE421 Mean Earth/Polar "
        "Axis catalog.",
        "source_url": "https://nssdc.gsfc.nasa.gov/planetary/lunar/lunar_sites.html",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "shackleton-connecting-ridge",
        "name": "Shackleton Connecting Ridge",
        "category": "artemis",
        "latitude": -89.44,
        "longitude": -137.9,
        "description": "Project reference point supplied in the API v1 specification for "
        "this south-polar study region; not an officially selected landing "
        "location or measured terrain elevation.",
        "source_url": "https://pgda.gsfc.nasa.gov/products/78",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
    {
        "id": "faustini-rim-a",
        "name": "Faustini Rim A",
        "category": "artemis",
        "latitude": -87.45,
        "longitude": 77.0,
        "description": "Project reference point supplied in the API v1 specification for "
        "this south-polar study region; not an officially selected landing "
        "location or measured terrain elevation.",
        "source_url": "https://pgda.gsfc.nasa.gov/products/78",
        "quickmap_url": None,
        "terrain_region_id": None,
    },
]


def upgrade():
    op.create_table(
        "sites",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=False),
        sa.Column("quickmap_url", sa.String()),
        sa.Column("terrain_region_id", sa.String()),
        sa.CheckConstraint("latitude >= -90 AND latitude <= 90"),
        sa.CheckConstraint("longitude >= -180 AND longitude < 180"),
        sa.CheckConstraint("category IN ('artemis','apollo','clps','international')"),
    )
    op.create_table(
        "observation_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(36), nullable=False),
        sa.Column("submitted", postgresql.JSONB(), nullable=False),
        sa.Column("normalized", postgresql.JSONB(), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("result", postgresql.JSONB()),
        sa.Column("error", postgresql.JSONB()),
        sa.Column("lease_token", sa.String(36)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("result_expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind = 'now'"),
        sa.CheckConstraint("status IN ('queued','running','succeeded','failed')"),
    )
    op.create_index("ix_jobs_queue", "observation_jobs", ["status", "created_at"])
    op.create_index("ix_jobs_lease", "observation_jobs", ["status", "lease_expires_at"])
    op.create_index("ix_jobs_expiry", "observation_jobs", ["result_expires_at"])
    op.create_table(
        "observation_cache",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_observation_cache_expiry", "observation_cache", ["expires_at"])
    op.create_table(
        "resource_cache",
        sa.Column("key", sa.String(), primary_key=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )
    table = sa.table(
        "sites",
        *[
            sa.column(name, sa.Float() if name in ("latitude", "longitude") else sa.String())
            for name in SEED_SITES[0]
        ],
    )
    op.bulk_insert(table, SEED_SITES)


def downgrade():
    op.drop_table("resource_cache")
    op.drop_table("observation_cache")
    op.drop_table("observation_jobs")
    op.drop_table("sites")
