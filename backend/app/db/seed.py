import uuid
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

from sqlalchemy import delete, inspect, select, text

from app.business.models import (
    Asset,
    AssetException,
    InventoryTask,
    JobOpening,
    ScreeningJob,
    ServiceTicket,
    ServiceTicketEvent,
)
from app.core.config import settings
from app.core.security import hash_password
from app.db.database import Base, SessionLocal, engine
from app.db.models import AIRun, AuditLog, Notification, User

DEMO_PASSWORD = "Demo@2026!"

ROLE_PERMISSIONS = {
    "platform_admin": [
        "dashboard:view",
        "resume:view",
        "resume:manage",
        "recruitment:manage",
        "approval:view",
        "asset:view",
        "asset:manage",
        "inventory:manage",
        "inventory:self_check",
        "service_desk:view",
        "service_desk:handle",
        "service_desk:manage",
        "notification:view",
        "audit:view",
        "ai_run:view",
        "platform:manage",
        "approval:manage",
    ],
    "recruitment_admin": [
        "dashboard:view",
        "resume:view",
        "resume:manage",
        "recruitment:manage",
        "notification:view",
        "ai_run:view",
    ],
    "asset_admin": [
        "dashboard:view",
        "asset:view",
        "asset:manage",
        "inventory:manage",
        "inventory:self_check",
        "notification:view",
        "ai_run:view",
    ],
    "it_support": [
        "dashboard:view",
        "asset:view",
        "service_desk:view",
        "service_desk:handle",
        "notification:view",
    ],
    "department_manager": [
        "dashboard:view",
        "resume:view",
        "approval:view",
        "asset:view",
        "service_desk:view",
        "notification:view",
        "approval:review",
        "inventory:review",
    ],
    "approval_finance": [
        "dashboard:view",
        "approval:view",
        "asset:view",
        "notification:view",
        "approval:finance",
        "inventory:review",
    ],
    "employee": [
        "dashboard:view",
        "approval:view",
        "asset:view",
        "service_desk:view",
        "notification:view",
        "inventory:self_check",
    ],
}

