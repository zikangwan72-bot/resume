import uuid

from sqlalchemy import delete, select

from app.business.models import Asset, AssetException, InventoryTask, JobOpening
from app.db.database import Base, SessionLocal, engine
from app.db.models import AIRun, AuditLog, Notification, User

ROLE_PERMISSIONS = {
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
        "approval:manage",
    ],
    "product_demo_user": [
        "dashboard:view",
        "resume:view",
        "approval:view",
        "asset:view",
        "service_desk:view",
        "notification:view",
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
        "id": "22222222-2222-2222-2222-222222222222",
        "email": "product@demo.local",
        "display_name": "产品演示用户",
        "department": "产品与流程创新",
        "role": "product_demo_user",
    },
]


def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        db.execute(delete(User).where(User.role == "auditor"))
        db.commit()
        users = list(db.scalars(select(User).order_by(User.created_at)).all())
        if not users:
            for item in DEMO_USERS:
                user = User(**item, permissions=ROLE_PERMISSIONS[item["role"]])
                db.add(user)
                users.append(user)
            db.flush()
            db.add_all(
                [
                    Notification(user_id=users[0].id, title="平台基础架构已就绪", content="四个业务模块入口已经建立，可以开始逐个迭代。", category="delivery"),
                    Notification(user_id=users[0].id, title="需要配置Supabase", content="当前使用本地SQLite。准备云端联调时再填写Supabase环境变量。", category="configuration"),
                    AuditLog(actor_id=None, actor_name="System", action="foundation_initialized", resource="platform", request_id=str(uuid.uuid4()), detail={"database": "local", "modules": 4}),
                    AIRun(module="platform", task_type="provider_check", status="disabled", human_review=True),
                ]
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
                InventoryTask(name="西安生产与办公资产", scope="西安生产与办公资产", owner="区域资产专员", status="进行中", total_count=860, checked_count=702, exception_count=11),
                AssetException(asset_id=assets[2].id, type="盘亏待核实", description="需要核对借用记录和维修记录", status="待核实"),
            ])

        if not db.scalar(select(JobOpening.id).limit(1)):
            db.add_all([
                JobOpening(title="AI产品经理实习生", department="企业AI应用部", location="Singapore", employment_type="实习", description="参与企业AI工作流产品的需求、原型和上线迭代。", requirements="理解B端业务流程，熟悉SQL、Python或AI应用原型。", status="开放"),
                JobOpening(title="数据产品实习生", department="数据平台组", location="Kuala Lumpur", employment_type="实习", description="支持数据指标、看板和业务分析产品。", requirements="熟悉SQL和数据分析，能整理需求并配合开发。", status="开放"),
                JobOpening(title="数字化转型产品助理", department="流程创新中心", location="Singapore", employment_type="实习", description="支持企业流程梳理和数字化项目交付。", requirements="了解审批、资产或工单系统，具备良好沟通能力。", status="暂停"),
            ])
        db.commit()
