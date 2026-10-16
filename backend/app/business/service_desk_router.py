from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.business.models import Asset, ServiceTicket, ServiceTicketEvent
from app.business.schemas import (
    TicketAssign,
    TicketClose,
    TicketComment,
    TicketCreate,
    TicketReason,
    TicketResolve,
)
from app.core.pagination import (
    PageParams,
    page_params,
    page_response,
    paginate_list,
    paginate_select,
)
from app.core.security import require_permission
from app.db.database import get_db
from app.db.models import AuditLog, Notification, User

router = APIRouter(prefix="/service-desk", tags=["service-desk"])

VIEW = "service_desk:view"
HANDLE = "service_desk:handle"
MANAGE = "service_desk:manage"
# SLA 计时只覆盖 IT 侧在处理的状态；「待补充」等待提单人，不算超时。
OPEN_STATUSES = ("待受理", "处理中")
ACTIVE_STATUSES = ("待受理", "处理中", "待补充")
SLA_HOURS = {"紧急": 4, "高": 8, "中": 24, "低": 72}
SLA_WARNING_RATIO = 0.2
AUTO_CLOSE_AFTER = timedelta(hours=72)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def is_overdue(row: ServiceTicket, now: datetime | None = None) -> bool:
    return row.status in OPEN_STATUSES and as_utc(row.due_at) < (now or datetime.now(UTC))


def sla_state(row: ServiceTicket, now: datetime | None = None) -> str:
    if row.status not in OPEN_STATUSES:
        return "不计时"
    now = now or datetime.now(UTC)
    due_at = as_utc(row.due_at)
    if due_at < now:
        return "已超时"
    window = (due_at - as_utc(row.created_at)).total_seconds()
    if window > 0 and (due_at - now).total_seconds() < window * SLA_WARNING_RATIO:
        return "即将超时"
    return "正常"


def can_handle(user: User) -> bool:
    return HANDLE in user.permissions


def can_manage(user: User) -> bool:
    return MANAGE in user.permissions


def is_assignee(row: ServiceTicket, user: User) -> bool:
    return row.assignee_id == user.id


def available_actions(row: ServiceTicket, user: User) -> list[str]:
    requester = row.requester_id == user.id
    owner = is_assignee(row, user) or can_manage(user)
    actions: list[str] = []
    if row.status == "待受理":
        if can_handle(user):
            actions.append("claim")
        if can_manage(user):
            actions.append("assign")
    if row.status == "处理中" and owner:
        actions += ["transfer", "request_info", "resolve"]
    if row.status == "待补充" and requester:
        actions.append("reply")
    if row.status == "已解决" and requester:
        actions += ["close", "reopen"]
    if row.status in ACTIVE_STATUSES and requester:
        actions.append("cancel")
    if row.status in (*ACTIVE_STATUSES, "已解决") and (requester or owner or can_handle(user)):
        actions.append("comment")
    return actions


def ticket_payload(row: ServiceTicket, db: Session, user: User | None = None) -> dict:
    asset = db.get(Asset, row.asset_id) if row.asset_id else None
    payload = {
        "id": row.id,
        "ticket_no": row.ticket_no,
        "title": row.title,
        "description": row.description,
        "category": row.category,
        "priority": row.priority,
        "status": row.status,
        "requester_id": row.requester_id,
        "requester_name": row.requester_name,
        "department": row.department,
        "contact": row.contact,
        "assignee_id": row.assignee_id,
        "assignee_name": row.assignee_name,
        "asset_id": row.asset_id,
        "asset_code": asset.asset_code if asset else None,
        "asset_name": asset.name if asset else None,
        "resolution": row.resolution,
        "rating": row.rating,
        "due_at": as_utc(row.due_at),
        "overdue": is_overdue(row),
        "sla_state": sla_state(row),
        "resolved_at": as_utc(row.resolved_at),
        "auto_close_at": as_utc(row.resolved_at) + AUTO_CLOSE_AFTER if row.status == "已解决" and row.resolved_at else None,
        "closed_at": as_utc(row.closed_at),
        "created_at": as_utc(row.created_at),
        "updated_at": as_utc(row.updated_at),
    }
    if user is not None:
        payload["available_actions"] = available_actions(row, user)
    return payload


def event_payload(row: ServiceTicketEvent) -> dict:
    return {"id": row.id, "kind": row.kind, "actor_name": row.actor_name, "content": row.content, "created_at": as_utc(row.created_at)}