DEMO_USERS = [
    {
        "id": "11111111-1111-1111-1111-111111111111",
        "email": "admin@demo.local",
        "display_name": "平台管理员",
        "department": "企业数字化中心",
        "role": "platform_admin",
    },
    {
        "id": "12111111-1111-1111-1111-111111111111",
        "email": "owner@demo.local",
        "display_name": "平台负责人",
        "department": "企业数字化中心",
        "role": "platform_admin",
    },
    {
        "id": "23111111-1111-1111-1111-111111111111",
        "email": "recruit01@demo.local",
        "display_name": "招聘负责人",
        "department": "人才发展部",
        "role": "recruitment_admin",
    },
    {
        "id": "23222222-2222-2222-2222-222222222222",
        "email": "recruit02@demo.local",
        "display_name": "校招运营",
        "department": "人才发展部",
        "role": "recruitment_admin",
    },
    {
        "id": "23333333-3333-3333-3333-333333333333",
        "email": "recruit03@demo.local",
        "display_name": "用人协同HR",
        "department": "人力资源部",
        "role": "recruitment_admin",
    },
    {
        "id": "34111111-1111-1111-1111-111111111111",
        "email": "asset01@demo.local",
        "display_name": "资产管理员A",
        "department": "行政资产组",
        "role": "asset_admin",
    },
    {
        "id": "34222222-2222-2222-2222-222222222222",
        "email": "asset02@demo.local",
        "display_name": "区域资产专员",
        "department": "深圳行政资产组",
        "role": "asset_admin",
    },
    {
        "id": "34333333-3333-3333-3333-333333333333",
        "email": "asset03@demo.local",
        "display_name": "IT资产专员",
        "department": "信息技术部",
        "role": "asset_admin",
    },
    {
        "id": "77111111-1111-1111-1111-111111111111",
        "email": "it01@demo.local",
        "display_name": "IT运维工程师",
        "department": "信息技术部",
        "role": "it_support",
    },
    {
        "id": "77222222-2222-2222-2222-222222222222",
        "email": "it02@demo.local",
        "display_name": "IT桌面支持",
        "department": "信息技术部",
        "role": "it_support",
    },
    {
        "id": "22222222-2222-2222-2222-222222222222",
        "email": "manager01@demo.local",
        "display_name": "产品研发经理",
        "department": "产品与流程创新",
        "role": "department_manager",
    },
    {
        "id": "44222222-2222-2222-2222-222222222222",
        "email": "manager02@demo.local",
        "display_name": "数据平台经理",
        "department": "数据平台组",
        "role": "department_manager",
    },
    {
        "id": "44333333-3333-3333-3333-333333333333",
        "email": "manager03@demo.local",
        "display_name": "质量检测经理",
        "department": "质量检测部",
        "role": "department_manager",
    },
    {
        "id": "44444444-4444-4444-4444-444444444444",
        "email": "manager04@demo.local",
        "display_name": "流程创新经理",
        "department": "流程创新中心",
        "role": "department_manager",
    },
    {
        "id": "55111111-1111-1111-1111-111111111111",
        "email": "finance01@demo.local",
        "display_name": "财务审批A",
        "department": "财务管理部",
        "role": "approval_finance",
    },
    {
        "id": "55222222-2222-2222-2222-222222222222",
        "email": "finance02@demo.local",
        "display_name": "财务审批B",
        "department": "财务管理部",
        "role": "approval_finance",
    },
    {
        "id": "55333333-3333-3333-3333-333333333333",
        "email": "finance03@demo.local",
        "display_name": "区域财务",
        "department": "区域财务组",
        "role": "approval_finance",
    },
    {
        "id": "66111111-1111-1111-1111-111111111111",
        "email": "employee01@demo.local",
        "display_name": "员工一",
        "department": "产品研发部",
        "role": "employee",
    },
    {
        "id": "66222222-2222-2222-2222-222222222222",
        "email": "employee02@demo.local",
        "display_name": "员工二",
        "department": "数据平台组",
        "role": "employee",
    },
    {
        "id": "66333333-3333-3333-3333-333333333333",
        "email": "employee03@demo.local",
        "display_name": "员工三",
        "department": "质量检测部",
        "role": "employee",
    },
    {
        "id": "66444444-4444-4444-4444-444444444444",
        "email": "employee04@demo.local",
        "display_name": "员工四",
        "department": "行政资产组",
        "role": "employee",
    },
    {
        "id": "66555555-5555-5555-5555-555555555555",
        "email": "employee05@demo.local",
        "display_name": "员工五",
        "department": "流程创新中心",
        "role": "employee",
    },
]


def ensure_user_schema() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("users")}
    if "password_hash" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))


def ensure_asset_schema() -> None:
    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    asset_columns = (
        {column["name"] for column in inspector.get_columns("assets")}
        if "assets" in table_names
        else set()
    )
    with engine.begin() as connection:
        if asset_columns and "asset_uuid" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN asset_uuid VARCHAR(36)"))
        if asset_columns and "qr_secret" not in asset_columns:
            connection.execute(text("ALTER TABLE assets ADD COLUMN qr_secret VARCHAR(128)"))
        record_columns = (
            {column["name"] for column in inspector.get_columns("inventory_records")}
            if "inventory_records" in table_names
            else set()
        )
        if record_columns and "photo_url" not in record_columns:
            connection.execute(text("ALTER TABLE inventory_records ADD COLUMN photo_url TEXT"))


def ensure_recruitment_schema() -> None:
    inspector = inspect(engine)
    if "candidate_applications" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("candidate_applications")}
    with engine.begin() as connection:
        if "ai_status" not in columns:
            connection.execute(text("ALTER TABLE candidate_applications ADD COLUMN ai_status VARCHAR(30) DEFAULT '未筛选'"))
        if "ai_score" not in columns:
            connection.execute(text("ALTER TABLE candidate_applications ADD COLUMN ai_score FLOAT"))
        if "ai_summary" not in columns:
            connection.execute(text("ALTER TABLE candidate_applications ADD COLUMN ai_summary TEXT"))
        if "ai_evidence" not in columns:
            connection.execute(text("ALTER TABLE candidate_applications ADD COLUMN ai_evidence JSON"))


def ensure_service_desk_schema() -> None:
    inspector = inspect(engine)
    if "service_tickets" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("service_tickets")}
    with engine.begin() as connection:
        if "asset_id" not in columns:
            connection.execute(text("ALTER TABLE service_tickets ADD COLUMN asset_id INTEGER REFERENCES assets(id)"))


