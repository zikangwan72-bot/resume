from sqlalchemy import select

from app.approval.database import ApprovalBase, ApprovalSessionLocal, approval_engine
from app.approval.models import (
    ApprovalType,
    ApprovalUser,
    FlowTemplate,
    FormTemplate,
    ProcessApp,
    ProcessVersion,
)

APPROVAL_USERS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "admin@demo.local",
        "display_name": "平台管理员",
        "department": "企业数字化中心",
        "position": "平台管理员",
        "role": "platform_admin",
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "email": "product@demo.local",
        "display_name": "产品演示用户",
        "department": "产品与流程创新",
        "position": "产品经理",
        "role": "department_manager",
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "email": "zhangsan@demo.local",
        "display_name": "张三",
        "department": "产品研发部",
        "position": "产品经理",
        "role": "department_manager",
    },
    {
        "id": "55555555-5555-5555-5555-555555555555",
        "email": "lisi@demo.local",
        "display_name": "李四",
        "department": "产品研发部",
        "position": "分管领导",
        "role": "division_leader",
    },
    {
        "id": "66666666-6666-6666-6666-666666666666",
        "email": "wangwu@demo.local",
        "display_name": "王五",
        "department": "人力资源部",
        "position": "人力资源专员",
        "role": "hr",
    },
    {
        "id": "77777777-7777-7777-7777-777777777777",
        "email": "zhaoliu@demo.local",
        "display_name": "赵六",
        "department": "财务管理部",
        "position": "财务专员",
        "role": "finance",
    },
    {
        "id": "88888888-8888-8888-8888-888888888888",
        "email": "sunqi@demo.local",
        "display_name": "孙七",
        "department": "产品研发部",
        "position": "副总裁",
        "role": "vp",
    },
]

LEAVE_FORM_FIELDS = [
    {
        "key": "leave_type",
        "label": "请假类型",
        "type": "select",
        "required": True,
        "options": ["事假", "病假", "年假", "调休", "婚假"],
    },
    {"key": "start_date", "label": "开始日期", "type": "date", "required": True},
    {"key": "end_date", "label": "结束日期", "type": "date", "required": True},
    {"key": "days", "label": "天数", "type": "number", "required": True},
    {"key": "reason", "label": "请假事由", "type": "textarea", "required": True},
]

