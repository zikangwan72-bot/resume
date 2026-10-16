from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.business.asset_router import router as asset_router
from app.business.recruitment_router import router as recruitment_router
from app.business.service_desk_router import router as service_desk_router
from app.core.config import settings
from app.core.security import (
    create_access_token,
    get_current_user,
    require_permission,
    verify_password,
)
from app.db.database import get_db
from app.db.models import AIRun, AuditLog, Notification, User
from app.db.seed import DEMO_PASSWORD, DEMO_USERS
from app.integrations.supabase import get_supabase_status
from app.integrations.storage import StorageUploadError, upload_bytes

router = APIRouter()

router.include_router(asset_router)
router.include_router(recruitment_router)
router.include_router(service_desk_router)

MODULES = [
    {
        "key": "resume-screening",
        "name": "招聘管理系统",
        "short_name": "人才筛选",
        "description": "管理岗位、候选人、AI初筛、面试推进和人才库。",
        "planned_ai": ["简历解析", "岗位匹配", "面试问题", "人工复核"],
        "permission": "resume:view",
        "accent": "cyan",
        "status": "foundation",
    },
    {
        "key": "approval-center",
        "name": "流程审批中心",
        "short_name": "智能审批",
        "description": "统一承载企业审批流程，并提供制度检索和意见辅助。",
        "planned_ai": ["制度RAG", "材料摘要", "风险提示", "审批Copilot"],
        "permission": "approval:view",
        "accent": "orange",
        "status": "foundation",
    },
    {
        "key": "asset-management",
        "name": "全资产管理",
        "short_name": "资产运营",
        "description": "管理资产台账、批量导入、二维码自助盘点和异常处置。",
        "planned_ai": ["台账管理", "批量导入", "扫码盘点", "异常处置"],
        "permission": "asset:view",
        "accent": "green",
        "status": "foundation",
    },
    {
        "key": "service-desk",
        "name": "企业IT服务台",
        "short_name": "服务台Agent",
        "description": "统一知识问答、工单受理、分类派发与人工接管。",
        "planned_ai": ["知识库RAG", "信息追问", "工单分类", "工具调用"],
        "permission": "service_desk:view",
        "accent": "blue",
        "status": "foundation",
    },
]


class DemoLoginRequest(BaseModel):
    role: str = "platform_admin"


class LoginRequest(BaseModel):
    email: str
    password: str


def require_demo_environment() -> None:
    if not settings.demo_auth_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")


def user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "department": user.department,
        "role": user.role,
        "permissions": user.permissions,
    }


def auth_payload(user: User) -> dict[str, Any]:
    return {"access_token": create_access_token(user), "user": user_payload(user)}


def write_login_audit(db: Session, request: Request, user: User, action: str) -> None:
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_name=user.display_name,
            action=action,
            resource="authentication",
            request_id=getattr(request.state, "request_id", str(uuid4())),
            detail={"role": user.role, "email": user.email},
        )
    )


