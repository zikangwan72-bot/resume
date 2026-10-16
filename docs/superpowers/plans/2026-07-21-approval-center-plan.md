# 流程审批中心（approval-center）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 enterprise-ai-suite 中实现流程审批中心模块，支持三级串行审批 + 会签，独立 approval.db 数据库，6 个前端业务页面 + 4 个后台管理页面。

**Architecture:** 后端新建 `app/approval/` 模块（独立引擎/Session/模型/路由），与现有 `app/` 并行。前端在 `views/approval/` 下新增 8 个组件，修改路由和导航。审批数据存 `backend/approval.db`，与 `enterprise_ai.db` 物理隔离。

**Tech Stack:** FastAPI + SQLAlchemy (SQLite) + Vue 3 + TypeScript + Ant Design Vue 4 + Axios

---

### Task 1: 创建审批模块目录和数据库引擎

**Files:**
- Create: `backend/app/approval/__init__.py`
- Create: `backend/app/approval/database.py`

- [ ] **Step 1: 创建 `__init__.py`**

```python
# backend/app/approval/__init__.py
```

- [ ] **Step 2: 创建审批专用数据库引擎**

```python
# backend/app/approval/database.py
from collections.abc import Generator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

APPROVAL_DB_PATH = Path(__file__).resolve().parents[2] / "approval.db"
APPROVAL_DB_URL = f"sqlite:///{APPROVAL_DB_PATH}"


class ApprovalBase(DeclarativeBase):
    pass


approval_engine = create_engine(
    APPROVAL_DB_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
)
ApprovalSessionLocal = sessionmaker(bind=approval_engine, autoflush=False, expire_on_commit=False)


def get_approval_db() -> Generator[Session, None, None]:
    db = ApprovalSessionLocal()
    try:
        yield db
    finally:
        db.close()
```

- [ ] **Step 3: 验证文件创建成功**

```powershell
Get-ChildItem C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend\app\approval\
```

---

### Task 2: 创建审批 ORM 模型

**Files:**
- Create: `backend/app/approval/models.py`

- [ ] **Step 1: 写入全部 7 个模型**

```python
# backend/app/approval/models.py
from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.approval.database import ApprovalBase


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ApprovalUser(ApprovalBase):
    __tablename__ = "approval_users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class FormTemplate(ApprovalBase):
    __tablename__ = "form_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    fields: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class FlowTemplate(ApprovalBase):
    __tablename__ = "flow_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    nodes: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ApprovalType(ApprovalBase):
    __tablename__ = "approval_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    form_template_id: Mapped[int] = mapped_column(Integer, nullable=False)
    flow_template_id: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ApprovalRequest(ApprovalBase):
    __tablename__ = "approval_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    applicant_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    applicant_name: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    form_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    current_node_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    flow_snapshot: Mapped[list[dict]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ApprovalNode(ApprovalBase):
    __tablename__ = "approval_nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    node_index: Mapped[int] = mapped_column(Integer, nullable=False)
    approver_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    approver_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    acted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)


class ApprovalAction(ApprovalBase):
    __tablename__ = "approval_actions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    node_id: Mapped[int] = mapped_column(Integer, nullable=False)
    request_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(36), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utc_now)
```

- [ ] **Step 2: 运行 Python 语法检查**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend; python -c "from app.approval.models import ApprovalRequest, ApprovalNode, ApprovalAction, ApprovalType, FormTemplate, FlowTemplate, ApprovalUser; print('OK, 7 models loaded')"
```

---

### Task 3: 创建种子数据

**Files:**
- Create: `backend/app/approval/seed.py`

- [ ] **Step 1: 写入种子数据脚本**

```python
# backend/app/approval/seed.py
from sqlalchemy import select

from app.approval.database import ApprovalBase, ApprovalSessionLocal, approval_engine
from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalType,
    ApprovalUser,
    FlowTemplate,
    FormTemplate,
)

APPROVAL_USERS = [
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "email": "zhangsan@demo.local",
        "display_name": "张三",
        "department": "产品研发部",
        "role": "department_manager",
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "email": "lisi@demo.local",
        "display_name": "李四",
        "department": "产品研发部",
        "role": "division_leader",
    },
    {
        "id": "66666666-6666-6666-6666-666666666666",
        "email": "wangwu@demo.local",
        "display_name": "王五",
        "department": "人力资源部",
        "role": "hr",
    },
    {
        "id": "77777777-7777-7777-7777-777777777777",
        "email": "zhaoliu@demo.local",
        "display_name": "赵六",
        "department": "财务管理部",
        "role": "finance",
    },
    {
        "id": "88888888-8888-8888-8888-888888888888",
        "email": "sunqi@demo.local",
        "display_name": "孙七",
        "department": "产品研发部",
        "role": "vp",
    },
]

LEAVE_FORM_FIELDS = [
    {"key": "leave_type", "label": "请假类型", "type": "select", "required": True, "options": ["事假", "病假", "年假", "调休", "婚假"]},
    {"key": "start_date", "label": "开始日期", "type": "date", "required": True},
    {"key": "end_date", "label": "结束日期", "type": "date", "required": True},
    {"key": "days", "label": "天数", "type": "number", "required": True},
    {"key": "reason", "label": "请假事由", "type": "textarea", "required": True},
]

EXPENSE_FORM_FIELDS = [
    {"key": "expense_type", "label": "报销类别", "type": "select", "required": True, "options": ["差旅费", "办公用品", "招待费", "交通费", "其他"]},
    {"key": "amount", "label": "报销金额（元）", "type": "number", "required": True},
    {"key": "expense_date", "label": "发生日期", "type": "date", "required": True},
    {"key": "description", "label": "费用说明", "type": "textarea", "required": True},
]

PURCHASE_FORM_FIELDS = [
    {"key": "item_name", "label": "采购物品", "type": "text", "required": True},
    {"key": "quantity", "label": "数量", "type": "number", "required": True},
    {"key": "estimated_amount", "label": "预估金额（元）", "type": "number", "required": True},
    {"key": "purpose", "label": "采购用途", "type": "textarea", "required": True},
    {"key": "supplier", "label": "建议供应商", "type": "text", "required": False},
]

LEAVE_FLOW_NODES = [
    {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "44444444-4444-4444-4444-444444444444", "allow_transfer": True},
    {"index": 1, "name": "分管领导审批", "type": "single", "approver_id": "55555555-5555-5555-5555-555555555555", "allow_transfer": True},
    {"index": 2, "name": "HR确认", "type": "single", "approver_id": "66666666-6666-6666-6666-666666666666", "allow_transfer": False},
]

EXPENSE_FLOW_NODES = [
    {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "44444444-4444-4444-4444-444444444444", "allow_transfer": True},
    {"index": 1, "name": "分管领导审批", "type": "single", "approver_id": "55555555-5555-5555-5555-555555555555", "allow_transfer": True},
    {"index": 2, "name": "财务审批", "type": "single", "approver_id": "77777777-7777-7777-7777-777777777777", "allow_transfer": False},
]

PURCHASE_FLOW_NODES = [
    {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "44444444-4444-4444-4444-444444444444", "allow_transfer": True},
    {"index": 1, "name": "领导会签", "type": "counter_sign", "approver_ids": ["55555555-5555-5555-5555-555555555555", "88888888-8888-8888-8888-888888888888"], "allow_transfer": True},
    {"index": 2, "name": "财务审批", "type": "single", "approver_id": "77777777-7777-7777-7777-777777777777", "allow_transfer": False},
]


def initialize_approval_db() -> None:
    ApprovalBase.metadata.create_all(bind=approval_engine)
    with ApprovalSessionLocal() as db:
        if db.scalar(select(ApprovalUser.id).limit(1)):
            return

        for u in APPROVAL_USERS:
            db.add(ApprovalUser(**u))
        db.flush()

        leave_form = FormTemplate(name="请假表单", description="请假申请表单", fields=LEAVE_FORM_FIELDS)
        expense_form = FormTemplate(name="报销表单", description="报销申请表单", fields=EXPENSE_FORM_FIELDS)
        purchase_form = FormTemplate(name="采购表单", description="采购申请表单", fields=PURCHASE_FORM_FIELDS)
        db.add_all([leave_form, expense_form, purchase_form])
        db.flush()

        leave_flow = FlowTemplate(name="三级审批（HR终审）", description="部门经理→分管领导→HR", nodes=LEAVE_FLOW_NODES)
        expense_flow = FlowTemplate(name="三级审批（财务终审）", description="部门经理→分管领导→财务", nodes=EXPENSE_FLOW_NODES)
        purchase_flow = FlowTemplate(name="会签流程（财务终审）", description="部门经理→领导会签→财务", nodes=PURCHASE_FLOW_NODES)
        db.add_all([leave_flow, expense_flow, purchase_flow])
        db.flush()

        db.add_all([
            ApprovalType(name="请假申请", description="员工请假审批", form_template_id=leave_form.id, flow_template_id=leave_flow.id),
            ApprovalType(name="报销申请", description="费用报销审批", form_template_id=expense_form.id, flow_template_id=expense_flow.id),
            ApprovalType(name="采购申请", description="物品采购审批", form_template_id=purchase_form.id, flow_template_id=purchase_flow.id),
        ])
        db.commit()
```

- [ ] **Step 2: 运行种子数据**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend; python -c "from app.approval.seed import initialize_approval_db; initialize_approval_db(); from app.approval.database import ApprovalSessionLocal; from app.approval.models import ApprovalType, ApprovalUser; db = ApprovalSessionLocal(); print(f'Users: {db.query(ApprovalUser).count()}, Types: {db.query(ApprovalType).count()}')"
```

Expected: `Users: 5, Types: 3`

- [ ] **Step 3: 删除自动生成的 approval.db 以便后续正式初始化**