EXPENSE_FORM_FIELDS = [
    {
        "key": "expense_type",
        "label": "报销类别",
        "type": "select",
        "required": True,
        "options": ["差旅费", "办公用品", "招待费", "交通费", "其他"],
    },
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

# 请假流程第一个节点用产品演示用户(2222...)，确保demo可走通
LEAVE_FLOW_NODES = [
    {
        "index": 0,
        "name": "部门经理审批",
        "type": "single",
        "approver_id": "22222222-2222-2222-2222-222222222222",
        "allow_transfer": True,
    },
    {
        "index": 1,
        "name": "分管领导审批",
        "type": "single",
        "approver_id": "55555555-5555-5555-5555-555555555555",
        "allow_transfer": True,
    },
    {
        "index": 2,
        "name": "HR确认",
        "type": "single",
        "approver_id": "66666666-6666-6666-6666-666666666666",
        "allow_transfer": False,
    },
]

EXPENSE_FLOW_NODES = [
    {
        "index": 0,
        "name": "部门经理审批",
        "type": "single",
        "approver_id": "22222222-2222-2222-2222-222222222222",
        "allow_transfer": True,
    },
    {
        "index": 1,
        "name": "分管领导审批",
        "type": "single",
        "approver_id": "55555555-5555-5555-5555-555555555555",
        "allow_transfer": True,
    },
    {
        "index": 2,
        "name": "财务审批",
        "type": "single",
        "approver_id": "77777777-7777-7777-7777-777777777777",
        "allow_transfer": False,
    },
]

PURCHASE_FLOW_NODES = [
    {
        "index": 0,
        "name": "部门经理审批",
        "type": "single",
        "approver_id": "22222222-2222-2222-2222-222222222222",
        "allow_transfer": True,
    },
    {
        "index": 1,
        "name": "领导会签",
        "type": "counter_sign",
        "approver_ids": [
            "55555555-5555-5555-5555-555555555555",
            "88888888-8888-8888-8888-888888888888",
        ],
        "allow_transfer": True,
    },
    {
        "index": 2,
        "name": "财务审批",
        "type": "single",
        "approver_id": "77777777-7777-7777-7777-777777777777",
        "allow_transfer": False,
    },
]


def _form_schema(fields: list[dict]) -> dict:
    return {"fields": [{"id": field["key"], **field} for field in fields]}


def _flow_schema(nodes: list[dict], node_ids: list[str]) -> dict:
    flow_nodes = [{"id": "start", "type": "start", "name": "开始"}]
    flow_nodes.extend(
        {"id": node_id, "type": "approval", **node}
        for node, node_id in zip(nodes, node_ids, strict=True)
    )
    flow_nodes.append({"id": "end", "type": "end", "name": "结束"})
    node_order = [node["id"] for node in flow_nodes]
    return {
        "nodes": flow_nodes,
        "edges": [
            {"source": source, "target": target}
            for source, target in zip(node_order, node_order[1:], strict=False)
        ],
    }


PROCESS_APP_SEEDS = [
    {
        "code": "leave",
        "name": "请假申请",
        "description": "员工请假审批",
        "form_schema": _form_schema(LEAVE_FORM_FIELDS),
        "flow_schema": _flow_schema(LEAVE_FLOW_NODES, ["manager", "director", "hr"]),
    },
    {
        "code": "expense",
        "name": "报销申请",
        "description": "费用报销审批",
        "form_schema": _form_schema(EXPENSE_FORM_FIELDS),
        "flow_schema": _flow_schema(EXPENSE_FLOW_NODES, ["manager", "director", "finance"]),
    },
    {
        "code": "purchase",
        "name": "采购申请",
        "description": "物品采购审批",
        "form_schema": _form_schema(PURCHASE_FORM_FIELDS),
        "flow_schema": _flow_schema(PURCHASE_FLOW_NODES, ["manager", "director", "finance"]),
    },
]


def initialize_approval_db() -> None:
    ApprovalBase.metadata.create_all(bind=approval_engine)
    with ApprovalSessionLocal() as db:
        for u in APPROVAL_USERS:
            existing_user = db.get(ApprovalUser, u["id"])
            if existing_user:
                for key, value in u.items():
                    setattr(existing_user, key, value)
            else:
                db.add(ApprovalUser(**u))
        db.flush()

        if not db.scalar(select(FormTemplate.id).limit(1)):
            leave_form = FormTemplate(
                name="请假表单", description="请假申请表单", fields=LEAVE_FORM_FIELDS
            )
            expense_form = FormTemplate(
                name="报销表单", description="报销申请表单", fields=EXPENSE_FORM_FIELDS
            )
            purchase_form = FormTemplate(
                name="采购表单", description="采购申请表单", fields=PURCHASE_FORM_FIELDS
            )
            db.add_all([leave_form, expense_form, purchase_form])
            db.flush()

            leave_flow = FlowTemplate(
                name="三级审批（HR终审）",
                description="部门经理→分管领导→HR",
                nodes=LEAVE_FLOW_NODES,
            )
            expense_flow = FlowTemplate(
                name="三级审批（财务终审）",
                description="部门经理→分管领导→财务",
                nodes=EXPENSE_FLOW_NODES,
            )
            purchase_flow = FlowTemplate(
                name="会签流程（财务终审）",
                description="部门经理→领导会签→财务",
                nodes=PURCHASE_FLOW_NODES,
            )
            db.add_all([leave_flow, expense_flow, purchase_flow])
            db.flush()

            db.add_all(
                [
                    ApprovalType(
                        name="请假申请",
                        description="员工请假审批",
                        form_template_id=leave_form.id,
                        flow_template_id=leave_flow.id,
                    ),
                    ApprovalType(
                        name="报销申请",
                        description="费用报销审批",
                        form_template_id=expense_form.id,
                        flow_template_id=expense_flow.id,
                    ),
                    ApprovalType(
                        name="采购申请",
                        description="物品采购审批",
                        form_template_id=purchase_form.id,
                        flow_template_id=purchase_flow.id,
                    ),
                ]
            )

        for seed in PROCESS_APP_SEEDS:
            app = db.scalar(select(ProcessApp).where(ProcessApp.code == seed["code"]))
            if app:
                continue

            app = ProcessApp(
                code=seed["code"],
                name=seed["name"],
                description=seed["description"],
                status="published",
            )
            db.add(app)
            db.flush()
            version = ProcessVersion(
                process_app_id=app.id,
                version_number=1,
                status="published",
                form_schema=seed["form_schema"],
                flow_schema=seed["flow_schema"],
                published_at=app.created_at,
            )
            db.add(version)
            db.flush()
            app.current_version_id = version.id

        db.commit()