@router.get("/health")
def health() -> dict[str, Any]:
    supabase = get_supabase_status()
    return {
        "data": {
            "status": "healthy",
            "app": settings.app_name,
            "database": settings.database_mode,
            "supabase": "configured" if supabase.configured else "not_configured",
            "supabase_details": {
                "database": supabase.database,
                "auth": supabase.auth,
                "storage": supabase.storage,
                "auth_mode": supabase.auth_mode,
                "storage_mode": supabase.storage_mode,
                "message": supabase.message,
            },
            "ai": "configured" if settings.ai_configured else "not_configured",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    }


@router.get("/auth/demo-accounts")
def demo_accounts() -> dict[str, Any]:
    require_demo_environment()
    return {
        "data": {
            "password": DEMO_PASSWORD,
            "accounts": [
                {
                    "email": item["email"],
                    "display_name": item["display_name"],
                    "department": item["department"],
                    "role": item["role"],
                }
                for item in DEMO_USERS
            ],
        }
    }


@router.post("/auth/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.email == payload.email.strip().lower()))
    if (
        user is None
        or not user.is_active
        or not verify_password(payload.password, user.password_hash)
    ):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    write_login_audit(db, request, user, "password_login")
    db.commit()
    return {"data": auth_payload(user)}


@router.post("/auth/demo-login")
def demo_login(
    payload: DemoLoginRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    require_demo_environment()
    role = payload.role
    user = db.scalar(select(User).where(User.role == role).order_by(User.created_at))
    if user is None:
        raise HTTPException(status_code=400, detail="Unknown demo role")
    write_login_audit(db, request, user, "demo_login")
    db.commit()
    return {"data": auth_payload(user)}


@router.get("/auth/me")
def me(user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"data": user_payload(user)}


@router.get("/modules")
def modules(user: User = Depends(get_current_user)) -> dict[str, Any]:
    allowed = [item for item in MODULES if item["permission"] in user.permissions]
    return {"data": allowed}


@router.get("/modules/{module_key}/summary")
def module_summary(module_key: str, user: User = Depends(get_current_user)) -> dict[str, Any]:
    module = next((item for item in MODULES if item["key"] == module_key), None)
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    if module["permission"] not in user.permissions:
        raise HTTPException(status_code=403, detail="Module permission denied")
    return {
        "data": {
            **module,
            "stage": "Available",
            "message": "模块已接入真实数据和可操作流程。",
        }
    }


@router.get("/notifications")
def notifications(
    user: User = Depends(require_permission("notification:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(desc(Notification.created_at))
    ).all()
    return {
        "data": [
            {
                "id": row.id,
                "title": row.title,
                "content": row.content,
                "category": row.category,
                "read_at": row.read_at,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.patch("/notifications/{notification_id}/read")
def mark_notification_read(
    notification_id: int,
    user: User = Depends(require_permission("notification:view")),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    row = db.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    row.read_at = datetime.now(UTC)
    db.commit()
    return {"data": {"id": row.id, "read_at": row.read_at}}


@router.get("/audit-logs")
def audit_logs(
    _: User = Depends(require_permission("audit:view")), db: Session = Depends(get_db)
) -> dict[str, Any]:
    rows = db.scalars(select(AuditLog).order_by(desc(AuditLog.created_at)).limit(100)).all()
    return {
        "data": [
            {
                "id": row.id,
                "actor_name": row.actor_name,
                "action": row.action,
                "resource": row.resource,
                "result": row.result,
                "request_id": row.request_id,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.get("/ai-runs")
def ai_runs(
    _: User = Depends(require_permission("ai_run:view")), db: Session = Depends(get_db)
) -> dict[str, Any]:
    rows = db.scalars(select(AIRun).order_by(desc(AIRun.created_at)).limit(100)).all()
    return {
        "data": [
            {
                "id": row.id,
                "module": row.module,
                "task_type": row.task_type,
                "model": row.model,
                "status": row.status,
                "latency_ms": row.latency_ms,
                "estimated_cost": row.estimated_cost,
                "human_review": row.human_review,
                "created_at": row.created_at,
            }
            for row in rows
        ]
    }


@router.post("/files/upload", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...), _: User = Depends(get_current_user)
) -> dict[str, Any]:
    content = await file.read()
    suffix = Path(file.filename or "upload").suffix.lower()
    relative_path = Path("uploads") / "files" / f"{uuid4()}{suffix}"
    content_type = file.content_type or "application/octet-stream"
    try:
        storage_path = upload_bytes(relative_path.as_posix(), content, content_type)
    except StorageUploadError as exc:
        if settings.app_env.lower() == "production":
            raise HTTPException(status_code=503, detail="云端文件存储不可用，请稍后重试") from exc
        storage_path = None
    if storage_path is None:
        target = Path(__file__).resolve().parents[3] / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        storage_path = str(relative_path)
    return {
        "data": {
            "filename": file.filename or "upload",
            "content_type": content_type,
            "size": len(content),
            "storage_path": storage_path,
        }
    }
