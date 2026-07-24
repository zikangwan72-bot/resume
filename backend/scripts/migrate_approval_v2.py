"""One-time, backup-first rebuild of an empty legacy approval SQLite database."""

# ruff: noqa: E402, I001

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.approval.database import ApprovalBase
from app.approval.models import ApprovalUser, ProcessApp, ProcessVersion
from app.approval.seed import APPROVAL_USERS, PROCESS_APP_SEEDS


LEGACY_TABLES = {
    "approval_users",
    "form_templates",
    "flow_templates",
    "approval_types",
    "approval_requests",
    "approval_nodes",
    "approval_actions",
}
V2_TABLES = {"process_apps", "process_versions"}


class MigrationAbort(RuntimeError):
    """Raised when the source database cannot safely be rebuilt."""


def preflight(source: Path) -> int:
    if not source.is_file():
        raise MigrationAbort(f"source database does not exist: {source}")

    source_uri = f"file:{source.as_posix()}?mode=ro"
    connection = sqlite3.connect(source_uri, uri=True)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        if V2_TABLES <= tables:
            raise MigrationAbort("database already uses the approval v2 schema")
        missing_tables = sorted(LEGACY_TABLES - tables)
        if missing_tables:
            raise MigrationAbort(
                f"legacy schema incomplete; missing tables: {', '.join(missing_tables)}"
            )
        runtime_counts = {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("approval_requests", "approval_nodes", "approval_actions")
        }
    finally:
        connection.close()

    if any(runtime_counts.values()):
        raise MigrationAbort(
            ", ".join(f"{table}_count={count}" for table, count in runtime_counts.items())
            + "; source database was not changed"
        )
    return runtime_counts["approval_requests"]


def seed_v2(session: Session) -> None:
    for user_data in APPROVAL_USERS:
        user = session.get(ApprovalUser, user_data["id"])
        if user is None:
            session.add(ApprovalUser(**user_data))
        else:
            for field, value in user_data.items():
                setattr(user, field, value)
    session.flush()

    for seed in PROCESS_APP_SEEDS:
        app = session.scalar(select(ProcessApp).where(ProcessApp.code == seed["code"]))
        if app is None:
            app = ProcessApp(
                code=seed["code"],
                name=seed["name"],
                category="通用审批",
                description=seed["description"],
                status="published",
            )
            session.add(app)
            session.flush()
        else:
            app.name = seed["name"]
            app.description = seed["description"]
            app.status = "published"

        version = session.scalar(
            select(ProcessVersion).where(
                ProcessVersion.process_app_id == app.id,
                ProcessVersion.version_number == 1,
            )
        )
        if version is None:
            version = ProcessVersion(
                process_app_id=app.id,
                version_number=1,
                status="published",
                form_schema=seed["form_schema"],
                flow_schema=seed["flow_schema"],
                published_at=datetime.now(UTC),
            )
            session.add(version)
            session.flush()
        else:
            version.status = "published"
            version.form_schema = seed["form_schema"]
            version.flow_schema = seed["flow_schema"]
            version.published_at = version.published_at or datetime.now(UTC)
        app.current_version_id = version.id


def verify_v2_database(path: Path) -> tuple[int, int, str, str]:
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA foreign_keys = ON")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_rows = connection.execute("PRAGMA foreign_key_check").fetchall()
        apps = connection.execute(
            """
            SELECT app.id, app.code, app.status, app.current_version_id,
                   version.version_number, version.status,
                   version.form_schema, version.flow_schema
            FROM process_apps AS app
            LEFT JOIN process_versions AS version ON version.id = app.current_version_id
            ORDER BY app.code
            """
        ).fetchall()
    finally:
        connection.close()

    expected_codes = ["expense", "leave", "purchase"]
    if [row[1] for row in apps] != expected_codes:
        raise MigrationAbort(f"expected exactly three process apps, found {len(apps)}")
    if any(row[2] != "published" or row[4] != 1 or row[5] != "published" for row in apps):
        raise MigrationAbort("process app current-version pointers are not published v1")
    expected_seeds = {seed["code"]: seed for seed in PROCESS_APP_SEEDS}
    for row in apps:
        expected = expected_seeds[row[1]]
        if json.loads(row[6]) != expected["form_schema"]:
            raise MigrationAbort(f"process app {row[1]} has an invalid form schema")
        if json.loads(row[7]) != expected["flow_schema"]:
            raise MigrationAbort(f"process app {row[1]} has an invalid flow schema")
    if integrity != "ok":
        raise MigrationAbort(f"integrity_check={integrity}")
    if foreign_key_rows:
        raise MigrationAbort(f"foreign_key_check returned {len(foreign_key_rows)} rows")
    return len(apps), len(apps), integrity, "ok"


def rebuild(source: Path) -> tuple[Path, int, int, int, str, str]:
    source = source.resolve()
    request_count = preflight(source)
    backup = source.with_name(f"approval.backup-{datetime.now():%Y%m%d-%H%M%S}.db")
    temp = source.with_name(f".{source.stem}.migration-{uuid4().hex}.db")
    replaced = False

    try:
        shutil.copy2(source, backup)
        engine = create_engine(f"sqlite:///{temp.as_posix()}")
        SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        try:
            ApprovalBase.metadata.create_all(bind=engine)
            with SessionLocal() as session:
                try:
                    with session.begin():
                        seed_v2(session)
                except Exception:
                    session.rollback()
                    raise
        finally:
            engine.dispose()

        published_apps, current_v1_pointers, integrity, foreign_key_check = verify_v2_database(temp)
        os.replace(temp, source)
        replaced = True
        return (
            backup.resolve(),
            request_count,
            published_apps,
            current_v1_pointers,
            integrity,
            foreign_key_check,
        )
    except Exception:
        if replaced and backup.exists():
            shutil.copy2(backup, source)
        raise
    finally:
        if temp.exists():
            temp.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        type=Path,
        default=BACKEND_ROOT / "approval.db",
        help="SQLite database to rebuild; defaults to backend/approval.db",
    )
    args = parser.parse_args()
    try:
        backup, request_count, published_apps, pointers, integrity, foreign_key_check = rebuild(
            args.source
        )
    except MigrationAbort as error:
        print(f"Migration aborted: {error}", file=sys.stderr)
        return 1
    except Exception as error:
        print(f"Migration failed without completing source replacement: {error}", file=sys.stderr)
        return 1

    print(f"backup_path={backup}")
    print(f"approval_requests_count={request_count}")
    print(f"published_apps={published_apps}")
    print(f"current_v1_pointers={pointers}")
    print(f"integrity_check={integrity}")
    print(f"foreign_key_check={foreign_key_check}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