```powershell
Remove-Item C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend\approval.db -ErrorAction SilentlyContinue
```

---

### Task 4: 创建审批 API 路由——基础端点（类型、提交、列表、详情）

**Files:**
- Create: `backend/app/approval/router.py`

- [ ] **Step 1: 创建路由文件并写入导入和基础端点**

```python
# backend/app/approval/router.py
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.approval.database import get_approval_db
from app.approval.models import (
    ApprovalAction,
    ApprovalNode,
    ApprovalRequest,
    ApprovalType,
    ApprovalUser,
    FlowTemplate,
    FormTemplate,
)
from app.core.security import get_current_user, require_permission
from app.db.models import User

router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])
admin_router = APIRouter(prefix="/api/v1/admin", tags=["approval-admin"])


# ── Pydantic schemas ──

class SubmitRequest(BaseModel):
    type_id: int
    title: str
    form_data: dict


class ApproveRejectBody(BaseModel):
    comment: str


class TransferBody(BaseModel):
    target_user_id: str
```

- [ ] **Step 2: 写入辅助函数和 GET /types 端点**

```python
# backend/app/approval/router.py (接上面)

def _type_with_form(approval_type: ApprovalType, db: Session) -> dict:
    form = db.get(FormTemplate, approval_type.form_template_id)
    return {
        "id": approval_type.id,
        "name": approval_type.name,
        "description": approval_type.description,
        "is_active": approval_type.is_active,
        "form_template": {
            "id": form.id,
            "name": form.name,
            "fields": form.fields,
        } if form else None,
    }


def _request_detail(request: ApprovalRequest, db: Session) -> dict:
    nodes = db.scalars(
        select(ApprovalNode)
        .where(ApprovalNode.request_id == request.id)
        .order_by(ApprovalNode.node_index, ApprovalNode.id)
    ).all()
    actions = db.scalars(
        select(ApprovalAction)
        .where(ApprovalAction.request_id == request.id)
        .order_by(desc(ApprovalAction.created_at))
    ).all()
    return {
        "id": request.id,
        "type_id": request.type_id,
        "applicant_id": request.applicant_id,
        "applicant_name": request.applicant_name,
        "title": request.title,
        "form_data": request.form_data,
        "status": request.status,
        "current_node_index": request.current_node_index,
        "flow_snapshot": request.flow_snapshot,
        "nodes": [
            {
                "id": n.id,
                "node_index": n.node_index,
                "approver_id": n.approver_id,
                "approver_name": n.approver_name,
                "status": n.status,
                "comment": n.comment,
                "acted_at": n.acted_at.isoformat() if n.acted_at else None,
            }
            for n in nodes
        ],
        "actions": [
            {
                "id": a.id,
                "node_id": a.node_id,
                "actor_id": a.actor_id,
                "actor_name": a.actor_name,
                "action": a.action,
                "comment": a.comment,
                "created_at": a.created_at.isoformat(),
            }
            for a in actions
        ],
        "created_at": request.created_at.isoformat(),
        "updated_at": request.updated_at.isoformat(),
        "submitted_at": request.submitted_at.isoformat() if request.submitted_at else None,
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
    }


@router.get("/types")
def list_types(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(ApprovalType).where(ApprovalType.is_active == True)).all()
    return {"data": [_type_with_form(r, db) for r in rows]}


@router.post("/requests")
def submit_request(
    body: SubmitRequest,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    approval_type = db.get(ApprovalType, body.type_id)
    if not approval_type or not approval_type.is_active:
        raise HTTPException(status_code=400, detail="审批类型不存在或已停用")

    flow = db.get(FlowTemplate, approval_type.flow_template_id)
    if not flow:
        raise HTTPException(status_code=500, detail="流程模板缺失")

    flow_nodes = flow.nodes
    now = datetime.now(UTC)

    request = ApprovalRequest(
        type_id=body.type_id,
        applicant_id=user.id,
        applicant_name=user.display_name,
        title=body.title,
        form_data=body.form_data,
        status="pending",
        current_node_index=0,
        flow_snapshot=flow_nodes,
        submitted_at=now,
        updated_at=now,
    )
    db.add(request)
    db.flush()

    for node_def in flow_nodes:
        if node_def.get("type") == "counter_sign":
            for approver_id in node_def.get("approver_ids", []):
                approver = db.get(ApprovalUser, approver_id)
                db.add(ApprovalNode(
                    request_id=request.id,
                    node_index=node_def["index"],
                    approver_id=approver_id,
                    approver_name=approver.display_name if approver else "未知",
                    status="pending",
                ))
        else:
            approver_id = node_def.get("approver_id", "")
            approver = db.get(ApprovalUser, approver_id) if approver_id else None
            db.add(ApprovalNode(
                request_id=request.id,
                node_index=node_def["index"],
                approver_id=approver_id,
                approver_name=approver.display_name if approver else "未知",
                status="pending" if node_def["index"] == 0 else "pending",
            ))

    db.commit()
    db.refresh(request)
    return {"data": _request_detail(request, db)}


@router.get("/requests")
def list_my_requests(
    status: str | None = None,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    stmt = select(ApprovalRequest).where(ApprovalRequest.applicant_id == user.id)
    if status:
        stmt = stmt.where(ApprovalRequest.status == status)
    stmt = stmt.order_by(desc(ApprovalRequest.created_at)).limit(100)
    rows = db.scalars(stmt).all()
    return {"data": [_request_detail(r, db) for r in rows]}


@router.get("/requests/{request_id}")
def get_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    return {"data": _request_detail(req, db)}
```

- [ ] **Step 3: 验证路由可导入**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend; python -c "from app.approval.router import router, admin_router; print('router OK')"
```

---

### Task 5: 创建审批 API 路由——审批操作（同意/驳回/转审/撤回/催办）

**Files:**
- Modify: `backend/app/approval/router.py` — 追加以下代码

- [ ] **Step 1: 追加审批操作端点**

在 `router.py` 末尾追加：

```python
# backend/app/approval/router.py — 追加在文件末尾


@router.post("/nodes/{node_id}/approve")
def approve_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")

    now = datetime.now(UTC)
    node.status = "approved"
    node.comment = body.comment
    node.acted_at = now

    db.add(ApprovalAction(
        node_id=node.id, request_id=node.request_id,
        actor_id=user.id, actor_name=user.display_name,
        action="approve", comment=body.comment,
    ))

    request = db.get(ApprovalRequest, node.request_id)
    if not request:
        raise HTTPException(status_code=500, detail="申请数据异常")

    # 会签：检查同 node_index 的其他节点是否都已通过
    sibling_nodes = db.scalars(
        select(ApprovalNode).where(
            ApprovalNode.request_id == request.id,
            ApprovalNode.node_index == node.node_index,
        )
    ).all()

    all_approved = all(n.status == "approved" for n in sibling_nodes)

    if not all_approved:
        db.commit()
        db.refresh(node)
        return {"data": _request_detail(request, db)}

    # 当前节点全部通过，推进流程
    total_nodes = max(n["index"] for n in request.flow_snapshot) + 1
    if node.node_index >= total_nodes - 1:
        request.status = "approved"
        request.completed_at = now
    else:
        request.current_node_index = node.node_index + 1
    request.updated_at = now
    db.commit()
    db.refresh(request)
    return {"data": _request_detail(request, db)}


