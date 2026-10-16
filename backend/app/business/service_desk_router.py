from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.business.models import ServiceTicket, ServiceTicketEvent
from app.business.schemas import (
    TicketAssign,
    TicketClose,
    TicketComment,
    TicketCreate,
    TicketReason,
    TicketResolve,
)
from app.core.security import require_permission
from app.db.database import get_db
from app.db.models import AuditLog, Notification, User

router = APIRouter(prefix="/service-desk", tags=["service-desk"])

MANAGE = "service_desk:manage"
OPEN_STATUSES = ("待受理", "处理中")
SLA_HOURS = {"紧急": 4, "高": 8, "中": 24, "低": 72}


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_overdue(row: ServiceTicket, now: datetime | None = None) -> bool:
    return row.status in OPEN_STATUSES and as_utc(row.due_at) < (now or datetime.now(UTC))


def ticket_payload(row: ServiceTicket) -> dict:
    return {"id": row.id, "ticket_no": row.ticket_no, "title": row.title, "description": row.description, "category": row.category, "priority": row.priority, "status": row.status, "requester_id": row.requester_id, "requester_name": row.requester_name, "department": row.department, "contact": row.contact, "assignee_id": row.assignee_id, "assignee_name": row.assignee_name, "resolution": row.resolution, "rating": row.rating, "due_at": as_utc(row.due_at), "overdue": is_overdue(row), "resolved_at": as_utc(row.resolved_at), "closed_at": as_utc(row.closed_at), "created_at": as_utc(row.created_at), "updated_at": as_utc(row.updated_at)}


def event_payload(row: ServiceTicketEvent) -> dict:
    return {"id": row.id, "kind": row.kind, "actor_name": row.actor_name, "content": row.content, "created_at": as_utc(row.created_at)}


def can_manage(user: User) -> bool:
    return MANAGE in user.permissions


def get_visible_ticket(ticket_id: int, user: User, db: Session) -> ServiceTicket:
    row = db.get(ServiceTicket, ticket_id)
    if row is None or (row.requester_id != user.id and not can_manage(user)):
        raise HTTPException(status_code=404, detail="工单不存在")
    return row


def require_requester(row: ServiceTicket, user: User) -> None:
    if row.requester_id != user.id:
        raise HTTPException(status_code=403, detail="只有提单人可以执行此操作")


def require_status(row: ServiceTicket, *allowed: str) -> None:
    if row.status not in allowed:
        raise HTTPException(status_code=409, detail=f"工单当前为「{row.status}」，不能执行此操作")


def record_event(db: Session, request: Request, row: ServiceTicket, user: User, kind: str, content: str, action: str) -> None:
    db.add(ServiceTicketEvent(ticket_id=row.id, kind=kind, actor_id=user.id, actor_name=user.display_name, content=content))
    db.add(AuditLog(actor_id=user.id, actor_name=user.display_name, action=action, resource="service_ticket", request_id=getattr(request.state, "request_id", str(uuid4())), detail={"ticket_no": row.ticket_no, "status": row.status}))


def notify(db: Session, user_id: str | None, actor: User, title: str, content: str) -> None:
    if user_id and user_id != actor.id:
        db.add(Notification(user_id=user_id, title=title, content=content, category="service_desk"))


def finish(db: Session, row: ServiceTicket) -> dict:
    db.commit()
    db.refresh(row)
    return {"data": ticket_payload(row)}


@router.get("/overview")
def service_desk_overview(user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    query = select(ServiceTicket)
    if not can_manage(user):
        query = query.where(ServiceTicket.requester_id == user.id)
    rows = db.scalars(query).all()
    now = datetime.now(UTC)
    counts = {name: sum(1 for row in rows if row.status == name) for name in ["待受理", "处理中", "已解决", "已关闭", "已取消"]}
    ratings = [row.rating for row in rows if row.rating]
    return {
        "data": {
            "can_manage": can_manage(user),
            "total": len(rows),
            "status_counts": counts,
            "open_count": counts["待受理"] + counts["处理中"],
            "overdue_count": sum(1 for row in rows if is_overdue(row, now)),
            "my_assigned_open": sum(1 for row in rows if row.assignee_id == user.id and row.status in OPEN_STATUSES),
            "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        }
    }


@router.get("/agents")
def list_agents(_: User = Depends(require_permission(MANAGE)), db: Session = Depends(get_db)) -> dict:
    users = db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)).all()
    return {"data": [{"id": item.id, "display_name": item.display_name, "department": item.department} for item in users if MANAGE in item.permissions]}