def seed_service_tickets(db) -> None:
    now = datetime.now(UTC)
    engineer = next(item for item in DEMO_USERS if item["email"] == "it01@demo.local")
    laptop = db.scalar(select(Asset).where(Asset.asset_code == "BYD-LAP-2026-001"))
    samples = [
        (DEMO_USERS[-5], "VPN 连接后无法访问内网 Git", "居家办公连上 VPN 后，git.internal 一直超时，浏览器能打开公司门户。", "网络连接", "高", "待受理", None, None, None, None),
        (DEMO_USERS[-4], "申请 Tableau 只读账号", "需要查看数据平台组的周报看板，请开通 Tableau 只读权限。", "账号权限", "中", "处理中", engineer, None, None, None),
        (DEMO_USERS[-3], "工位显示器闪屏", "左侧显示器每隔几分钟黑屏一次，已更换过线缆。", "硬件设备", "低", "已解决", engineer, "已更换为备用显示器，原设备送修。", None, None),
        (DEMO_USERS[-2], "研发笔记本频繁蓝屏", "这周已经蓝屏三次，错误代码不记得了，多发生在开会投屏时。", "硬件设备", "高", "待补充", engineer, None, laptop, "请在蓝屏后拍一下错误代码，或者告诉我投屏用的是哪个转接头。"),
    ]
    for index, (requester, title, description, category, priority, status, assignee, resolution, asset, question) in enumerate(samples, start=1):
        created_at = now - timedelta(hours=6 * index)
        ticket = ServiceTicket(
            ticket_no=f"IT-SEED-{index:04d}",
            title=title,
            description=description,
            category=category,
            priority=priority,
            status=status,
            requester_id=requester["id"],
            requester_name=requester["display_name"],
            department=requester["department"],
            assignee_id=assignee["id"] if assignee else None,
            assignee_name=assignee["display_name"] if assignee else None,
            asset_id=asset.id if asset else None,
            resolution=resolution,
            due_at=created_at + timedelta(hours={"紧急": 4, "高": 8, "中": 24, "低": 72}[priority]),
            resolved_at=now - timedelta(hours=1) if status == "已解决" else None,
            created_at=created_at,
        )
        db.add(ticket)
        db.flush()
        db.add(ServiceTicketEvent(ticket_id=ticket.id, kind="status", actor_id=requester["id"], actor_name=requester["display_name"], content=f"提交工单（{category} / {priority}优先级）", created_at=created_at))
        if assignee:
            db.add(ServiceTicketEvent(ticket_id=ticket.id, kind="status", actor_id=assignee["id"], actor_name=assignee["display_name"], content=f"{assignee['display_name']} 已受理", created_at=created_at + timedelta(minutes=30)))
        if question:
            db.add(ServiceTicketEvent(ticket_id=ticket.id, kind="status", actor_id=assignee["id"], actor_name=assignee["display_name"], content=f"请求补充信息：{question}", created_at=created_at + timedelta(hours=1)))
        if resolution:
            db.add(ServiceTicketEvent(ticket_id=ticket.id, kind="status", actor_id=assignee["id"], actor_name=assignee["display_name"], content=f"标记已解决：{resolution}", created_at=now - timedelta(hours=1)))


