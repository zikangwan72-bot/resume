import sqlite3
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "migrate_approval_v2.py"
LEGACY_TABLES = (
    "approval_users",
    "form_templates",
    "flow_templates",
    "approval_types",
    "approval_requests",
    "approval_nodes",
    "approval_actions",
)


def create_legacy_database(
    path: Path,
    request_count: int = 0,
    node_count: int = 0,
    action_count: int = 0,
) -> None:
    connection = sqlite3.connect(path)
    try:
        for table in LEGACY_TABLES:
            connection.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)")
        connection.executemany(
            "INSERT INTO approval_requests (id) VALUES (?)",
            [(index,) for index in range(1, request_count + 1)],
        )
        connection.executemany(
            "INSERT INTO approval_nodes (id) VALUES (?)",
            [(index,) for index in range(1, node_count + 1)],
        )
        connection.executemany(
            "INSERT INTO approval_actions (id) VALUES (?)",
            [(index,) for index in range(1, action_count + 1)],
        )
        connection.commit()
    finally:
        connection.close()


def run_migration(source: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(source)],
        check=False,
        capture_output=True,
        text=True,
    )


def test_migration_rebuilds_an_empty_legacy_copy_with_published_v1_apps(tmp_path: Path):
    source = tmp_path / "approval.db"
    create_legacy_database(source)

    result = run_migration(source)

    assert result.returncode == 0, result.stderr
    assert "integrity_check=ok" in result.stdout
    assert "foreign_key_check=ok" in result.stdout
    assert "published_apps=3" in result.stdout
    assert "backup_path=" in result.stdout
    backups = list(tmp_path.glob("approval.backup-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(source) as connection:
        apps = connection.execute(
            "SELECT code, current_version_id, status FROM process_apps ORDER BY code"
        ).fetchall()
        versions = connection.execute(
            "SELECT version_number, status, form_schema, flow_schema "
            "FROM process_versions ORDER BY process_app_id"
        ).fetchall()
        assert apps and [row[0] for row in apps] == ["expense", "leave", "purchase"]
        assert all(row[1] and row[2] == "published" for row in apps)
        assert [(row[0], row[1]) for row in versions] == [(1, "published")] * 3
        assert all('"fields"' in row[2] and '"nodes"' in row[3] for row in versions)


def test_migration_aborts_without_mutating_a_source_that_has_requests(tmp_path: Path):
    source = tmp_path / "approval.db"
    create_legacy_database(source, request_count=1)
    before = source.read_bytes()

    result = run_migration(source)

    assert result.returncode != 0
    assert "approval_requests_count=1" in result.stderr
    assert source.read_bytes() == before
    assert not list(tmp_path.glob("approval.backup-*.db"))


def test_migration_aborts_when_orphan_runtime_records_exist(tmp_path: Path):
    source = tmp_path / "approval.db"
    create_legacy_database(source, node_count=1, action_count=1)
    before = source.read_bytes()

    result = run_migration(source)

    assert result.returncode != 0
    assert "approval_nodes_count=1" in result.stderr
    assert "approval_actions_count=1" in result.stderr
    assert source.read_bytes() == before
    assert not list(tmp_path.glob("approval.backup-*.db"))


def test_migration_cannot_run_twice(tmp_path: Path):
    source = tmp_path / "approval.db"
    create_legacy_database(source)
    assert run_migration(source).returncode == 0
    before = source.read_bytes()
    existing_backups = list(tmp_path.glob("approval.backup-*.db"))

    result = run_migration(source)

    assert result.returncode != 0
    assert "already uses the approval v2 schema" in result.stderr
    assert source.read_bytes() == before
    assert list(tmp_path.glob("approval.backup-*.db")) == existing_backups
