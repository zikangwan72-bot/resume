from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_current_user, require_permission
from app.business.asset_router import router as asset_router
from app.business.recruitment_router import router as recruitment_router
from app.db.database import get_db
from app.db.models import AIRun, AuditLog, Notification, User

router = APIRouter()

router.include_router(asset_router)
router.include_router(recruitment_router)

MODULES = [
    {
        "key": "resume-screening",
        "name": "AI简历筛选",
        "short_name": "人才筛选",
        "description": "从岗位要求到候选人评估的可解释AI辅助流程。",
        "planned_ai": ["简历解析", "语义匹配", "排序解释", "公平性评估"],
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
        "description": "建立资产台账与过程管理，逐步增加异常识别和处置建议。",
        "planned_ai": ["制度RAG", "异常解释", "处置建议", "资产Copilot"],
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


def user_payload(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "department": user.department,
        "role": user.role,
        "permissions": user.permissions,
    }


@router.get("/health")
def health() -> dict[str, Any]:
    return {
        "data": {
            "status": "healthy",
            "app": settings.app_name,
            "database": settings.database_mode,
            "supabase": "configured" if settings.supabase_configured else "not_configured",
            "ai": "configured" if settings.ai_configured else "not_configured",
            "timestamp": datetime.now(UTC).isoformat(),
        }
    }


@router.post("/auth/demo-login")
def demo_login(
    payload: DemoLoginRequest, request: Request, db: Session = Depends(get_db)
) -> dict[str, Any]:
    user = db.scalar(select(User).where(User.role == payload.role))
    if user is None:
        raise HTTPException(status_code=400, detail="Unknown demo role")
    db.add(
        AuditLog(
            actor_id=user.id,
            actor_name=user.display_name,
            action="demo_login",
            resource="authentication",
            request_id=getattr(request.state, "request_id", str(uuid4())),
            detail={"role": user.role},
        )
    )
    db.commit()
    return {"data": {"access_token": create_access_token(user), "user": user_payload(user)}}


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
            "stage": "Foundation only",
            "message": "公共架构已完成，详细业务将在后续迭代中实现。",
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


@router.post("/files/upload-url", status_code=status.HTTP_503_SERVICE_UNAVAILABLE)
def file_upload_placeholder(_: User = Depends(get_current_user)) -> None:
    raise HTTPException(
        status_code=503,
        detail="Supabase Storage is not configured. Add credentials before enabling uploads.",
    )