def initialize_screening_schema() -> None:
    Base.metadata.create_all(bind=engine)


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_user_schema()
    ensure_asset_schema()
    ensure_recruitment_schema()
    ensure_service_desk_schema()
    with SessionLocal() as db:
        db.execute(delete(User).where(User.role == "auditor"))
        db.commit()
        demo_password_hash = hash_password(DEMO_PASSWORD)
        demo_user_ids = [item["id"] for item in DEMO_USERS]
        existing_users = {
            user.id: user
            for user in db.scalars(select(User).where(User.id.in_(demo_user_ids))).all()
        }
        for item in DEMO_USERS:
            user = existing_users.get(item["id"])
            payload = {
                **item,
                "permissions": ROLE_PERMISSIONS[item["role"]],
                "password_hash": demo_password_hash,
            }
            if user is None:
                db.add(User(**payload))
            else:
                for key, value in payload.items():
                    setattr(user, key, value)
        db.flush()
        users = list(db.scalars(select(User).order_by(User.created_at)).all())
        if not db.scalar(select(Notification.id).limit(1)):
            db.add_all(
                [
                    Notification(user_id=users[0].id, title="平台基础架构已就绪", content="四个业务模块入口已经建立，可以开始逐个迭代。", category="delivery"),
                    Notification(user_id=users[0].id, title="需要配置Supabase", content="当前使用本地SQLite。准备云端联调时再填写Supabase环境变量。", category="configuration"),
                    AuditLog(actor_id=None, actor_name="System", action="foundation_initialized", resource="platform", request_id=str(uuid.uuid4()), detail={"database": "local", "modules": 4}),
                    AIRun(module="platform", task_type="provider_check", status="disabled", human_review=True),
                ]
            )
        elif settings.database_mode == "postgresql":
            stale_notice = db.scalar(
                select(Notification).where(Notification.title == "需要配置Supabase")
            )
            if stale_notice is not None:
                stale_notice.content = (
                    "业务数据库已连接PostgreSQL；登录使用本地邮箱密码，简历和盘点照片可写入Supabase Storage。"
                )

        if not db.scalar(select(Asset.id).limit(1)):
            assets = [
                Asset(asset_code="BYD-LAP-2026-001", name="研发笔记本电脑", category="办公设备", department="智能化研发试制部", owner="王明", location="深圳", status="在用", value=9800),
                Asset(asset_code="BYD-SRV-2026-014", name="测试服务器", category="IT设备", department="数据平台组", owner="李洁", location="深圳", status="在用", value=68000),
                Asset(asset_code="BYD-CAM-2026-033", name="工业相机", category="生产工具", department="质量检测部", owner="周强", location="西安", status="维修中", value=43000),
                Asset(asset_code="BYD-DESK-2025-109", name="升降办公桌", category="办公家具", department="行政资产组", owner="行政公用", location="西安", status="闲置", value=2400),
            ]
            db.add_all(assets); db.flush()
            db.add_all([
                InventoryTask(name="深圳办公与研发资产", scope="深圳办公与研发资产", owner="资产管理员", status="进行中", total_count=1280, checked_count=1096, exception_count=18),
                InventoryTask(name="西安生产与办公资产", scope="西安生产与办公资产", owner="区域资产专员", status="草稿", total_count=860, checked_count=702, exception_count=11),
                AssetException(asset_id=assets[2].id, type="盘亏待核实", description="需要核对借用记录和维修记录", status="待核实"),
            ])
        for asset in db.scalars(select(Asset)).all():
            if not asset.asset_uuid:
                asset.asset_uuid = str(uuid.uuid4())
            if not asset.qr_secret:
                asset.qr_secret = token_urlsafe(24)

        if not db.scalar(select(JobOpening.id).limit(1)):
            db.add_all([
                JobOpening(title="AI产品经理实习生", department="企业AI应用部", location="Singapore", employment_type="实习", description="参与企业AI工作流产品的需求、原型和上线迭代。", requirements="理解B端业务流程，熟悉SQL、Python或AI应用原型。", status="开放"),
                JobOpening(title="数据产品实习生", department="数据平台组", location="Kuala Lumpur", employment_type="实习", description="支持数据指标、看板和业务分析产品。", requirements="熟悉SQL和数据分析，能整理需求并配合开发。", status="开放"),
                JobOpening(title="数字化转型产品助理", department="流程创新中心", location="Singapore", employment_type="实习", description="支持企业流程梳理和数字化项目交付。", requirements="了解审批、资产或工单系统，具备良好沟通能力。", status="暂停"),
            ])
        if not db.scalar(select(ScreeningJob.id).limit(1)):
            db.add(
                ScreeningJob(
                    name="示例岗位标准（停用）",
                    description="本示例仅用于本地验收，启用前请替换为真实岗位标准。",
                    required_skills=["待配置"],
                    preferred_skills=[],
                    rejection_conditions=[],
                    scoring_weights={"required_skills": 0.7, "preferred_skills": 0.3},
                    status="inactive",
                )
            )
        if not db.scalar(select(ServiceTicket.id).limit(1)):
            seed_service_tickets(db)
        active_tasks = db.scalars(
            select(InventoryTask)
            .where(InventoryTask.status == "进行中")
            .order_by(InventoryTask.created_at.desc(), InventoryTask.id.desc())
        ).all()
        for stale_task in active_tasks[1:]:
            stale_task.status = "已结束"
            stale_task.updated_at = datetime.now(UTC)
        db.commit()
