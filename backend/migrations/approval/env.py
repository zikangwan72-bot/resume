from alembic import context

import app.main  # noqa: F401  (imports every router, so all models are registered)
from app.approval.database import ApprovalBase, approval_engine
from migrations.common import run

run(context, ApprovalBase.metadata, approval_engine, version_table="alembic_version_approval")
