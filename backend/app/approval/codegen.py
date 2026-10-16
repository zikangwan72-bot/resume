import secrets
import string
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.approval.models import ProcessApp

BUILTIN_PREFIXES = {
    "人事": "HR",
    "财务": "FIN",
    "采购": "PUR",
    "行政": "ADM",
    "通用": "GEN",
    "通用审批": "GEN",
}
ALPHABET = string.ascii_uppercase + string.digits


def generate_process_code(
    db: Session, category: str, now: datetime | None = None
) -> str:
    prefix = BUILTIN_PREFIXES.get(category.strip(), "CUS")
    date_part = (now or datetime.now(UTC)).strftime("%Y%m%d")
    for _ in range(64):
        suffix = "".join(secrets.choice(ALPHABET) for _ in range(4))
        code = f"{prefix}-{date_part}-{suffix}"
        if db.scalar(select(ProcessApp.id).where(ProcessApp.code == code)) is None:
            return code
    raise HTTPException(status_code=503, detail="流程编号生成失败，请重试")