@router.get("/tickets")
def list_tickets(
    scope: str = Query("mine", pattern="^(mine|all|assigned)$"),
    status_filter: str = Query("", alias="status"),
    keyword: str = "",
    user: User = Depends(require_permission("service_desk:view")),
    db: Session = Depends(get_db),
) -> dict:
    query = select(ServiceTicket).order_by(ServiceTicket.created_at.desc(), ServiceTicket.id.desc())
    if scope != "mine" and not can_manage(user):
        raise HTTPException(status_code=403, detail=f"Missing permission: {MANAGE}")
    if scope == "mine":
        query = query.where(ServiceTicket.requester_id == user.id)
    elif scope == "assigned":
        query = query.where(ServiceTicket.assignee_id == user.id)
    if status_filter == "超时":
        query = query.where(ServiceTicket.status.in_(OPEN_STATUSES))
    elif status_filter:
        query = query.where(ServiceTicket.status == status_filter)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.where(or_(ServiceTicket.title.ilike(pattern), ServiceTicket.ticket_no.ilike(pattern), ServiceTicket.requester_name.ilike(pattern)))
    rows = db.scalars(query).all()
    if status_filter == "超时":
        rows = [row for row in rows if is_overdue(row)]
    return {"data": [ticket_payload(row) for row in rows]}


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, request: Request, user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    now = datetime.now(UTC)
    row = ServiceTicket(
        **payload.model_dump(),
        ticket_no=f"IT-{now:%Y%m%d}-{uuid4().hex[:6].upper()}",
        requester_id=user.id,
        requester_name=user.display_name,
        department=user.department,
        due_at=now + timedelta(hours=SLA_HOURS[payload.priority]),
    )
    db.add(row)
    db.flush()
    record_event(db, request, row, user, "status", f"提交工单（{payload.category} / {payload.priority}优先级）", "service_ticket_created")
    for agent in db.scalars(select(User).where(User.is_active.is_(True))).all():
        if MANAGE in agent.permissions:
            notify(db, agent.id, user, "新的IT服务工单", f"{user.display_name} 提交了「{row.title}」，请及时受理。")
    return finish(db, row)


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    events = db.scalars(select(ServiceTicketEvent).where(ServiceTicketEvent.ticket_id == row.id).order_by(ServiceTicketEvent.id)).all()
    return {"data": {**ticket_payload(row), "events": [event_payload(item) for item in events]}}


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, payload: TicketAssign, request: Request, user: User = Depends(require_permission(MANAGE)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, *OPEN_STATUSES)
    assignee = db.get(User, payload.assignee_id) if payload.assignee_id else user
    if assignee is None or not assignee.is_active or MANAGE not in assignee.permissions:
        raise HTTPException(status_code=400, detail="处理人不存在或没有服务台处理权限")
    previous = row.assignee_name
    row.status = "处理中"
    row.assignee_id = assignee.id
    row.assignee_name = assignee.display_name
    content = f"转派给 {assignee.display_name}" if previous and previous != assignee.display_name else f"{assignee.display_name} 已受理"
    record_event(db, request, row, user, "status", content, "service_ticket_assigned")
    notify(db, row.requester_id, user, "工单已受理", f"「{row.title}」由 {assignee.display_name} 处理中。")
    notify(db, assignee.id, user, "工单已派给你", f"请处理「{row.title}」（{row.ticket_no}）。")
    return finish(db, row)


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, payload: TicketResolve, request: Request, user: User = Depends(require_permission(MANAGE)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, "处理中")
    row.status = "已解决"
    row.resolution = payload.resolution
    row.resolved_at = datetime.now(UTC)
    record_event(db, request, row, user, "status", f"标记已解决：{payload.resolution}", "service_ticket_resolved")
    notify(db, row.requester_id, user, "工单已解决，请确认", f"「{row.title}」已处理完成，请确认关闭或重新打开。")
    return finish(db, row)


@router.post("/tickets/{ticket_id}/close")
def close_ticket(ticket_id: int, payload: TicketClose, request: Request, user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, "已解决")
    row.status = "已关闭"
    row.rating = payload.rating
    row.closed_at = datetime.now(UTC)
    detail = f"确认解决并关闭{f'，评分 {payload.rating} 星' if payload.rating else ''}{f'：{payload.comment}' if payload.comment else ''}"
    record_event(db, request, row, user, "status", detail, "service_ticket_closed")
    notify(db, row.assignee_id, user, "工单已关闭", f"「{row.title}」已由提单人确认关闭。")
    return finish(db, row)


@router.post("/tickets/{ticket_id}/reopen")
def reopen_ticket(ticket_id: int, payload: TicketReason, request: Request, user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, "已解决")
    row.status = "处理中"
    row.resolved_at = None
    record_event(db, request, row, user, "status", f"重新打开：{payload.reason}", "service_ticket_reopened")
    notify(db, row.assignee_id, user, "工单被重新打开", f"「{row.title}」问题未解决：{payload.reason}")
    return finish(db, row)


@router.post("/tickets/{ticket_id}/cancel")
def cancel_ticket(ticket_id: int, payload: TicketReason, request: Request, user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, *OPEN_STATUSES)
    row.status = "已取消"
    row.closed_at = datetime.now(UTC)
    record_event(db, request, row, user, "status", f"撤回工单：{payload.reason}", "service_ticket_cancelled")
    notify(db, row.assignee_id, user, "工单已撤回", f"「{row.title}」已被提单人撤回。")
    return finish(db, row)


@router.post("/tickets/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
def comment_ticket(ticket_id: int, payload: TicketComment, request: Request, user: User = Depends(require_permission("service_desk:view")), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, "待受理", "处理中", "已解决")
    record_event(db, request, row, user, "comment", payload.content, "service_ticket_commented")
    if user.id == row.requester_id:
        notify(db, row.assignee_id, user, "工单有新回复", f"{user.display_name} 在「{row.title}」中留言。")
    else:
        notify(db, row.requester_id, user, "工单有新回复", f"{user.display_name} 在「{row.title}」中回复了你。")
    return finish(db, row)
