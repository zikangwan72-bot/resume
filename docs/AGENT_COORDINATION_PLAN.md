# 三 Agent 协同开发计划

目标：把全资产管理系统和招聘系统从“页面假数据”改造成真实 SQLite 数据驱动、前后端分离、可操作、可测试的 MVP。

项目归口：Codex

## 1. Agent 分工

### Codex：总负责人、架构和最终验收

负责：

- 维护产品边界和数据模型契约
- 决定 API 字段、状态、错误码和页面路由
- 完成跨模块集成
- 完成 HTML 原型检查点
- 解决 MIMO 与 DeepSeek 的合并冲突
- 启停开发服务并做 Chrome 业务走查
- 运行完整后端测试、前端构建、Playwright 测试
- 修复所有阻塞问题
- 最终确认“没有前端业务假数组”

Codex 可以修改：

- `docs/`
- `backend/app/api/v1/router.py`
- `frontend/src/router/index.ts`
- `frontend/src/api/client.ts`
- 任何集成测试、修复文件

### DeepSeek CC：后端数据和 API Agent

负责：

- SQLAlchemy 业务模型
- Pydantic 请求/响应模型
- 资产管理 API
- 招聘系统 API
- 数据库初始化和幂等种子
- 后端单元/API 测试

只修改：

- `backend/app/business/`
- `backend/app/db/models.py` 或 `backend/app/db/seed.py`
- `backend/app/api/v1/router.py` 仅在 API 注册所需的最小改动
- `backend/tests/test_business_*.py`

不得修改：

- `frontend/`
- 审批模块业务逻辑
- 企业 IT 服务台

交付要求：

- 所有列表数据从数据库读取
- 所有写操作进入数据库事务
- 资产编号唯一
- 同一邮箱不能重复投递同一岗位
- 不覆盖已有业务数据
- API 测试通过

### MIMO Claude Code：前端页面和交互 Agent

负责：

- 资产系统页面拆分和 Ant Design Vue 交互
- 招聘学生端/管理端页面拆分
- 表单、Drawer、Modal、Table、筛选、状态反馈
- 前端 API 调用、加载态、空态、错误态
- 前端 Playwright 测试

只修改：

- `frontend/src/views/asset*/`
- `frontend/src/views/assets/`
- `frontend/src/views/recruitment/`
- `frontend/src/views/AssetManagementView.vue`
- `frontend/src/views/ResumeScreeningView.vue`
- `frontend/tests/e2e/asset-*.spec.ts`
- `frontend/tests/e2e/recruitment-*.spec.ts`

不得修改：

- `backend/`
- `frontend/src/router/index.ts`，除非 Codex 明确授权
- `frontend/src/styles.css` 全局规则
- 审批模块页面

交付要求：

- 页面不声明资产、岗位、候选人的业务数组
- 通过 Axios 调用 API
- 新增/编辑/删除/投递/状态更新都能点击完成
- 成功后重新请求列表
- 失败显示用户可理解的错误信息
- 统一使用 Ant Design Vue

## 2. 共享协作文件

所有 Agent 通过以下文件交接，不依赖对话上下文：

- `docs/AGENT_COORDINATION_PLAN.md`：总计划，只由 Codex 维护
- `docs/agent-coordination/API_CONTRACT.md`：API 字段和状态契约，只由 Codex 发布
- `docs/agent-coordination/TASKS.md`：任务状态和负责人
- `docs/agent-coordination/MIMO_HANDOFF.md`：MIMO 交付说明
- `docs/agent-coordination/DEEPSEEK_HANDOFF.md`：DeepSeek 交付说明
- `docs/agent-coordination/INTEGRATION_REPORT.md`：Codex 集成和测试报告

Agent 完成任务后必须：

1. 修改自己的代码范围。
2. 运行自己范围内的测试。
3. 提交 Git commit。
4. 在对应 handoff 文件写入改动、测试、已知问题。
5. 不覆盖其他 Agent 的未提交改动。

## 3. 分阶段执行

### 阶段 A：契约冻结

Codex 先发布：

- 资产、盘点、异常的字段定义
- 岗位、候选人投递的字段定义
- 状态枚举
- API 路径和响应格式
- 统一错误格式

冻结后 DeepSeek 和 MIMO 按契约并行开发。

### 阶段 B：后端和前端并行

DeepSeek：完成真实数据库和 API。

MIMO：使用 API 契约完成页面和交互。API 未完成时，可以用 Playwright route mock 做页面测试，但交付前必须删除 mock，并切回真实 API。

Codex：制作第一版 HTML 原型，确认业务布局和核心流程；同时审查两个 Agent 的边界和提交。

### 阶段 C：归口集成

Codex 按以下顺序集成：

1. 合并后端模型和 API。
2. 启动 FastAPI，验证 OpenAPI 和关键接口。
3. 接入 MIMO 页面。
4. 删除前端业务假数据。
5. 运行前后端全量测试。
6. 用 Chrome 完成业务流程走查。

### 阶段 D：反复测试

必须测试：

- 资产新增、编辑、删除、筛选
- 创建盘点任务、更新盘点进度
- 异常处置和归档
- 学生浏览开放岗位
- 学生填写并提交投递
- 同邮箱重复投递被拒绝
- 管理端看到新候选人
- 管理端更新候选人状态
- 刷新页面后数据仍存在
- 空数据、接口失败、重复数据、未登录访问

## 4. Git 协议

推荐分支：

- `agent/deepseek-backend`
- `agent/mimo-frontend`
- `codex/integration`

每个 Agent 不直接重置、覆盖或删除其他 Agent 文件。Codex 负责合并和最终提交。

如果三个 Agent 必须共享同一目录，则必须遵守“文件范围隔离 + 小步 commit + handoff 文件”规则；不得同时编辑同一个业务文件。

## 5. 真实数据标准

以下内容禁止存在于最终业务页面：

- Vue 中的 `const assets = [...]`
- Vue 中的 `const jobs = [...]`
- Vue 中的 `const candidates = [...]`
- 点击按钮只改变前端变量、不调用 API
- 页面显示数字但数据库没有对应来源

允许存在：

- 首次安装时写入 SQLite 的演示种子
- 空状态文案
- API 返回的数据
- 测试文件中的测试数据

## 6. 完成标准

只有同时满足以下条件才算完成：

- 两个系统页面边界清楚
- 页面操作可点击并产生真实数据库变化
- 刷新页面数据不丢失
- 前端不再维护业务假数组
- 后端测试通过
- 前端 typecheck、build、Playwright 通过
- Chrome 业务走查通过
- HTML 原型和最终 Vue 页面行为一致
- 任何 AI 模块仍然保持关闭，不提前伪装为已接入