def can_view(row: ServiceTicket, user: User) -> bool:
    return row.requester_id == user.id or is_assignee(row, user) or can_handle(user)


def get_visible_ticket(ticket_id: int, user: User, db: Session) -> ServiceTicket:
    row = db.get(ServiceTicket, ticket_id)
    if row is None or not can_view(row, user):
        raise HTTPException(status_code=404, detail="工单不存在")
    return row


def require_requester(row: ServiceTicket, user: User) -> None:
    if row.requester_id != user.id:
        raise HTTPException(status_code=403, detail="只有提单人可以执行此操作")


def require_owner(row: ServiceTicket, user: User) -> None:
    if not (is_assignee(row, user) or can_manage(user)):
        raise HTTPException(status_code=403, detail="只有当前处理人或服务台主管可以执行此操作")


def require_status(row: ServiceTicket, *allowed: str) -> None:
    if row.status not in allowed:
        raise HTTPException(status_code=409, detail=f"工单当前为「{row.status}」，不能执行此操作")


def record_event(db: Session, request: Request | None, row: ServiceTicket, actor_id: str | None, actor_name: str, kind: str, content: str, action: str) -> None:
    db.add(ServiceTicketEvent(ticket_id=row.id, kind=kind, actor_id=actor_id, actor_name=actor_name, content=content))
    request_id = getattr(request.state, "request_id", None) if request else None
    db.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action=action, resource="service_ticket", request_id=request_id or str(uuid4()), detail={"ticket_no": row.ticket_no, "status": row.status}))


def record(db: Session, request: Request, row: ServiceTicket, user: User, kind: str, content: str, action: str) -> None:
    record_event(db, request, row, user.id, user.display_name, kind, content, action)


def notify(db: Session, user_id: str | None, actor_id: str | None, title: str, content: str) -> None:
    if user_id and user_id != actor_id:
        db.add(Notification(user_id=user_id, title=title, content=content, category="service_desk"))


def auto_close_resolved(db: Session) -> None:
    """已解决超过 72 小时无人反馈的工单在读取时顺带关闭，不依赖定时任务。"""
    cutoff = datetime.now(UTC) - AUTO_CLOSE_AFTER
    stale = [row for row in db.scalars(select(ServiceTicket).where(ServiceTicket.status == "已解决")).all() if row.resolved_at and as_utc(row.resolved_at) <= cutoff]
    for row in stale:
        row.status = "已关闭"
        row.closed_at = datetime.now(UTC)
        record_event(db, None, row, None, "System", "status", "已解决 72 小时内未反馈，系统自动关闭", "service_ticket_auto_closed")
        notify(db, row.requester_id, None, "工单已自动关闭", f"「{row.title}」解决后 72 小时未收到反馈，已自动关闭。")
    if stale:
        db.commit()


def handlers(db: Session) -> list[User]:
    return [item for item in db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.display_name)).all() if HANDLE in item.permissions]


def finish(db: Session, row: ServiceTicket, user: User) -> dict:
    db.commit()
    db.refresh(row)
    return {"data": ticket_payload(row, db, user)}