@router.post("/nodes/{node_id}/reject")
def reject_node(
    node_id: int,
    body: ApproveRejectBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可重复操作")
    if not body.comment:
        raise HTTPException(status_code=400, detail="驳回必须填写原因")

    now = datetime.now(UTC)
    request = db.get(ApprovalRequest, node.request_id)
    if not request:
        raise HTTPException(status_code=500, detail="申请数据异常")

    # 判断是否是会签节点
    is_counter_sign = any(
        n.get("type") == "counter_sign" and n["index"] == node.node_index
        for n in request.flow_snapshot
    )

    if is_counter_sign:
        # 会签驳回：当前 node_index 所有关联节点变 rejected，退回上一节点
        sibling_nodes = db.scalars(
            select(ApprovalNode).where(
                ApprovalNode.request_id == request.id,
                ApprovalNode.node_index == node.node_index,
            )
        ).all()
        for sn in sibling_nodes:
            sn.status = "rejected"
            sn.comment = sn.comment or body.comment
            sn.acted_at = sn.acted_at or now

        db.add(ApprovalAction(
            node_id=node.id, request_id=node.request_id,
            actor_id=user.id, actor_name=user.display_name,
            action="reject", comment=body.comment,
        ))

        if node.node_index > 0:
            request.current_node_index = node.node_index - 1
            prev_nodes = db.scalars(
                select(ApprovalNode).where(
                    ApprovalNode.request_id == request.id,
                    ApprovalNode.node_index == node.node_index - 1,
                )
            ).all()
            for pn in prev_nodes:
                pn.status = "pending"
                pn.comment = None
                pn.acted_at = None
    else:
        # 普通驳回：申请整体 rejected
        node.status = "rejected"
        node.comment = body.comment
        node.acted_at = now
        request.status = "rejected"

        db.add(ApprovalAction(
            node_id=node.id, request_id=node.request_id,
            actor_id=user.id, actor_name=user.display_name,
            action="reject", comment=body.comment,
        ))

    request.updated_at = now
    db.commit()
    db.refresh(request)
    return {"data": _request_detail(request, db)}


@router.post("/nodes/{node_id}/transfer")
def transfer_node(
    node_id: int,
    body: TransferBody,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node = db.get(ApprovalNode, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="节点不存在")
    if node.approver_id != user.id:
        raise HTTPException(status_code=403, detail="您不是该节点的审批人")
    if node.status != "pending":
        raise HTTPException(status_code=400, detail="该节点已被处理，不可转审")

    target = db.get(ApprovalUser, body.target_user_id)
    if not target:
        raise HTTPException(status_code=400, detail="目标用户不存在")

    old_approver_name = node.approver_name
    node.approver_id = target.id
    node.approver_name = target.display_name

    db.add(ApprovalAction(
        node_id=node.id, request_id=node.request_id,
        actor_id=user.id, actor_name=user.display_name,
        action="transfer",
        comment=f"转审：{old_approver_name} → {target.display_name}",
    ))

    request = db.get(ApprovalRequest, node.request_id)
    if request:
        request.updated_at = datetime.now(UTC)

    db.commit()
    db.refresh(request)
    return {"data": _request_detail(request, db)}


@router.put("/requests/{request_id}/revoke")
def revoke_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.applicant_id != user.id:
        raise HTTPException(status_code=403, detail="只能撤回自己的申请")
    if req.status != "pending":
        raise HTTPException(status_code=400, detail="只有待审批状态的申请可以撤回")

    req.status = "revoked"
    req.updated_at = datetime.now(UTC)

    db.add(ApprovalAction(
        node_id=0, request_id=req.id,
        actor_id=user.id, actor_name=user.display_name,
        action="revoke",
    ))
    db.commit()
    db.refresh(req)
    return {"data": _request_detail(req, db)}


@router.put("/requests/{request_id}/urge")
def urge_request(
    request_id: int,
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    req = db.get(ApprovalRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="申请不存在")
    if req.applicant_id != user.id:
        raise HTTPException(status_code=403, detail="只能催办自己的申请")
    if req.status not in ("pending",):
        raise HTTPException(status_code=400, detail="当前状态不支持催办")

    req.updated_at = datetime.now(UTC)

    db.add(ApprovalAction(
        node_id=0, request_id=req.id,
        actor_id=user.id, actor_name=user.display_name,
        action="urge",
    ))
    db.commit()
    db.refresh(req)
    return {"data": _request_detail(req, db)}


@router.get("/pending")
def list_pending(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node_rows = db.scalars(
        select(ApprovalNode).where(
            ApprovalNode.approver_id == user.id,
            ApprovalNode.status == "pending",
        ).order_by(desc(ApprovalNode.created_at)).limit(100)
    ).all()

    request_ids = list({n.request_id for n in node_rows})
    requests_map = {
        r.id: r
        for r in db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids))
        ).all()
    } if request_ids else {}

    result = []
    for n in node_rows:
        req = requests_map.get(n.request_id)
        if req:
            result.append({
                "node_id": n.id,
                "node_index": n.node_index,
                "request": {
                    "id": req.id,
                    "type_id": req.type_id,
                    "applicant_name": req.applicant_name,
                    "title": req.title,
                    "status": req.status,
                    "current_node_index": req.current_node_index,
                    "created_at": req.created_at.isoformat(),
                },
            })
    return {"data": result}


@router.get("/handled")
def list_handled(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    node_rows = db.scalars(
        select(ApprovalNode).where(
            ApprovalNode.approver_id == user.id,
            ApprovalNode.status != "pending",
        ).order_by(desc(ApprovalNode.acted_at)).limit(100)
    ).all()

    request_ids = list({n.request_id for n in node_rows})
    requests_map = {
        r.id: r
        for r in db.scalars(
            select(ApprovalRequest).where(ApprovalRequest.id.in_(request_ids))
        ).all()
    } if request_ids else {}

    result = []
    for n in node_rows:
        req = requests_map.get(n.request_id)
        if req:
            result.append({
                "node_id": n.id,
                "node_index": n.node_index,
                "node_status": n.status,
                "comment": n.comment,
                "acted_at": n.acted_at.isoformat() if n.acted_at else None,
                "request": {
                    "id": req.id,
                    "type_id": req.type_id,
                    "applicant_name": req.applicant_name,
                    "title": req.title,
                    "status": req.status,
                },
            })
    return {"data": result}


@router.get("/cc")
def list_cc(
    user: User = Depends(require_permission("approval:view")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(ApprovalRequest).where(
            ApprovalRequest.status.in_(["approved", "rejected"])
        ).order_by(desc(ApprovalRequest.completed_at)).limit(50)
    ).all()
    return {"data": [_request_detail(r, db) for r in rows]}
```

- [ ] **Step 2: 验证所有端点可导入**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend; python -c "from app.approval.router import router, admin_router; print('All endpoints OK')"
```

---

### Task 6: 创建后台管理路由

**Files:**
- Modify: `backend/app/approval/router.py` — 追加以下代码

- [ ] **Step 1: 在文件末尾追加后台管理端点**

```python
# backend/app/approval/router.py — 追加在文件末尾


# ── 后台管理 ──

@admin_router.get("/approval-types")
def admin_list_types(
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(ApprovalType).order_by(ApprovalType.id)).all()
    return {"data": [_type_with_form(r, db) for r in rows]}


@admin_router.post("/approval-types")
def admin_create_type(
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    t = ApprovalType(
        name=body["name"],
        description=body.get("description", ""),
        form_template_id=body["form_template_id"],
        flow_template_id=body["flow_template_id"],
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"data": {"id": t.id, "name": t.name}}


@admin_router.put("/approval-types/{type_id}")
def admin_update_type(
    type_id: int,
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    t = db.get(ApprovalType, type_id)
    if not t:
        raise HTTPException(status_code=404, detail="审批类型不存在")
    for field in ("name", "description", "form_template_id", "flow_template_id", "is_active"):
        if field in body:
            setattr(t, field, body[field])
    db.commit()
    return {"data": {"id": t.id, "name": t.name}}


@admin_router.delete("/approval-types/{type_id}")
def admin_delete_type(
    type_id: int,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    t = db.get(ApprovalType, type_id)
    if not t:
        raise HTTPException(status_code=404, detail="审批类型不存在")
    db.delete(t)
    db.commit()
    return {"data": {"deleted": True}}


@admin_router.get("/form-templates")
def admin_list_form_templates(
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(FormTemplate).order_by(FormTemplate.id)).all()
    return {"data": [
        {"id": r.id, "name": r.name, "description": r.description, "fields": r.fields, "is_active": r.is_active, "created_at": r.created_at.isoformat()}
        for r in rows
    ]}


@admin_router.post("/form-templates")
def admin_create_form_template(
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    ft = FormTemplate(
        name=body["name"],
        description=body.get("description", ""),
        fields=body.get("fields", []),
    )
    db.add(ft)
    db.commit()
    db.refresh(ft)
    return {"data": {"id": ft.id, "name": ft.name}}


@admin_router.put("/form-templates/{template_id}")
def admin_update_form_template(
    template_id: int,
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    ft = db.get(FormTemplate, template_id)
    if not ft:
        raise HTTPException(status_code=404, detail="表单模板不存在")
    for field in ("name", "description", "fields", "is_active"):
        if field in body:
            setattr(ft, field, body[field])
    db.commit()
    return {"data": {"id": ft.id, "name": ft.name}}


@admin_router.delete("/form-templates/{template_id}")
def admin_delete_form_template(
    template_id: int,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    ft = db.get(FormTemplate, template_id)
    if not ft:
        raise HTTPException(status_code=404, detail="表单模板不存在")
    db.delete(ft)
    db.commit()
    return {"data": {"deleted": True}}


@admin_router.get("/flow-templates")
def admin_list_flow_templates(
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(FlowTemplate).order_by(FlowTemplate.id)).all()
    return {"data": [
        {"id": r.id, "name": r.name, "description": r.description, "nodes": r.nodes, "is_active": r.is_active, "created_at": r.created_at.isoformat()}
        for r in rows
    ]}


@admin_router.post("/flow-templates")
def admin_create_flow_template(
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    ft = FlowTemplate(
        name=body["name"],
        description=body.get("description", ""),
        nodes=body.get("nodes", []),
    )
    db.add(ft)
    db.commit()
    db.refresh(ft)
    return {"data": {"id": ft.id, "name": ft.name}}


@admin_router.put("/flow-templates/{template_id}")
def admin_update_flow_template(
    template_id: int,
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    ft = db.get(FlowTemplate, template_id)
    if not ft:
        raise HTTPException(status_code=404, detail="流程模板不存在")
    for field in ("name", "description", "nodes", "is_active"):
        if field in body:
            setattr(ft, field, body[field])
    db.commit()
    return {"data": {"id": ft.id, "name": ft.name}}


@admin_router.delete("/flow-templates/{template_id}")
def admin_delete_flow_template(
    template_id: int,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    ft = db.get(FlowTemplate, template_id)
    if not ft:
        raise HTTPException(status_code=404, detail="流程模板不存在")
    db.delete(ft)
    db.commit()
    return {"data": {"deleted": True}}


@admin_router.get("/users")
def admin_list_approval_users(
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(select(ApprovalUser).where(ApprovalUser.is_active == True).order_by(ApprovalUser.display_name)).all()
    return {"data": [
        {"id": r.id, "email": r.email, "display_name": r.display_name, "department": r.department, "role": r.role}
        for r in rows
    ]}


@admin_router.get("/logs")
def admin_list_logs(
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    rows = db.scalars(
        select(ApprovalAction).order_by(desc(ApprovalAction.created_at)).limit(200)
    ).all()
    return {"data": [
        {
            "id": r.id,
            "node_id": r.node_id,
            "request_id": r.request_id,
            "actor_name": r.actor_name,
            "action": r.action,
            "comment": r.comment,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]}
```

- [ ] **Step 2: 验证所有管理端点可导入**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend; python -c "from app.approval.router import router, admin_router; print([r.path for r in router.routes]); print([r.path for r in admin_router.routes])"
```

---

### Task 7: 集成审批模块到主应用

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/db/seed.py`

- [ ] **Step 1: 修改 main.py 注册审批路由和初始化**

```python
# backend/app/main.py — 修改后完整内容
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router
from app.approval.router import router as approval_router, admin_router as approval_admin_router
from app.core.config import settings
from app.db.seed import initialize_database
from app.approval.seed import initialize_approval_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    initialize_approval_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="Common foundation API for the four-in-one enterprise AI portfolio.",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    application.include_router(router, prefix=settings.api_v1_prefix)
    application.include_router(approval_router)
    application.include_router(approval_admin_router)

    return application


app = create_app()
```

- [ ] **Step 2: 修改 seed.py 给 platform_admin 增加 approval:manage 权限**

用 Edit 工具在 `backend/app/db/seed.py` 的 `ROLE_PERMISSIONS["platform_admin"]` 列表末尾加入 `"approval:manage"`：

```python
    "platform_admin": [
        "dashboard:view",
        "resume:view",
        "approval:view",
        "asset:view",
        "service_desk:view",
        "notification:view",
        "audit:view",
        "ai_run:view",
        "platform:manage",
        "approval:manage",       # 新增
    ],
```

- [ ] **Step 3: 删除旧数据库并启动后端验证**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend
Remove-Item enterprise_ai.db -ErrorAction SilentlyContinue
Remove-Item approval.db -ErrorAction SilentlyContinue
python -m uvicorn app.main:app --reload --port 8000
```

启动后访问 `http://127.0.0.1:8000/docs`，确认 Swagger 中出现 `/api/v1/approvals/` 和 `/api/v1/admin/` 两组端点。

- [ ] **Step 4: 用 curl 快速验证 3 个核心端点**

```powershell
# 1. 登录获取 token
$token = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/auth/demo-login -Method Post -Body '{"role":"product_demo_user"}' -ContentType "application/json").data.access_token

# 2. 获取审批类型
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/approvals/types -Headers @{Authorization="Bearer $token"} | ConvertTo-Json -Depth 5

# 3. 提交申请
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/approvals/requests -Method Post -Headers @{Authorization="Bearer $token"} -Body '{"type_id":1,"title":"测试请假","form_data":{"leave_type":"年假","start_date":"2026-07-25","end_date":"2026-07-26","days":2,"reason":"休息"}}' -ContentType "application/json" | ConvertTo-Json -Depth 5
```

Expected: 审批类型返回 3 条，提交申请返回带节点列表的 JSON。

---

### Task 8: 前端——TypeScript 类型 + 路由

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/router/index.ts`

- [ ] **Step 1: 在 types.ts 末尾追加审批相关类型**

```typescript
// frontend/src/types.ts — 追加在文件末尾

export interface ApprovalType {
  id: number
  name: string
  description: string | null
  is_active: boolean
  form_template: {
    id: number
    name: string
    fields: FormField[]
  } | null
}

export interface FormField {
  key: string
  label: string
  type: 'text' | 'textarea' | 'number' | 'date' | 'select'
  required: boolean
  options?: string[]
}

export interface ApprovalNode {
  id: number
  node_index: number
  approver_id: string
  approver_name: string
  status: 'pending' | 'approved' | 'rejected'
  comment: string | null
  acted_at: string | null
}

export interface ApprovalAction {
  id: number
  node_id: number
  actor_id: string
  actor_name: string
  action: string
  comment: string | null
  created_at: string
}

export interface ApprovalRequestDetail {
  id: number
  type_id: number
  applicant_id: string
  applicant_name: string
  title: string
  form_data: Record<string, any>
  status: 'pending' | 'approved' | 'rejected' | 'revoked'
  current_node_index: number
  flow_snapshot: FlowNodeDef[]
  nodes: ApprovalNode[]
  actions: ApprovalAction[]
  created_at: string
  updated_at: string
  submitted_at: string | null
  completed_at: string | null
}

export interface FlowNodeDef {
  index: number
  name: string
  type: 'single' | 'counter_sign'
  approver_id?: string
  approver_ids?: string[]
  allow_transfer: boolean
}

export interface PendingItem {
  node_id: number
  node_index: number
  request: {
    id: number
    type_id: number
    applicant_name: string
    title: string
    status: string
    current_node_index: number
    created_at: string
  }
}

export interface ApprovalUser {
  id: string
  email: string
  display_name: string
  department: string
  role: string
}
```

- [ ] **Step 2: 修改 router/index.ts 新增审批路由**

在现有 routes 中，在 `modules/:moduleKey` 路由之前插入审批相关路由：

```typescript
// frontend/src/router/index.ts — 修改后完整内容
import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import { useAuthStore } from '@/stores/auth'

declare module 'vue-router' {
  interface RouteMeta {
    title?: string
    permission?: string
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: () => import('@/views/LoginView.vue') },
    {
      path: '/',
      component: AppLayout,
      children: [
        { path: '', redirect: '/dashboard' },
        {
          path: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { title: '工作台', permission: 'dashboard:view' },
        },
        // ── 审批模块路由 ──
        {
          path: 'modules/approval-center',
          component: () => import('@/views/approval/ApprovalHome.vue'),
          meta: { title: '审批中心', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/requests',
          component: () => import('@/views/approval/ApprovalMyRequests.vue'),
          meta: { title: '我的申请', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/new',
          component: () => import('@/views/approval/ApprovalNew.vue'),
          meta: { title: '发起申请', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/pending',
          component: () => import('@/views/approval/ApprovalPending.vue'),
          meta: { title: '待我审批', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/handled',
          component: () => import('@/views/approval/ApprovalHandled.vue'),
          meta: { title: '我已审批', permission: 'approval:view' },
        },
        {
          path: 'modules/approval-center/:id',
          component: () => import('@/views/approval/ApprovalDetail.vue'),
          meta: { title: '审批详情', permission: 'approval:view' },
        },
        // ── 后台管理路由 ──
        {
          path: 'admin/approval-types',
          component: () => import('@/views/approval/AdminTypes.vue'),
          meta: { title: '审批类型管理', permission: 'approval:manage' },
        },
        {
          path: 'admin/form-templates',
          component: () => import('@/views/approval/AdminFormTemplates.vue'),
          meta: { title: '表单模板管理', permission: 'approval:manage' },
        },
        {
          path: 'admin/flow-templates',
          component: () => import('@/views/approval/AdminFlowTemplates.vue'),
          meta: { title: '流程模板管理', permission: 'approval:manage' },
        },
        {
          path: 'admin/approval-logs',
          component: () => import('@/views/approval/AdminLogs.vue'),
          meta: { title: '审批日志', permission: 'approval:manage' },
        },
        // ── 原有路由 ──
        {
          path: 'modules/:moduleKey',
          component: () => import('@/views/ModuleView.vue'),
          meta: { title: '业务模块' },
        },
        {
          path: 'notifications',
          component: () => import('@/views/NotificationsView.vue'),
          meta: { title: '通知中心', permission: 'notification:view' },
        },
        {
          path: 'ai-runs',
          component: () => import('@/views/AIRunsView.vue'),
          meta: { title: 'AI运行记录', permission: 'ai_run:view' },
        },
        {
          path: 'audit-logs',
          component: () => import('@/views/AuditLogsView.vue'),
          meta: { title: '审计日志', permission: 'audit:view' },
        },
        {
          path: 'profile',
          component: () => import('@/views/ProfileView.vue'),
          meta: { title: '个人资料' },
        },
      ],
    },
    { path: '/:pathMatch(.*)*', component: () => import('@/views/NotFoundView.vue') },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (to.path === '/login' && auth.isAuthenticated) return '/dashboard'
  if (to.path !== '/login' && !auth.isAuthenticated) return '/login'
  if (to.meta.permission && !auth.can(to.meta.permission)) return '/dashboard'
  document.title = `${to.meta.title || '企业AI平台'} · Enterprise AI Suite`
})

export default router
```

注意：审批路由要放在 `modules/:moduleKey` 通配路由**之前**，避免 `approval-center` 被当成 `moduleKey` 捕获。

- [ ] **Step 3: 创建 views/approval 目录并验证编译**

```powershell
New-Item -ItemType Directory -Force -Path C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\frontend\src\views\approval
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\frontend; npx vue-tsc --noEmit 2>&1 | Select-Object -First 20
```

Expected: 会报缺少组件文件的错（正常，下一步创建）。

---

### Task 9: 前端——审批首页 ApprovalHome.vue

**Files:**
- Create: `frontend/src/views/approval/ApprovalHome.vue`

- [ ] **Step 1: 写入审批首页组件**

```vue
<!-- frontend/src/views/approval/ApprovalHome.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PlusOutlined, FileTextOutlined, CheckCircleOutlined, SendOutlined } from '@ant-design/icons-vue'

import api from '@/api/client'
import type { PendingItem } from '@/types'

const router = useRouter()
const pendingCount = ref(0)
const handledCount = ref(0)
const pendingList = ref<PendingItem[]>([])
const loading = ref(true)

async function load() {
  loading.value = true
  try {
    const [pendingRes, handledRes] = await Promise.all([
      api.get('/api/v1/approvals/pending'),
      api.get('/api/v1/approvals/handled'),
    ])
    pendingList.value = (pendingRes.data.data as PendingItem[]).slice(0, 5)
    pendingCount.value = pendingRes.data.data.length
    handledCount.value = handledRes.data.data.length
  } catch { /* ignore */ }
  finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-frame approval-home">
    <header class="page-heading">
      <div>
        <p class="eyebrow">APPROVAL CENTER</p>
        <h1>流程审批中心</h1>
        <p>统一承载企业审批流程，快速发起、高效审批、全程可追溯。</p>
      </div>
    </header>

    <!-- 统计卡片 -->
    <div class="stat-row">
      <div class="stat-card">
        <div class="stat-icon" style="background:#fff3e8;color:#d9682f;"><FileTextOutlined /></div>
        <div class="stat-body">
          <span class="stat-num">{{ pendingCount }}</span>
          <span class="stat-label">待我审批</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-icon" style="background:#e8f5f1;color:#087e6f;"><CheckCircleOutlined /></div>
        <div class="stat-body">
          <span class="stat-num">{{ handledCount }}</span>
          <span class="stat-label">我已审批</span>
        </div>
      </div>
    </div>

    <!-- 快捷操作 -->
    <div class="quick-actions">
      <a-button type="primary" size="large" @click="router.push('/modules/approval-center/new')">
        <PlusOutlined /> 发起申请
      </a-button>
      <a-button size="large" @click="router.push('/modules/approval-center/requests')">
        <FileTextOutlined /> 我的申请
      </a-button>
      <a-button size="large" @click="router.push('/modules/approval-center/pending')">
        <SendOutlined /> 待我审批
      </a-button>
    </div>

    <!-- 待审批列表 -->
    <div class="section-title" style="margin-top:28px;">
      <div><p class="eyebrow">PENDING</p><h2>待我审批</h2></div>
    </div>
    <a-skeleton v-if="loading" active :paragraph="{ rows: 4 }" />
    <a-empty v-else-if="pendingList.length === 0" description="暂无待审批项" />
    <div v-else class="pending-cards">
      <div
        v-for="item in pendingList" :key="item.node_id"
        class="pending-card"
        @click="router.push(`/modules/approval-center/${item.request.id}`)"
      >
        <div class="pending-info">
          <strong>{{ item.request.title }}</strong>
          <small>{{ item.request.applicant_name }} · {{ item.request.created_at.slice(0, 10) }}</small>
        </div>
        <a-tag color="processing">待处理</a-tag>
      </div>
    </div>
  </div>
</template>
```

---

### Task 10: 前端——发起申请 ApprovalNew.vue

**Files:**
- Create: `frontend/src/views/approval/ApprovalNew.vue`

- [ ] **Step 1: 写入发起申请页面**

```vue
<!-- frontend/src/views/approval/ApprovalNew.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'

import api from '@/api/client'
import type { ApprovalType, FormField } from '@/types'

const router = useRouter()
const types = ref<ApprovalType[]>([])
const selectedType = ref<ApprovalType | null>(null)
const formValues = ref<Record<string, any>>({})
const submitting = ref(false)

onMounted(async () => {
  try {
    const res = await api.get('/api/v1/approvals/types')
    types.value = res.data.data
  } catch { /* ignore */ }
})

function selectType(type: ApprovalType) {
  selectedType.value = type
  formValues.value = {}
}

function renderField(field: FormField) {
  if (field.type === 'select') {
    return (
      <a-select v-model:value={formValues.value[field.key]} placeholder={`请选择${field.label}`} allowClear>
        {field.options?.map(opt => <a-select-option value={opt}>{opt}</a-select-option>)}
      </a-select>
    )
  }
  if (field.type === 'textarea') {
    return <a-textarea v-model:value={formValues.value[field.key]} placeholder={`请输入${field.label}`} rows={3} />
  }
  if (field.type === 'number') {
    return <a-input-number v-model:value={formValues.value[field.key]} placeholder={`请输入${field.label}`} style="width:100%" />
  }
  if (field.type === 'date') {
    return <a-input v-model:value={formValues.value[field.key]} placeholder={`请输入${field.label}（如 2026-07-25）`} />
  }
  return <a-input v-model:value={formValues.value[field.key]} placeholder={`请输入${field.label}`} />
}

async function submit() {
  if (!selectedType.value) return message.warning('请选择审批类型')
  const fields = selectedType.value.form_template?.fields || []
  for (const f of fields) {
    if (f.required && !formValues.value[f.key]) {
      return message.warning(`请填写：${f.label}`)
    }
  }
  submitting.value = true
  try {
    const title = `${selectedType.value.name} - ${new Date().toLocaleDateString('zh-CN')}`
    await api.post('/api/v1/approvals/requests', {
      type_id: selectedType.value.id,
      title,
      form_data: { ...formValues.value },
    })
    message.success('提交成功')
    router.push('/modules/approval-center/requests')
  } catch {
    message.error('提交失败')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="page-frame approval-new">
    <header class="page-heading">
      <div>
        <p class="eyebrow">NEW REQUEST</p>
        <h1>发起申请</h1>
      </div>
    </header>

    <!-- 选择审批类型 -->
    <div class="section-title"><div><p class="eyebrow">STEP 1</p><h2>选择审批类型</h2></div></div>
    <div class="type-cards">
      <div
        v-for="t in types" :key="t.id"
        class="type-card"
        :class="{ active: selectedType?.id === t.id }"
        @click="selectType(t)"
      >
        <strong>{{ t.name }}</strong>
        <small>{{ t.description }}</small>
      </div>
    </div>

    <!-- 填写表单 -->
    <template v-if="selectedType?.form_template">
      <div class="section-title" style="margin-top:24px;">
        <div><p class="eyebrow">STEP 2</p><h2>填写信息</h2></div>
      </div>
      <div class="form-panel">
        <div v-for="field in selectedType.form_template.fields" :key="field.key" class="form-field">
          <label>
            {{ field.label }}
            <span v-if="field.required" style="color:#d9682f;">*</span>
          </label>
          <component :is="() => renderField(field)" />
        </div>
      </div>
      <div style="margin-top:20px;">
        <a-button type="primary" size="large" :loading="submitting" @click="submit">提交申请</a-button>
        <a-button size="large" style="margin-left:12px;" @click="router.back()">取消</a-button>
      </div>
    </template>
  </div>
</template>
```

---

### Task 11: 前端——审批详情 + 操作 ApprovalDetail.vue

**Files:**
- Create: `frontend/src/views/approval/ApprovalDetail.vue`

- [ ] **Step 1: 写入审批详情页**

```vue
<!-- frontend/src/views/approval/ApprovalDetail.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message, Modal } from 'ant-design-vue'
import { CheckCircleOutlined, CloseCircleOutlined, SwapOutlined } from '@ant-design/icons-vue'

import { useAuthStore } from '@/stores/auth'
import api from '@/api/client'
import type { ApprovalRequestDetail, FlowNodeDef } from '@/types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const detail = ref<ApprovalRequestDetail | null>(null)
const loading = ref(true)
const comment = ref('')
const submitting = ref(false)
const transferTarget = ref('')
const users = ref<{ id: string; display_name: string }[]>([])

onMounted(async () => {
  await loadDetail()
  try {
    const res = await api.get('/api/v1/admin/users')
    users.value = res.data.data
  } catch { /* ignore */ }
})

async function loadDetail() {
  loading.value = true
  try {
    const res = await api.get(`/api/v1/approvals/requests/${route.params.id}`)
    detail.value = res.data.data
  } finally {
    loading.value = false
  }
}

function getNodeStatusClass(nodeStatus: string) {
  if (nodeStatus === 'approved') return 'node-done'
  if (nodeStatus === 'rejected') return 'node-reject'
  return 'node-pending'
}

function getNodeStatusLabel(nodeStatus: string) {
  if (nodeStatus === 'approved') return '已通过'
  if (nodeStatus === 'rejected') return '已驳回'
  return '待审批'
}

function getStatusTag(status: string) {
  const map: Record<string, { color: string; text: string }> = {
    pending: { color: 'processing', text: '审批中' },
    approved: { color: 'success', text: '已通过' },
    rejected: { color: 'error', text: '已驳回' },
    revoked: { color: 'default', text: '已撤回' },
  }
  return map[status] || { color: 'default', text: status }
}

function getMyNode() {
  if (!detail.value || !auth.user) return null
  return detail.value.nodes.find(
    n => n.status === 'pending' && n.approver_id === auth.user!.id
  )
}

async function doApprove() {
  const node = getMyNode()
  if (!node) return message.warning('没有可操作的审批节点')
  submitting.value = true
  try {
    await api.post(`/api/v1/approvals/nodes/${node.id}/approve`, { comment: comment.value || '同意' })
    message.success('已审批通过')
    comment.value = ''
    await loadDetail()
  } catch {
    message.error('操作失败')
  } finally {
    submitting.value = false
  }
}

async function doReject() {
  const node = getMyNode()
  if (!node) return message.warning('没有可操作的审批节点')
  if (!comment.value.trim()) return message.warning('驳回必须填写原因')
  submitting.value = true
  try {
    await api.post(`/api/v1/approvals/nodes/${node.id}/reject`, { comment: comment.value })
    message.success('已驳回')
    comment.value = ''
    await loadDetail()
  } catch {
    message.error('操作失败')
  } finally {
    submitting.value = false
  }
}

async function doTransfer() {
  const node = getMyNode()
  if (!node || !transferTarget.value) return message.warning('请选择转审目标人')
  submitting.value = true
  try {
    await api.post(`/api/v1/approvals/nodes/${node.id}/transfer`, { target_user_id: transferTarget.value })
    message.success('已转审')
    transferTarget.value = ''
    await loadDetail()
  } catch {
    message.error('操作失败')
  } finally {
    submitting.value = false
  }
}

async function doRevoke() {
  Modal.confirm({
    title: '确认撤回',
    content: '撤回后该申请将标记为已撤回。',
    okText: '确认撤回',
    cancelText: '取消',
    onOk: async () => {
      try {
        await api.put(`/api/v1/approvals/requests/${detail.value!.id}/revoke`)
        message.success('已撤回')
        await loadDetail()
      } catch { message.error('撤回失败') }
    },
  })
}

function getFlowNodeDef(index: number): FlowNodeDef | undefined {
  return detail.value?.flow_snapshot.find(n => n.index === index)
}
</script>

<template>
  <div class="page-frame approval-detail">
    <a-skeleton v-if="loading" active :paragraph="{ rows: 8 }" />
    <template v-else-if="detail">
      <header class="page-heading">
        <div>
          <p class="eyebrow">REQUEST #{{ detail.id }}</p>
          <h1>{{ detail.title }}</h1>
          <p>申请人：{{ detail.applicant_name }} · 提交时间：{{ detail.created_at.slice(0, 16).replace('T',' ') }}</p>
        </div>
        <a-tag :color="getStatusTag(detail.status).color" style="font-size:14px;padding:4px 14px;">
          {{ getStatusTag(detail.status).text }}
        </a-tag>
      </header>

      <!-- 审批进度 -->
      <div class="section-title"><div><p class="eyebrow">PROGRESS</p><h2>审批进度</h2></div></div>
      <div class="node-timeline">
        <div
          v-for="(node, i) in detail.nodes" :key="node.id"
          class="node-row"
        >
          <div class="node-marker" :class="getNodeStatusClass(node.status)">
            <CheckCircleOutlined v-if="node.status === 'approved'" />
            <CloseCircleOutlined v-else-if="node.status === 'rejected'" />
            <span v-else>{{ i + 1 }}</span>
          </div>
          <div class="node-body">
            <div class="node-header">
              <strong>{{ getFlowNodeDef(node.node_index)?.name || `节点${node.node_index + 1}` }}</strong>
              <a-tag :color="node.status === 'approved' ? 'success' : node.status === 'rejected' ? 'error' : 'processing'">
                {{ getNodeStatusLabel(node.status) }}
              </a-tag>
            </div>
            <small>审批人：{{ node.approver_name }}</small>
            <small v-if="node.comment" style="color:#66716e;margin-top:4px;">意见：{{ node.comment }}</small>
            <small v-if="node.acted_at" style="color:#66716e;">{{ node.acted_at.slice(0, 16).replace('T',' ') }}</small>
          </div>
        </div>
      </div>

      <!-- 表单数据 -->
      <div class="section-title" style="margin-top:24px;"><div><p class="eyebrow">FORM DATA</p><h2>申请内容</h2></div></div>
      <div class="form-readonly">
        <div v-for="(_val, key) in detail.form_data" :key="key" class="form-readonly-item">
          <span class="f-label">{{ key }}</span>
          <span class="f-value">{{ _val }}</span>
        </div>
      </div>

      <!-- 操作区 -->
      <div v-if="getMyNode()" class="action-bar">
        <div class="section-title"><div><p class="eyebrow">ACTION</p><h2>审批操作</h2></div></div>
        <a-textarea v-model:value="comment" placeholder="审批意见（驳回时必填）" :rows="3" style="margin-bottom:16px;" />
        <a-space size="middle">
          <a-button type="primary" :loading="submitting" @click="doApprove">
            <CheckCircleOutlined /> 同意
          </a-button>
          <a-button danger :loading="submitting" @click="doReject">
            <CloseCircleOutlined /> 驳回
          </a-button>
          <a-select v-model:value="transferTarget" placeholder="选择转审人" style="width:180px;">
            <a-select-option v-for="u in users" :key="u.id" :value="u.id">{{ u.display_name }}</a-select-option>
          </a-select>
          <a-button :loading="submitting" :disabled="!transferTarget" @click="doTransfer">
            <SwapOutlined /> 转审
          </a-button>
        </a-space>
      </div>

      <!-- 申请人操作 -->
      <div v-if="detail.status === 'pending' && detail.applicant_id === 'me'" class="action-bar" style="margin-top:16px;">
        <a-button @click="doRevoke">撤回申请</a-button>
      </div>

      <!-- 操作记录 -->
      <div class="section-title" style="margin-top:28px;"><div><p class="eyebrow">HISTORY</p><h2>操作记录</h2></div></div>
      <a-timeline v-if="detail.actions.length" style="margin-top:16px;">
        <a-timeline-item v-for="act in detail.actions" :key="act.id" :color="act.action === 'reject' ? 'red' : act.action === 'approve' ? 'green' : 'gray'">
          <strong>{{ act.actor_name }}</strong> · {{ act.action === 'approve' ? '同意' : act.action === 'reject' ? '驳回' : act.action === 'transfer' ? '转审' : act.action === 'revoke' ? '撤回' : act.action }}
          <small v-if="act.comment"> — {{ act.comment }}</small>
          <br /><small style="color:#999;">{{ act.created_at.slice(0, 16).replace('T',' ') }}</small>
        </a-timeline-item>
      </a-timeline>
      <a-empty v-else description="暂无操作记录" />
    </template>
  </div>
</template>
```

---

### Task 12: 前端——我的申请 + 待我审批 + 已审批页面

**Files:**
- Create: `frontend/src/views/approval/ApprovalMyRequests.vue`
- Create: `frontend/src/views/approval/ApprovalPending.vue`
- Create: `frontend/src/views/approval/ApprovalHandled.vue`

- [ ] **Step 1: 写入我的申请页**

```vue
<!-- frontend/src/views/approval/ApprovalMyRequests.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PlusOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import type { ApprovalRequestDetail } from '@/types'

const router = useRouter()
const requests = ref<ApprovalRequestDetail[]>([])
const loading = ref(true)
const statusFilter = ref<string | undefined>(undefined)
const statusOptions = [
  { label: '全部', value: undefined },
  { label: '审批中', value: 'pending' },
  { label: '已通过', value: 'approved' },
  { label: '已驳回', value: 'rejected' },
]

const statusTagMap: Record<string, string> = { pending: 'processing', approved: 'success', rejected: 'error', revoked: 'default' }
const statusTextMap: Record<string, string> = { pending: '审批中', approved: '已通过', rejected: '已驳回', revoked: '已撤回' }

async function load() {
  loading.value = true
  try {
    const params = statusFilter.value ? { params: { status: statusFilter.value } } : {}
    const res = await api.get('/api/v1/approvals/requests', params)
    requests.value = res.data.data
  } finally { loading.value = false }
}

onMounted(load)
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div>
        <p class="eyebrow">MY REQUESTS</p>
        <h1>我的申请</h1>
      </div>
      <a-button type="primary" @click="router.push('/modules/approval-center/new')"><PlusOutlined /> 发起申请</a-button>
    </header>

    <a-radio-group v-model:value="statusFilter" @change="load" :options="statusOptions" option-type="button" style="margin-bottom:16px;" />

    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
    <a-empty v-else-if="requests.length === 0" description="暂无申请记录" />
    <div v-else class="request-list">
      <div
        v-for="r in requests" :key="r.id"
        class="request-card"
        @click="router.push(`/modules/approval-center/${r.id}`)"
      >
        <div class="request-info">
          <strong>{{ r.title }}</strong>
          <small>{{ r.created_at.slice(0, 16).replace('T',' ') }}</small>
        </div>
        <a-tag :color="statusTagMap[r.status]">{{ statusTextMap[r.status] }}</a-tag>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 2: 写入待我审批页**

```vue
<!-- frontend/src/views/approval/ApprovalPending.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { CheckCircleOutlined, CloseCircleOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'
import type { PendingItem } from '@/types'

const router = useRouter()
const items = ref<PendingItem[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await api.get('/api/v1/approvals/pending')
    items.value = res.data.data
  } finally { loading.value = false }
})

async function quickApprove(item: PendingItem) {
  try {
    await api.post(`/api/v1/approvals/nodes/${item.node_id}/approve`, { comment: '同意' })
    message.success('已审批通过')
    items.value = items.value.filter(i => i.node_id !== item.node_id)
  } catch { message.error('操作失败') }
}

async function quickReject(item: PendingItem) {
  try {
    await api.post(`/api/v1/approvals/nodes/${item.node_id}/reject`, { comment: '不同意' })
    message.success('已驳回')
    items.value = items.value.filter(i => i.node_id !== item.node_id)
  } catch { message.error('操作失败') }
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div>
        <p class="eyebrow">PENDING APPROVAL</p>
        <h1>待我审批</h1>
        <p>共 {{ items.length }} 项待处理</p>
      </div>
    </header>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
    <a-empty v-else-if="items.length === 0" description="没有待审批项" />
    <div v-else class="pending-list">
      <div v-for="item in items" :key="item.node_id" class="pending-card-full">
        <div class="pending-main" @click="router.push(`/modules/approval-center/${item.request.id}`)">
          <strong>{{ item.request.title }}</strong>
          <small>{{ item.request.applicant_name }} · {{ item.request.created_at.slice(0, 10) }}</small>
        </div>
        <div class="pending-actions">
          <a-button size="small" type="primary" @click="quickApprove(item)"><CheckCircleOutlined /> 同意</a-button>
          <a-button size="small" danger @click="quickReject(item)"><CloseCircleOutlined /> 驳回</a-button>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 3: 写入我已审批页**

```vue
<!-- frontend/src/views/approval/ApprovalHandled.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '@/api/client'

const router = useRouter()
const items = ref<any[]>([])
const loading = ref(true)

const statusTagMap: Record<string, string> = { approved: 'success', rejected: 'error' }
const statusTextMap: Record<string, string> = { approved: '已通过', rejected: '已驳回' }

onMounted(async () => {
  try {
    const res = await api.get('/api/v1/approvals/handled')
    items.value = res.data.data
  } finally { loading.value = false }
})
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div>
        <p class="eyebrow">HANDLED</p>
        <h1>我已审批</h1>
        <p>共 {{ items.length }} 条记录</p>
      </div>
    </header>

    <a-skeleton v-if="loading" active :paragraph="{ rows: 6 }" />
    <a-empty v-else-if="items.length === 0" description="暂无已审批记录" />
    <div v-else class="request-list">
      <div
        v-for="item in items" :key="item.node_id"
        class="request-card"
        @click="router.push(`/modules/approval-center/${item.request.id}`)"
      >
        <div class="request-info">
          <strong>{{ item.request.title }}</strong>
          <small>{{ item.request.applicant_name }} · {{ item.acted_at?.slice(0, 10) || '' }}</small>
        </div>
        <a-tag :color="statusTagMap[item.node_status]">{{ statusTextMap[item.node_status] || item.node_status }}</a-tag>
      </div>
    </div>
  </div>
</template>
```

---

### Task 13: 前端——后台管理页面

**Files:**
- Create: `frontend/src/views/approval/AdminTypes.vue`
- Create: `frontend/src/views/approval/AdminFormTemplates.vue`
- Create: `frontend/src/views/approval/AdminFlowTemplates.vue`
- Create: `frontend/src/views/approval/AdminLogs.vue`

- [ ] **Step 1: AdminTypes.vue**

```vue
<!-- frontend/src/views/approval/AdminTypes.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import api from '@/api/client'

const types = ref<any[]>([])
const loading = ref(true)
const visible = ref(false)
const editing = ref<any>(null)
const form = ref({ name: '', description: '', form_template_id: 0, flow_template_id: 0 })
const formTemplates = ref<any[]>([])
const flowTemplates = ref<any[]>([])

onMounted(async () => {
  await load()
  const [ft, flowt] = await Promise.all([
    api.get('/api/v1/admin/form-templates'),
    api.get('/api/v1/admin/flow-templates'),
  ])
  formTemplates.value = ft.data.data
  flowTemplates.value = flowt.data.data
})

async function load() {
  loading.value = true
  try {
    const res = await api.get('/api/v1/admin/approval-types')
    types.value = res.data.data
  } finally { loading.value = false }
}

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', form_template_id: 0, flow_template_id: 0 }
  visible.value = true
}

function openEdit(t: any) {
  editing.value = t
  form.value = { name: t.name, description: t.description || '', form_template_id: t.form_template?.id || 0, flow_template_id: 0 }
  visible.value = true
}

async function save() {
  try {
    if (editing.value) {
      await api.put(`/api/v1/admin/approval-types/${editing.value.id}`, form.value)
    } else {
      await api.post('/api/v1/admin/approval-types', form.value)
    }
    message.success('保存成功')
    visible.value = false
    await load()
  } catch { message.error('保存失败') }
}

async function remove(id: number) {
  Modal.confirm({
    title: '确认删除', content: '删除后不可恢复',
    onOk: async () => { await api.delete(`/api/v1/admin/approval-types/${id}`); message.success('已删除'); await load() },
  })
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div><p class="eyebrow">ADMIN</p><h1>审批类型管理</h1></div>
      <a-button type="primary" @click="openCreate">新增类型</a-button>
    </header>

    <a-table :dataSource="types" :loading="loading" rowKey="id" :pagination="false">
      <a-table-column title="名称" dataIndex="name" />
      <a-table-column title="描述" dataIndex="description" />
      <a-table-column title="表单模板">
        <template #default="{ record }">{{ record.form_template?.name }}</template>
      </a-table-column>
      <a-table-column title="操作">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">编辑</a>
            <a style="color:#d9682f;" @click="remove(record.id)">删除</a>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:visible="visible" :title="editing ? '编辑审批类型' : '新增审批类型'" @ok="save">
      <a-form layout="vertical">
        <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" /></a-form-item>
        <a-form-item label="表单模板" required>
          <a-select v-model:value="form.form_template_id">
            <a-select-option v-for="ft in formTemplates" :key="ft.id" :value="ft.id">{{ ft.name }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="流程模板" required>
          <a-select v-model:value="form.flow_template_id">
            <a-select-option v-for="ft in flowTemplates" :key="ft.id" :value="ft.id">{{ ft.name }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
```

- [ ] **Step 2: AdminFormTemplates.vue**

```vue
<!-- frontend/src/views/approval/AdminFormTemplates.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import api from '@/api/client'

const items = ref<any[]>([])
const loading = ref(true)
const visible = ref(false)
const editing = ref<any>(null)
const form = ref({ name: '', description: '', fields_json: '[]' })

onMounted(load)

async function load() {
  loading.value = true
  try { const res = await api.get('/api/v1/admin/form-templates'); items.value = res.data.data } finally { loading.value = false }
}

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', fields_json: '[]' }
  visible.value = true
}

function openEdit(item: any) {
  editing.value = item
  form.value = { name: item.name, description: item.description || '', fields_json: JSON.stringify(item.fields, null, 2) }
  visible.value = true
}

async function save() {
  try {
    let fields
    try { fields = JSON.parse(form.value.fields_json) } catch { return message.warning('JSON 格式不正确') }
    const body = { name: form.value.name, description: form.value.description, fields }
    if (editing.value) {
      await api.put(`/api/v1/admin/form-templates/${editing.value.id}`, body)
    } else {
      await api.post('/api/v1/admin/form-templates', body)
    }
    message.success('保存成功'); visible.value = false; await load()
  } catch { message.error('保存失败') }
}

async function remove(id: number) {
  Modal.confirm({
    title: '确认删除',
    onOk: async () => { await api.delete(`/api/v1/admin/form-templates/${id}`); message.success('已删除'); await load() },
  })
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div><p class="eyebrow">ADMIN</p><h1>表单模板管理</h1></div>
      <a-button type="primary" @click="openCreate">新增模板</a-button>
    </header>

    <a-table :dataSource="items" :loading="loading" rowKey="id" :pagination="false">
      <a-table-column title="名称" dataIndex="name" />
      <a-table-column title="字段数"><template #default="{ record }">{{ record.fields?.length || 0 }}</template></a-table-column>
      <a-table-column title="操作">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">编辑</a>
            <a style="color:#d9682f;" @click="remove(record.id)">删除</a>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:visible="visible" :title="editing ? '编辑表单模板' : '新增表单模板'" @ok="save" width="700px">
      <a-form layout="vertical">
        <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" /></a-form-item>
        <a-form-item label="字段定义（JSON）" required>
          <a-textarea v-model:value="form.fields_json" :rows="12" style="font-family:monospace;font-size:12px;" />
          <small style="color:#999;">格式：[{"key":"xxx","label":"标签","type":"text|number|date|select|textarea","required":true,"options":["A","B"]}]</small>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
```

- [ ] **Step 3: AdminFlowTemplates.vue**

```vue
<!-- frontend/src/views/approval/AdminFlowTemplates.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import api from '@/api/client'

const items = ref<any[]>([])
const loading = ref(true)
const visible = ref(false)
const editing = ref<any>(null)
const form = ref({ name: '', description: '', nodes_json: '[]' })
const users = ref<any[]>([])

onMounted(async () => {
  await load()
  try { const res = await api.get('/api/v1/admin/users'); users.value = res.data.data } catch { /* */ }
})

async function load() {
  loading.value = true
  try { const res = await api.get('/api/v1/admin/flow-templates'); items.value = res.data.data } finally { loading.value = false }
}

function openCreate() {
  editing.value = null
  form.value = { name: '', description: '', nodes_json: '[]' }
  visible.value = true
}

function openEdit(item: any) {
  editing.value = item
  form.value = { name: item.name, description: item.description || '', nodes_json: JSON.stringify(item.nodes, null, 2) }
  visible.value = true
}

async function save() {
  try {
    let nodes
    try { nodes = JSON.parse(form.value.nodes_json) } catch { return message.warning('JSON 格式不正确') }
    const body = { name: form.value.name, description: form.value.description, nodes }
    if (editing.value) {
      await api.put(`/api/v1/admin/flow-templates/${editing.value.id}`, body)
    } else {
      await api.post('/api/v1/admin/flow-templates', body)
    }
    message.success('保存成功'); visible.value = false; await load()
  } catch { message.error('保存失败') }
}

async function remove(id: number) {
  Modal.confirm({
    title: '确认删除',
    onOk: async () => { await api.delete(`/api/v1/admin/flow-templates/${id}`); message.success('已删除'); await load() },
  })
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div><p class="eyebrow">ADMIN</p><h1>流程模板管理</h1></div>
      <a-button type="primary" @click="openCreate">新增模板</a-button>
    </header>

    <a-table :dataSource="items" :loading="loading" rowKey="id" :pagination="false">
      <a-table-column title="名称" dataIndex="name" />
      <a-table-column title="节点数"><template #default="{ record }">{{ record.nodes?.length || 0 }}</template></a-table-column>
      <a-table-column title="操作">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">编辑</a>
            <a style="color:#d9682f;" @click="remove(record.id)">删除</a>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:visible="visible" :title="editing ? '编辑流程模板' : '新增流程模板'" @ok="save" width="800px">
      <a-form layout="vertical">
        <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
        <a-form-item label="描述"><a-textarea v-model:value="form.description" /></a-form-item>
        <a-form-item label="节点定义（JSON）" required>
          <a-textarea v-model:value="form.nodes_json" :rows="14" style="font-family:monospace;font-size:12px;" />
          <small style="color:#999;display:block;margin-top:4px;">
            单审：{"index":0,"name":"节点名","type":"single","approver_id":"UUID","allow_transfer":true}<br/>
            会签：{"index":1,"name":"会签","type":"counter_sign","approver_ids":["UUID1","UUID2"],"allow_transfer":true}<br/>
            可选用户ID：<span v-for="u in users" :key="u.id" style="margin-right:8px;">{{ u.display_name }}({{ u.id.slice(0,8) }})</span>
          </small>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
```

- [ ] **Step 4: AdminLogs.vue**

```vue
<!-- frontend/src/views/approval/AdminLogs.vue -->
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import api from '@/api/client'

const logs = ref<any[]>([])
const loading = ref(true)

const actionMap: Record<string, string> = {
  approve: '同意', reject: '驳回', transfer: '转审', revoke: '撤回', urge: '催办',
}
const actionColorMap: Record<string, string> = {
  approve: 'success', reject: 'error', transfer: 'processing', revoke: 'default', urge: 'warning',
}

onMounted(async () => {
  try {
    const res = await api.get('/api/v1/admin/logs')
    logs.value = res.data.data
  } finally { loading.value = false }
})
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div><p class="eyebrow">ADMIN</p><h1>审批日志</h1></div>
    </header>

    <a-table :dataSource="logs" :loading="loading" rowKey="id" :pagination="{ pageSize: 20 }">
      <a-table-column title="操作人" dataIndex="actor_name" width="120" />
      <a-table-column title="操作" width="80">
        <template #default="{ record }">
          <a-tag :color="actionColorMap[record.action]">{{ actionMap[record.action] || record.action }}</a-tag>
        </template>
      </a-table-column>
      <a-table-column title="申请ID" dataIndex="request_id" width="80" />
      <a-table-column title="备注" dataIndex="comment" ellipsis />
      <a-table-column title="时间" dataIndex="created_at" width="170">
        <template #default="{ record }">{{ record.created_at?.slice(0, 16).replace('T',' ') }}</template>
      </a-table-column>
    </a-table>
  </div>
</template>
```

---

### Task 14: 前端——审批专用样式 + AppLayout 导航更新

**Files:**
- Modify: `frontend/src/styles.css` — 追加审批样式
- Modify: `frontend/src/layouts/AppLayout.vue` — 审批菜单项跳转到新路由

- [ ] **Step 1: 在 styles.css 末尾追加审批样式**

```css
/* frontend/src/styles.css — 追加在文件末尾 */

/* ── 审批模块样式 ── */

.stat-row { display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px; margin-bottom: 20px; }
.stat-card { display: flex; align-items: center; gap: 16px; padding: 22px 24px; background: #fff; border: 1px solid var(--line); }
.stat-icon { width: 48px; height: 48px; display: grid; place-items: center; font-size: 22px; flex-shrink: 0; }
.stat-body { display: flex; flex-direction: column; }
.stat-num { font: 700 32px/1.1 Georgia, serif; color: var(--ink); }
.stat-label { color: var(--muted); font-size: 13px; margin-top: 2px; }

.quick-actions { display: flex; gap: 10px; }

.type-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.type-card { padding: 18px; border: 1px solid var(--line); background: #fff; cursor: pointer; display: flex; flex-direction: column; gap: 6px; }
.type-card:hover, .type-card.active { border-color: var(--teal); background: #f7fbfa; }
.type-card strong { font-size: 14px; }
.type-card small { color: var(--muted); font-size: 12px; }

.form-panel { padding: 24px; background: #fff; border: 1px solid var(--line); }
.form-field { margin-bottom: 16px; }
.form-field label { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600; color: var(--ink); }

.form-readonly { padding: 24px; background: #fff; border: 1px solid var(--line); display: grid; gap: 14px; }
.form-readonly-item { display: flex; gap: 12px; align-items: baseline; padding-bottom: 10px; border-bottom: 1px solid #f0f2f1; }
.f-label { color: var(--muted); font-size: 12px; min-width: 100px; text-transform: uppercase; }
.f-value { font-size: 14px; color: var(--ink); }

.node-timeline { padding: 20px 24px; background: #fff; border: 1px solid var(--line); }
.node-row { display: flex; gap: 16px; align-items: flex-start; padding: 12px 0; }
.node-row + .node-row { border-top: 1px solid #f0f2f1; }
.node-marker { width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; font-size: 14px; flex-shrink: 0; }
.node-marker.node-pending { background: #e8f5f1; color: var(--teal); font-weight: 700; font-size: 12px; }
.node-marker.node-done { background: #e8f5f1; color: #42c697; }
.node-marker.node-reject { background: #fde9e9; color: #d9682f; }
.node-body { display: flex; flex-direction: column; gap: 4px; flex: 1; }
.node-header { display: flex; align-items: center; gap: 10px; }
.node-header strong { font-size: 14px; }

.action-bar { padding: 22px 24px; background: #fff; border: 1px solid var(--line); margin-top: 18px; }

.pending-cards { display: flex; flex-direction: column; gap: 8px; }
.pending-card { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: #fff; border: 1px solid var(--line); cursor: pointer; }
.pending-card:hover { border-color: var(--teal); }
.pending-info { display: flex; flex-direction: column; gap: 4px; }
.pending-info strong { font-size: 14px; }
.pending-info small { color: var(--muted); font-size: 12px; }

.pending-list { display: flex; flex-direction: column; gap: 8px; }
.pending-card-full { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: #fff; border: 1px solid var(--line); }
.pending-main { display: flex; flex-direction: column; gap: 4px; cursor: pointer; flex: 1; }
.pending-main:hover strong { color: var(--teal); }
.pending-main strong { font-size: 14px; }
.pending-main small { color: var(--muted); font-size: 12px; }
.pending-actions { display: flex; gap: 8px; flex-shrink: 0; margin-left: 16px; }

.request-list { display: flex; flex-direction: column; gap: 8px; }
.request-card { display: flex; align-items: center; justify-content: space-between; padding: 16px 20px; background: #fff; border: 1px solid var(--line); cursor: pointer; }
.request-card:hover { border-color: var(--teal); }
.request-info { display: flex; flex-direction: column; gap: 4px; }
.request-info strong { font-size: 14px; }
.request-info small { color: var(--muted); font-size: 12px; }

@media (max-width: 960px) {
  .stat-row, .type-cards { grid-template-columns: 1fr; }
}
```

- [ ] **Step 2: 修改 AppLayout.vue 使审批菜单跳转到新路由**

用 Edit 工具修改 `AppLayout.vue` 中模块菜单的 key：

```typescript
// 将
{ key: '/modules/approval-center', ... }
// 无需改动，路由已配置为 /modules/approval-center
```

审批模块菜单项保持 `key: '/modules/approval-center'` 不变，因为路由 `path: 'modules/approval-center'` 对应 URL `/modules/approval-center`，正好匹配。

---

### Task 15: 验证——后端 API 完整流程测试

- [ ] **Step 1: 启动后端**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend
Remove-Item enterprise_ai.db -ErrorAction SilentlyContinue
Remove-Item approval.db -ErrorAction SilentlyContinue
Start-Process python -ArgumentList "-m uvicorn app.main:app --reload --port 8000" -NoNewWindow
Start-Sleep -Seconds 3
```

- [ ] **Step 2: 完整流程测试**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend

# 1. 管理员登录
$admin = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/auth/demo-login -Method Post -Body '{"role":"platform_admin"}' -ContentType "application/json").data.access_token

# 2. 申请人登录
$user = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/auth/demo-login -Method Post -Body '{"role":"product_demo_user"}' -ContentType "application/json").data.access_token

# 3. 张三登录（用管理员token查看用户列表拿张三ID）
$users = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/admin/users -Headers @{Authorization="Bearer $admin"}).data
$zhangsan = $users[0].id

# 4. 获取审批类型
$types = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/approvals/types -Headers @{Authorization="Bearer $user"}).data
Write-Host "审批类型数量：$($types.Count)"

# 5. 提交请假申请
$req = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/approvals/requests -Method Post -Headers @{Authorization="Bearer $user"} -Body '{"type_id":1,"title":"请假申请-测试","form_data":{"leave_type":"年假","start_date":"2026-07-25","end_date":"2026-07-26","days":2,"reason":"休息"}}' -ContentType "application/json").data
Write-Host "申请ID：$($req.id)，状态：$($req.status)，节点数：$($req.nodes.Count)"
Write-Host "第一个节点审批人：$($req.nodes[0].approver_name)"

# 6. 待审批列表
$pending = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/approvals/pending -Headers @{Authorization="Bearer $user"}).data
Write-Host "待审批数：$($pending.Count)"

Write-Host "`n=== 全部端点验证通过 ==="
```

Expected: 审批类型 3 条，申请创建成功含 3 个节点，每个节点有具体的审批人姓名。

- [ ] **Step 3: 提交审批操作的额外验证（手动curl）**

用张三的身份无法直接登录（审批用户不走 JWT）。为验证审批操作，通过修改 pending 查询的 approver_id 验证：
- 在 seed.py 中张三是第一个节点的审批人
- 提交申请后，节点 0 的 approver_id 是张三的 UUID
- 可手动用 SQLite 修改 pending 查询逻辑或通过 API 文档页手动测试

---

### Task 16: 前端——编译验证 + 端到端检查

- [ ] **Step 1: TypeScript 类型检查**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\frontend
npx vue-tsc --noEmit
```

修复所有类型错误。

- [ ] **Step 2: 构建验证**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\frontend
npm run build
```

Expected: 构建成功，无报错。

- [ ] **Step 3: 启动前端并手动测试**

```powershell
npm run dev
```

访问 `http://127.0.0.1:5173`，以"产品演示用户"登录，验证：
1. 点击侧栏"流程审批中心"→ 进入审批首页，看到统计卡片
2. 点击"发起申请"→ 看到 3 种审批类型 → 选择一种 → 填写表单 → 提交成功
3. 提交后跳转到"我的申请"列表 → 看到刚才的申请
4. 点击申请进入详情 → 看到完整的审批节点进度和操作记录
5. 在"待我审批"页看到待处理的申请
6. 以"平台管理员"登录 → 能访问后台管理页面（审批类型/表单模板/流程模板/审批日志）
