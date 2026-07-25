# Enterprise AI Suite

一个用于承载四个B端企业AI项目的统一工作台基础架构：

1. AI简历筛选系统
2. 流程审批中心与AI审批助手
3. 全资产管理系统与AI资产助手
4. 企业IT服务台、知识库RAG与工单Agent

当前版本已完成两个不接入 AI 的业务 MVP：全资产管理和招聘系统。流程审批中心继续沿用既有实现，企业 IT 服务台暂保留底座入口。

## 已实现

- Vue 3、TypeScript、Vite和Ant Design Vue企业后台
- FastAPI、Swagger和统一请求ID
- SQLite本地数据库与Supabase PostgreSQL迁移脚本
- 两种demo角色、Bearer token和前后端权限检查
- 工作台、四模块入口、通知、审计、AI记录和个人资料
- AI与Supabase未配置状态，避免伪造外部服务连接
- 后端测试、前端类型检查和生产构建
- Playwright桌面、手机和权限边界验收
- 全资产管理：资产台账、资产新增/编辑/删除、盘点任务、异常处置归档
- 招聘系统：学生岗位浏览、岗位投递、投递记录、管理端岗位和候选人状态流转
- 资产和招聘业务数据由 FastAPI + SQLAlchemy 写入本地 SQLite，不再由前端维护业务假数组
- 可点击 HTML 原型：`artifacts/real-data-mvp-prototype.html`

## 目录

```text
frontend/    Vue前端
backend/     FastAPI后端和本地数据库
supabase/    PostgreSQL迁移和seed说明
scripts/     Windows启动与检查脚本
docs/        架构和数据库说明
```

## 本地启动

### 后端

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 前端

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\frontend
npm install
npm run dev
```

访问：

- 前端：http://127.0.0.1:5173
- API文档：http://127.0.0.1:8000/docs
- 健康检查：http://127.0.0.1:8000/api/v1/health

## Demo角色

登录页面可选择：平台管理员和产品演示用户。不同角色拥有不同菜单与API权限。

## Supabase

当前默认使用SQLite，启动后会自动创建`enterprise_ai.db`。准备云端联调时阅读
`docs/database.md`并运行`supabase/migrations/0001_common_foundation.sql`。

## 检查

```powershell
.\scripts\check.ps1
```

## 业务数据说明

首次启动会写入少量本地演示种子，用于展示真实数据库流程；之后的新增、编辑、删除、投递和状态更新都会持久化到 `enterprise_ai.db`。种子不会覆盖已有业务记录。

当前阶段明确不接入 AI，后续可在不改变核心业务模型的情况下增加简历解析、岗位匹配、资产异常解释和处置建议。

## 安全说明

- `.env`不会提交Git。
- Supabase service role和模型API密钥只能放在后端。
- 当前demo token仅用于本地开发，正式部署前必须切换为Supabase Auth验证。
- 当前不接入外部招聘网站，也不上传真实个人简历；本地投递数据仅用于项目演示和测试。