@router.get("/overview")
def service_desk_overview(user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    auto_close_resolved(db)
    query = select(ServiceTicket)
    if not can_handle(user):
        query = query.where(ServiceTicket.requester_id == user.id)
    rows = db.scalars(query).all()
    now = datetime.now(UTC)
    counts = {name: sum(1 for row in rows if row.status == name) for name in ["待受理", "处理中", "待补充", "已解决", "已关闭", "已取消"]}
    ratings = [row.rating for row in rows if row.rating]
    return {
        "data": {
            "can_handle": can_handle(user),
            "can_manage": can_manage(user),
            "total": len(rows),
            "status_counts": counts,
            "open_count": counts["待受理"] + counts["处理中"] + counts["待补充"],
            "overdue_count": sum(1 for row in rows if is_overdue(row, now)),
            "warning_count": sum(1 for row in rows if sla_state(row, now) == "即将超时"),
            "my_assigned_open": sum(1 for row in rows if row.assignee_id == user.id and row.status in ACTIVE_STATUSES),
            "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
        }
    }


@router.get("/agents")
def list_agents(_: User = Depends(require_permission(HANDLE)), db: Session = Depends(get_db)) -> dict:
    return {"data": [{"id": item.id, "display_name": item.display_name, "department": item.department} for item in handlers(db)]}


@router.get("/assets")
def list_linkable_assets(keyword: str = "", _: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    query = select(Asset).order_by(Asset.asset_code).limit(50)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.where(or_(Asset.asset_code.ilike(pattern), Asset.name.ilike(pattern), Asset.owner.ilike(pattern)))
    return {"data": [{"id": item.id, "asset_code": item.asset_code, "name": item.name, "owner": item.owner, "location": item.location} for item in db.scalars(query).all()]}


@router.get("/tickets")
def list_tickets(
    scope: str = Query("mine", pattern="^(mine|all|assigned|pool)$"),
    status_filter: str = Query("", alias="status"),
    keyword: str = "",
    paging: PageParams | None = Depends(page_params),
    user: User = Depends(require_permission(VIEW)),
    db: Session = Depends(get_db),
) -> dict:
    auto_close_resolved(db)
    query = select(ServiceTicket).order_by(ServiceTicket.created_at.desc(), ServiceTicket.id.desc())
    if scope != "mine" and not can_handle(user):
        raise HTTPException(status_code=403, detail=f"Missing permission: {HANDLE}")
    if scope == "mine":
        query = query.where(ServiceTicket.requester_id == user.id)
    elif scope == "assigned":
        query = query.where(ServiceTicket.assignee_id == user.id)
    elif scope == "pool":
        query = query.where(ServiceTicket.status == "待受理")
    if status_filter == "超时":
        query = query.where(ServiceTicket.status.in_(OPEN_STATUSES))
    elif status_filter:
        query = query.where(ServiceTicket.status == status_filter)
    if keyword.strip():
        pattern = f"%{keyword.strip()}%"
        query = query.where(or_(ServiceTicket.title.ilike(pattern), ServiceTicket.ticket_no.ilike(pattern), ServiceTicket.requester_name.ilike(pattern)))
    if status_filter == "超时":
        # Overdue is computed in Python, so filter first and page the result.
        rows, meta = paginate_list([row for row in db.scalars(query).all() if is_overdue(row)], paging)
    else:
        rows, meta = paginate_select(db, query, paging)
    return page_response([ticket_payload(row, db) for row in rows], meta)


@router.post("/tickets", status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, request: Request, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    if payload.asset_id is not None and db.get(Asset, payload.asset_id) is None:
        raise HTTPException(status_code=400, detail="关联的资产不存在")
    now = datetime.now(UTC)
    row = ServiceTicket(
        **payload.model_dump(),
        ticket_no=f"IT-{now:%Y%m%d}-{uuid4().hex[:6].upper()}",
        requester_id=user.id,
        requester_name=user.display_name,
        department=user.department,
        due_at=now + timedelta(hours=SLA_HOURS[payload.priority]),
        created_at=now,
    )
    db.add(row)
    db.flush()
    record(db, request, row, user, "status", f"提交工单（{payload.category} / {payload.priority}优先级）", "service_ticket_created")
    for agent in handlers(db):
        notify(db, agent.id, user.id, "新的IT服务工单", f"{user.display_name} 提交了「{row.title}」，请及时受理。")
    return finish(db, row, user)


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    auto_close_resolved(db)
    row = get_visible_ticket(ticket_id, user, db)
    events = db.scalars(select(ServiceTicketEvent).where(ServiceTicketEvent.ticket_id == row.id).order_by(ServiceTicketEvent.id)).all()
    return {"data": {**ticket_payload(row, db, user), "events": [event_payload(item) for item in events]}}


@router.post("/tickets/{ticket_id}/assign")
def assign_ticket(ticket_id: int, payload: TicketAssign, request: Request, user: User = Depends(require_permission(HANDLE)), db: Session = Depends(get_db)) -> dict:
    """接单（不传 assignee_id）、派单（主管指定他人）和转派（当前处理人换人）共用一个入口。"""
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, *OPEN_STATUSES)
    assignee = db.get(User, payload.assignee_id) if payload.assignee_id else user
    if assignee is None or not assignee.is_active or HANDLE not in assignee.permissions:
        raise HTTPException(status_code=400, detail="处理人不存在或没有服务台处理权限")
    previous_id, previous_name = row.assignee_id, row.assignee_name
    if previous_id:
        require_owner(row, user)
    elif assignee.id != user.id and not can_manage(user):
        raise HTTPException(status_code=403, detail="只有服务台主管可以把工单派给他人")
    if previous_id == assignee.id:
        raise HTTPException(status_code=409, detail="工单已经由该处理人负责")
    row.status = "处理中"
    row.assignee_id = assignee.id
    row.assignee_name = assignee.display_name
    if previous_id:
        reason = f"，原因：{payload.reason}" if payload.reason else ""
        content, action = f"由 {previous_name} 转派给 {assignee.display_name}{reason}", "service_ticket_transferred"
    elif assignee.id == user.id:
        content, action = f"{assignee.display_name} 已受理", "service_ticket_assigned"
    else:
        content, action = f"派单给 {assignee.display_name}", "service_ticket_assigned"
    record(db, request, row, user, "status", content, action)
    notify(db, row.requester_id, user.id, "工单已受理", f"「{row.title}」由 {assignee.display_name} 处理中。")
    notify(db, assignee.id, user.id, "工单已派给你", f"请处理「{row.title}」（{row.ticket_no}）。")
    if previous_id:
        notify(db, previous_id, user.id, "工单已转出", f"「{row.title}」已转给 {assignee.display_name}。")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/request-info")
def request_info(ticket_id: int, payload: TicketComment, request: Request, user: User = Depends(require_permission(HANDLE)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, "处理中")
    require_owner(row, user)
    row.status = "待补充"
    record(db, request, row, user, "status", f"请求补充信息：{payload.content}", "service_ticket_info_requested")
    notify(db, row.requester_id, user.id, "工单需要你补充信息", f"「{row.title}」：{payload.content}")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/reply")
def reply_info(ticket_id: int, payload: TicketComment, request: Request, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, "待补充")
    row.status = "处理中"
    record(db, request, row, user, "status", f"补充信息：{payload.content}", "service_ticket_info_replied")
    notify(db, row.assignee_id, user.id, "提单人已补充信息", f"「{row.title}」：{payload.content}")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/resolve")
def resolve_ticket(ticket_id: int, payload: TicketResolve, request: Request, user: User = Depends(require_permission(HANDLE)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, "处理中")
    require_owner(row, user)
    row.status = "已解决"
    row.resolution = payload.resolution
    row.resolved_at = datetime.now(UTC)
    record(db, request, row, user, "status", f"标记已解决：{payload.resolution}", "service_ticket_resolved")
    notify(db, row.requester_id, user.id, "工单已解决，请确认", f"「{row.title}」已处理完成，请确认关闭或重新打开；72 小时内未反馈将自动关闭。")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/close")
def close_ticket(ticket_id: int, payload: TicketClose, request: Request, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, "已解决")
    row.status = "已关闭"
    row.rating = payload.rating
    row.closed_at = datetime.now(UTC)
    detail = f"确认解决并关闭{f'，评分 {payload.rating} 星' if payload.rating else ''}{f'：{payload.comment}' if payload.comment else ''}"
    record(db, request, row, user, "status", detail, "service_ticket_closed")
    notify(db, row.assignee_id, user.id, "工单已关闭", f"「{row.title}」已由提单人确认关闭。")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/reopen")
def reopen_ticket(ticket_id: int, payload: TicketReason, request: Request, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, "已解决")
    row.status = "处理中"
    row.resolved_at = None
    record(db, request, row, user, "status", f"重新打开：{payload.reason}", "service_ticket_reopened")
    notify(db, row.assignee_id, user.id, "工单被重新打开", f"「{row.title}」问题未解决：{payload.reason}")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/cancel")
def cancel_ticket(ticket_id: int, payload: TicketReason, request: Request, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_requester(row, user)
    require_status(row, *ACTIVE_STATUSES)
    row.status = "已取消"
    row.closed_at = datetime.now(UTC)
    record(db, request, row, user, "status", f"撤回工单：{payload.reason}", "service_ticket_cancelled")
    notify(db, row.assignee_id, user.id, "工单已撤回", f"「{row.title}」已被提单人撤回。")
    return finish(db, row, user)


@router.post("/tickets/{ticket_id}/comments", status_code=status.HTTP_201_CREATED)
def comment_ticket(ticket_id: int, payload: TicketComment, request: Request, user: User = Depends(require_permission(VIEW)), db: Session = Depends(get_db)) -> dict:
    row = get_visible_ticket(ticket_id, user, db)
    require_status(row, *ACTIVE_STATUSES, "已解决")
    record(db, request, row, user, "comment", payload.content, "service_ticket_commented")
    if user.id == row.requester_id:
        notify(db, row.assignee_id, user.id, "工单有新回复", f"{user.display_name} 在「{row.title}」中留言。")
    else:
        notify(db, row.requester_id, user.id, "工单有新回复", f"{user.display_name} 在「{row.title}」中回复了你。")
    return finish(db, row, user)
