# Enterprise AI Suite

一个用于承载四个B端企业AI项目的统一工作台基础架构：

1. AI简历筛选系统
2. 流程审批中心与AI审批助手
3. 全资产管理系统与AI资产助手
4. 企业IT服务台、知识库RAG与工单Agent

当前版本已完成不接入 AI 的核心业务闭环：全资产管理、招聘系统、流程审批中心和统一工作台。AI 能力保留为后续嵌入项。

## 已实现

- Vue 3、TypeScript、Vite和Ant Design Vue企业后台
- FastAPI、Swagger和统一请求ID
- SQLite本地数据库与Supabase PostgreSQL云端数据库
- 20个固定试用账号、Bearer token和前后端权限检查
- 工作台、四模块入口、通知、审计、AI记录和个人资料
- Supabase Database/Auth/Storage状态探针，避免伪造外部服务连接
- 后端测试、前端类型检查和生产构建
- Playwright桌面、手机和权限边界验收
- 全资产管理：资产台账、资产新增/编辑/删除、盘点任务、异常处置归档
- 招聘系统：学生岗位浏览、岗位投递、投递记录、管理端岗位和候选人状态流转
- 资产、招聘和审批业务数据由 FastAPI + SQLAlchemy 持久化，支持本地 SQLite 和 Supabase PostgreSQL
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

## 固定试用账号

登录页面提供20个固定试用账号，覆盖平台管理员、招聘管理员、资产管理员、部门经理、财务审批和普通员工。统一试用密码为 `Demo@2026!`。

## Supabase

系统支持Supabase PostgreSQL和Storage。云端模式通过后端`.env`中的`DATABASE_URL`、`APPROVAL_DATABASE_URL`、`SUPABASE_URL`、`SUPABASE_ANON_KEY`和`SUPABASE_SERVICE_ROLE_KEY`启用；当前登录仍由后端本地用户表校验，健康检查会明确标注这一点。

## 检查

```powershell
.\scripts\check.ps1
```

## 业务数据说明

首次启动会写入可操作试用种子，用于展示真实数据库流程；之后的新增、编辑、删除、投递和状态更新都会持久化到当前配置的数据库。种子不会覆盖已有业务记录。

当前阶段明确不接入 AI，后续可在不改变核心业务模型的情况下增加简历解析、岗位匹配、资产异常解释和处置建议。

## 安全说明

- `.env`不会提交Git。
- Supabase service role和模型API密钥只能放在后端。
- 试用账号接口只在`APP_ENV=development`或`test`开放；生产环境必须使用随机`JWT_SECRET`，并关闭演示账号面板。
- 当前不接入外部招聘网站，也不上传真实个人简历；投递数据仅用于项目演示和测试。
