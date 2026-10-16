"""Shared Alembic env logic for the main and approval migration environments.

On PostgreSQL both model groups live in one database, so each environment
must ignore the other group's tables (and its version table) instead of
proposing to drop them.
"""

from sqlalchemy import Engine, MetaData

VERSION_TABLES = {"alembic_version", "alembic_version_approval"}


def run(context, metadata: MetaData, engine: Engine, version_table: str) -> None:
    def include_object(obj, name, type_, reflected, compare_to):
        if type_ == "table" and (name in VERSION_TABLES or (reflected and compare_to is None)):
            return False
        return True

    options = dict(
        target_metadata=metadata,
        version_table=version_table,
        include_object=include_object,
        compare_type=True,
    )
    if context.is_offline_mode():
        context.configure(
            url=engine.url.render_as_string(hide_password=False),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    with engine.connect() as connection:
        context.configure(
            connection=connection,
            render_as_batch=connection.dialect.name == "sqlite",
            **options,
        )
        with context.begin_transaction():
            context.run_migrations()
