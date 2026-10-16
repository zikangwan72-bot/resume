from alembic import context

import app.main  # noqa: F401  (imports every router, so all models are registered)
from app.db.database import Base, engine
from migrations.common import run

run(context, Base.metadata, engine, version_table="alembic_version")
