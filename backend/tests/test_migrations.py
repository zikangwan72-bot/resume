"""Migrations must build the same schema as the models (fails when a model change lacks a migration)."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine

from app.approval.database import ApprovalBase
from app.db.database import Base
from migrations.common import VERSION_TABLES

BACKEND = Path(__file__).resolve().parents[1]


def _include_object(obj, name, type_, reflected, compare_to):
    return not (type_ == "table" and (name in VERSION_TABLES or (reflected and compare_to is None)))


@pytest.mark.parametrize(
    ("config_name", "metadata"),
    [("alembic", Base.metadata), ("approval", ApprovalBase.metadata)],
)
def test_upgrade_head_matches_models(tmp_path, config_name, metadata):
    main_db = tmp_path / "main.db"
    approval_db = tmp_path / "approval.db"
    # Env vars beat backend/.env, so this never touches a configured real database.
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{main_db.as_posix()}",
        "APPROVAL_DATABASE_URL": f"sqlite:///{approval_db.as_posix()}",
        "LOG_LEVEL": "WARNING",
    }
    for args in (["upgrade", "head"], ["downgrade", "base"], ["upgrade", "head"]):
        subprocess.run(
            [sys.executable, "-m", "alembic", "-n", config_name, *args],
            cwd=BACKEND,
            env=env,
            check=True,
            capture_output=True,
        )

    db_path = main_db if config_name == "alembic" else approval_db
    engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"include_object": _include_object, "compare_type": True}
        )
        assert compare_metadata(context, metadata) == []
    engine.dispose()
