# 企业 AI 套件身份、资产盘点与招聘 AI 设计

日期：2026-07-28

状态：设计章节已由用户确认，等待书面规格复核

## 1. 背景

现有系统已经具备 Vue 3、FastAPI、SQLAlchemy、SQLite、资产台账、基础盘点任务、招聘学生端和招聘管理端，但仍存在以下缺口：

- 登录仍是角色卡片式本地演示登录，没有邮箱密码账号。
- 主用户表与审批用户表分离，员工身份可能不一致。
- Supabase 只保留环境变量和基础迁移，尚未真正接入 PostgreSQL、Auth、Storage。
- 资产没有永久 UUID、可轮换二维码、批量导入和员工手机盘点入口。
- 盘点照片没有受控上传、访问和审计链路。
- 招聘 B 端和 C 端虽然路由分开，但业务深度不足，缺少文件简历、职位画像、结构化筛选、人才库、过程分析和真实 AI。
- DeepSeek 尚未接入，不能把静态或规则结果冒充模型输出。

本设计采用“本地可运行、云端可切换”的双模式架构。当前先交付完整本地业务流；创建 Supabase 项目后，切换到 PostgreSQL、Auth、Storage，而不重写业务模块。

## 2. 目标

1. 提供 20 个固定邮箱密码测试账号，覆盖六类企业角色。
2. 建立统一身份目录和稳定权限边界。
3. 支持 Excel/CSV 资产批量导入、预检、错误报告和事务提交。
4. 每件资产获得永久 UUID，以及可重新生成并使旧码失效的随机二维码。
5. 员工可使用微信扫一扫打开移动 H5，登录、拍照并提交盘点。
6. 将招聘候选人 C 端与招聘管理 B 端彻底分离，并补齐端到端招聘流程。
7. 通过 DeepSeek 生成可解释的简历结构化结果、岗位匹配评分、证据、缺口和面试问题。
8. 保留人工最终决策、AI 运行记录和完整审计日志。
9. 提供可应用到新 Supabase 项目的完整迁移、RLS、私有 Bucket 和配置说明。

## 3. 非目标

- 本阶段不代替用户注册或购买 Supabase 云项目。
- 不实现微信小程序、微信 OAuth 或微信 JS-SDK。
- 不接入外部招聘网站、短信网关、电子 Offer 或背景调查。
- 不允许 AI 自动拒绝、自动录用或直接改变候选人最终状态。
- 不允许匿名用户读取候选人资料、盘点照片或内部审核信息。
- 不把只存在环境变量的状态显示为“Supabase 已就绪”。

## 4. 总体架构

### 4.1 三个用户入口

| 入口 | 用户 | 路由范围 | 外壳 |
|---|---|---|---|
| 企业 B 端 | 管理员、招聘、资产、经理、审批角色 | `/dashboard`、`/modules/*`、`/recruitment/admin/*` | 企业后台导航 |
| 候选人 C 端 | 外部求职者 | `/careers`、`/careers/jobs/:id`、`/careers/status` | 独立招聘门户 |
| 员工移动端 | 内部员工 | `/inventory/scan/:token`、`/inventory/my-tasks` | 移动 H5 |

三个入口使用同一个 FastAPI API，但页面、权限、数据返回字段和导航完全分开。C 端不得引用后台布局组件；移动端不得暴露后台管理菜单。

### 4.2 服务边界

- `IdentityService`：登录、密码验证、角色权限、20 个测试账号和 Supabase JWT 适配。
- `AssetService`：资产台账、批量导入、永久 UUID 和二维码生命周期。
- `InventoryService`：任务、员工分配、扫码校验、照片、结果和异常复核。
- `RecruitmentService`：岗位、投递、候选人管道、状态历史和人才库。
- `AIScreeningService`：简历净化、DeepSeek 调用、结构化解析、评分和人工复核。
- `StorageProvider`：本地私有文件存储与 Supabase Storage 的统一接口。

### 4.3 双模式适配器

| 能力 | 本地模式 | Supabase 模式 |
|---|---|---|
| 数据库 | SQLite | Supabase PostgreSQL |
| 身份 | 本地邮箱密码 JWT | Supabase Auth JWT |
| 文件 | 后端私有目录 | 私有 Storage Bucket |
| AI | 未配置时禁用；配置后调用 DeepSeek | 相同后端 DeepSeek 适配器 |

服务端根据配置选择 Provider。业务 Router 不直接依赖 Supabase SDK，也不直接读写本地文件。

## 5. 身份、账号与权限

### 5.1 统一账号来源

主数据库 `users` 是账号的唯一事实来源。补充字段：

- `password_hash`
- `position`
- `role`
- `permissions`
- `is_active`
- `last_login_at`
- `auth_provider`
- `supabase_user_id`

审批模块现有 `approval_users` 暂时保留为兼容投影。应用启动时按不可变用户 UUID 同步显示名称、邮箱、部门、职位、角色和启用状态。所有登录和权限判断只读取主用户表。

### 5.2 测试账号矩阵

本地开发模式提供以下 20 个账号。默认测试密码为 `Demo@2026!`，数据库只保存 Argon2 哈希。生产或 Supabase 模式默认隐藏试用账号面板，并禁止共享测试密码。

| 角色 | 数量 | 邮箱 |
|---|---:|---|
| 平台管理员 | 2 | `admin01@demo.local`、`admin02@demo.local` |
| 招聘管理员 | 3 | `recruiter01@demo.local` 至 `recruiter03@demo.local` |
| 资产管理员 | 3 | `asset01@demo.local` 至 `asset03@demo.local` |
| 部门经理 | 4 | `manager01@demo.local` 至 `manager04@demo.local` |
| 审批/财务 | 3 | `approver01@demo.local`、`finance01@demo.local`、`finance02@demo.local` |
| 普通员工 | 5 | `employee01@demo.local` 至 `employee05@demo.local` |

### 5.3 权限矩阵

| 角色 | 核心权限 |
|---|---|
| `platform_admin` | 全部模块、配置、审计和用户管理 |
| `recruitment_admin` | 岗位、候选人、AI 筛选、人才库、招聘分析 |
| `asset_admin` | 资产、导入、二维码、盘点任务、异常复核 |
| `department_manager` | 本部门资产、下属盘点进度、审批处理 |
| `approval_finance` | 指定审批节点、财务复核、本人通知 |
| `employee` | 本人审批、通知、分配给本人的盘点任务和扫码提交 |

登录 API 使用邮箱密码，不再把客户端提供的角色直接当作身份依据。后端根据账号记录签发 JWT。账号停用后，已有 Token 也必须在下一次受保护请求时失效。

## 6. 资产批量导入

### 6.1 模板字段

必填列：`asset_code`、`name`、`category`、`department`、`owner_email`、`location`。

可选列：`status`、`purchase_date`、`value`、`vendor`、`serial_number`、`remark`。

支持 `.xlsx` 和 `.csv`。Excel 使用结构化工作簿解析，CSV 明确要求 UTF-8 或 UTF-8 BOM，不使用字符串拆行模拟表格解析。

### 6.2 两阶段导入

1. `POST /api/v1/assets/imports/preview` 上传文件。
2. 后端创建 `AssetImportBatch` 和逐行 `AssetImportRow`。
3. 校验列名、类型、必填值、邮箱、状态、日期、金额和重复资产编号。
4. 返回有效行、警告行、错误行及其原始行号。
5. 用户确认后调用 `POST /api/v1/assets/imports/{batch_id}/commit`。
6. 提交只写入预检通过且尚未提交的行，并使用事务和幂等键。
7. 重复资产编号跳过，不覆盖现有资产。
8. `GET /api/v1/assets/imports/{batch_id}/errors.csv` 下载错误报告。

新资产提交时自动生成 `asset_uid`，但不会自动轮换已有资产二维码。

## 7. 固定资产 ID 与二维码

### 7.1 标识模型

- `id`：数据库内部主键。
- `asset_uid`：永久 UUID，对外稳定且不可编辑。
- `asset_code`：企业可读编号，唯一且可在管理员流程中修正。
- `qr_version`：二维码版本，从 1 开始递增。
- `qr_generated_at`：最近生成时间。

二维码签名由 `asset_uid`、`qr_version` 与服务端 `QR_SIGNING_SECRET` 通过 HMAC-SHA256 生成。数据库不保存明文令牌，签名密钥只存在于后端环境变量。

### 7.2 生成与轮换

- `GET /api/v1/assets/{asset_id}/qr` 下载当前版本的二维码 PNG/SVG 和打印标签数据；如果尚未生成则创建版本 1。
- `POST /api/v1/assets/{asset_id}/qr/rotate` 明确执行二维码轮换。
- 二维码签名由 `asset_uid`、`qr_version` 和服务端密钥生成，可重复渲染当前标签，但无法从数据库字段推导签名。
- 轮换会增加 `qr_version`，旧二维码立即失效。
- `POST /api/v1/assets/qr/batch` 为选中资产打包当前版本 ZIP/PDF；只有显式 `rotate=true` 才批量轮换。
- 二维码 URL 使用 `PUBLIC_APP_BASE_URL`，不能硬编码 `127.0.0.1`。

本地手机验收时，前端通过局域网地址访问，Vite 监听 `0.0.0.0`，API 使用同源 `/api` 代理。云端必须使用 HTTPS 域名。

## 8. 员工微信 H5 盘点

### 8.1 扫码数据流

1. 微信扫一扫打开 `/inventory/scan/:token`。
2. 未登录时跳转移动登录页，并保留扫码回跳地址。
3. 后端验证签名、二维码版本、资产状态、当前盘点任务和员工权限。
4. 只有一个符合条件的任务时自动进入；有多个任务时先让员工选择任务；没有任务时显示无可执行任务。
5. 页面显示资产编号、名称、台账位置、责任人和任务信息。
6. 员工使用 `<input type="file" accept="image/*" capture="environment">` 拍摄现场照片。
7. 至少上传一张，最多三张；支持 JPEG、PNG、WebP，单张最大 8 MiB。
8. 选择 `正常`、`位置不符`、`盘亏` 或 `损坏`。
9. 异常结果必须填写实际位置和说明。
10. `POST /api/v1/inventory/mobile/submissions` 以任务、资产、员工和幂等键提交。
11. 返回成功凭证，后台任务进度、异常数和审计日志同步更新。

### 8.2 照片安全

本地照片保存在后端私有目录，不能由静态 Web 目录直接访问。Supabase 模式保存到私有 `asset-inventory` Bucket。数据库记录对象路径、MIME、大小、SHA-256、上传人和上传时间。后台查看通过鉴权下载接口或短期签名 URL；普通员工不能删除已提交照片。

同一盘点记录在任务关闭前允许重新提交，但必须保留版本历史。任务关闭后只允许资产管理员重新开启或更正。

## 9. 招聘 C 端

### 9.1 页面

- `/careers`：开放岗位列表、关键词、部门、地点和用工类型筛选。
- `/careers/jobs/:id`：岗位职责、要求、流程和工作地点。
- `/careers/status`：通过申请编号和查询凭证查看状态。

C 端使用独立布局，不展示后台侧栏、内部统计、AI 分数、审核备注或其他候选人数据。

### 9.2 投递

候选人可上传 PDF/DOCX 简历，并填写姓名、邮箱、电话、教育、经历、项目、技能和求职说明。提交前必须同意隐私说明及 AI 辅助筛选说明。系统生成不可猜测的状态查询凭证，只显示对外状态和招聘团队公开消息。

同一邮箱对同一岗位的重复投递返回明确提示；允许招聘管理员将历史候选人关联到新岗位，但不复制原始文件。

## 10. 招聘 B 端

### 10.1 工作台

- 招聘漏斗：投递、待筛选、待面试、面试中、Offer、录用、关闭。
- 待办：未解析简历、AI 失败、待人工复核、超时未处理。
- 维度：岗位、来源、部门、负责人、阶段停留时间。
- 招聘分析：转化率、平均处理时长、来源质量和岗位积压。

### 10.2 岗位与职位画像

岗位新增结构化字段：必备技能、加分技能、最低经验、教育要求、关键职责、评分权重和淘汰性人工检查项。AI 只按已发布的职位画像评估，画像变更产生版本，不覆盖历史筛选依据。

### 10.3 候选人详情

候选人详情分为原始简历、结构化画像、AI 匹配、流程记录、面试反馈和人工结论。支持筛选、排序、批量进入人才库和阶段流转。人工覆盖 AI 建议必须填写理由，并记录操作人、时间、旧值和新值。

## 11. DeepSeek AI 筛选

### 11.1 Provider

DeepSeek 仅由后端调用，配置项为：

- `DEEPSEEK_API_KEY`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-flash`

密钥不得进入前端、数据库、日志或审计详情。已在聊天中出现的旧密钥视为泄露，不得使用。

### 11.2 隐私净化

发送模型前移除姓名、邮箱、电话、精确地址和受保护属性。仅发送岗位画像和与岗位相关的教育、经历、项目、技能文本。候选人未同意 AI 辅助处理时，不创建模型任务，仍允许人工招聘流程继续。

### 11.3 结构化输出

模型必须返回符合 JSON Schema 的结果：

- `summary`
- `skills`
- `experience`
- `education`
- `projects`
- `dimension_scores`
- `evidence`
- `gaps`
- `uncertainties`
- `interview_questions`
- `recommendation`

评分维度默认是技能 35%、经验 30%、项目 20%、教育 15%，但以职位画像版本为准。每个得分必须关联原文证据；没有证据时必须标记不确定，不能补造经历。

### 11.4 运行与降级

创建 `AIScreeningRun`，状态为 `pending`、`running`、`completed` 或 `failed`。后台任务执行模型调用，前端轮询状态。保存模型名、提示词版本、输入摘要哈希、耗时、Token 使用量、结果和人工复核状态。

401、402、429、超时、无效 JSON 或服务错误均进入 `failed`，候选人投递保持成功。招聘管理员可以重试，不得因模型失败自动改变候选人阶段。

## 12. Supabase 云端切换

用户创建项目后执行以下流程：

1. 安装 Supabase CLI，并在仓库保留 `config.toml`、迁移和开发 seed。
2. `supabase login` 后使用项目引用执行 `supabase link`。
3. 先运行 `supabase db push --dry-run`，审核后再推送迁移。
4. 创建完整的身份、资产、盘点、招聘、AI 和审计表。
5. 创建私有 `asset-inventory` 和 `candidate-resumes` Bucket。
6. 为公开 Schema 和 `storage.objects` 配置 RLS。
7. 使用管理员脚本创建测试 Auth 用户并关联 `profiles`；生产环境不创建共享密码账号。
8. 配置后端 `DATABASE_URL`、Supabase URL、Anon Key 和 Service Role Key。
9. 运行数据库、Auth、Storage 主动健康检查，通过后才显示“Supabase 已配置”。

Supabase 官方建议把数据库变化作为迁移纳入版本控制，并先预览再推送。公开 Schema 表必须启用 RLS；Storage 默认也通过 `storage.objects` 的 RLS 控制访问。参考：[本地开发与迁移](https://supabase.com/docs/guides/local-development/cli-workflows)、[Row Level Security](https://supabase.com/docs/guides/database/postgres/row-level-security)、[Storage Access Control](https://supabase.com/docs/guides/storage/security/access-control)。

## 13. API 边界

### 13.1 身份

- `POST /api/v1/auth/login`
- `POST /api/v1/auth/logout`
- `GET /api/v1/auth/me`
- `GET /api/v1/auth/trial-accounts`，仅开发模式

### 13.2 资产与导入

- `POST /api/v1/assets/imports/preview`
- `GET /api/v1/assets/imports/{batch_id}`
- `POST /api/v1/assets/imports/{batch_id}/commit`
- `GET /api/v1/assets/imports/{batch_id}/errors.csv`
- `GET /api/v1/assets/{asset_id}/qr`
- `POST /api/v1/assets/{asset_id}/qr/rotate`
- `POST /api/v1/assets/qr/batch`

### 13.3 移动盘点

- `GET /api/v1/inventory/mobile/scan/{token}`
- `POST /api/v1/inventory/mobile/photos`
- `POST /api/v1/inventory/mobile/submissions`
- `GET /api/v1/inventory/mobile/my-tasks`

### 13.4 招聘与 AI

- `GET /api/v1/recruitment/public/jobs`
- `POST /api/v1/recruitment/public/applications`
- `POST /api/v1/recruitment/public/status`
- `GET /api/v1/recruitment/admin/dashboard`
- `GET /api/v1/recruitment/applications`
- `POST /api/v1/recruitment/applications/{id}/screen`
- `GET /api/v1/recruitment/applications/{id}/screening`
- `POST /api/v1/recruitment/applications/{id}/review`

## 14. 错误处理与审计

- 批量导入先预检再提交；提交使用事务和幂等键。
- 失效二维码返回 410；无任务或无权限分别返回 404/403。
- 文件类型、大小、图片数量和内容哈希由后端再次验证。
- 重复点击盘点提交返回原结果，不创建重复记录。
- AI 错误使用稳定错误码，不把上游响应、提示词或密钥返回前端。
- 登录、账号停用、资产导入、二维码轮换、照片上传、盘点提交、异常处置、AI 运行和人工覆盖都写审计日志。
- 审计详情不保存密码、Token、API Key、简历全文或照片二进制。

## 15. 测试边界

测试只通过公开接口和用户页面观察行为，不绑定私有函数实现。

### 15.1 后端 API

- 20 个账号能够登录，错误密码、停用账号和越权请求被拒绝。
- Excel/CSV 预检、重复编号、错误报告、事务提交和幂等提交。
- 永久 UUID 不变，二维码轮换后旧码返回 410。
- 员工只能提交分配给自己的任务，照片必填且访问受控。
- C 端不能读取后台候选人数据，B 端按角色限制。
- DeepSeek 成功结果符合 Schema；401、402、429、超时和坏 JSON 正确降级。
- SQLite 与 PostgreSQL 迁移具备相同业务约束。

### 15.2 前端 E2E

- 邮箱密码登录和试用账号选择。
- 不同角色菜单及路由权限。
- 资产模板下载、预检、错误显示和提交。
- 单个/批量二维码入口和旧码失效提示。
- 390 x 844 移动视口完成扫码回跳、拍照、异常填写和成功凭证。
- C 端独立投递，B 端收到候选人并展示 AI 状态。
- 招聘管理员查看证据、填写人工结论并保留历史。

### 15.3 完成验证

- `backend/.venv/Scripts/python.exe -m pytest`
- `npm.cmd run test:e2e`
- `npm.cmd run typecheck`
- `npm.cmd run build`
- Playwright 桌面与手机截图检查无横向溢出、重叠和不可操作控件。
- 后端 `/api/v1/health` 为 `healthy`，前端目标路由返回 200。

## 16. 交付阶段

### 阶段 1：身份与权限

统一用户目录、密码登录、20 个测试账号、角色权限和审批用户投影同步。

### 阶段 2：资产全流程

批量导入、永久 UUID、二维码、移动 H5、照片存储、异常复核和审计。

### 阶段 3：招聘与 AI

C 端职位/投递/查询，B 端岗位/候选人/人才库/分析，DeepSeek 筛选和人工复核。

### 阶段 4：Supabase 激活

完整迁移、RLS、私有 Bucket、Auth 用户同步、主动健康检查和云端验收。

每个阶段必须先通过本阶段回归，再进入下一阶段。现有审批中心行为不得回归。

## 17. 验收标准

- 登录页至少可使用 20 个固定测试账号，角色权限准确。
- 可导入包含有效行和错误行的 Excel/CSV，并得到可下载错误报告。
- 每件新增资产拥有永久 UUID，可生成并轮换二维码。
- 同一 Wi-Fi 下使用微信扫码可打开手机页，登录、拍照并完成盘点。
- 普通员工无法读取其他员工任务或后台照片。
- 招聘 C 端和 B 端在路由、布局、权限和返回数据上完全分离。
- 候选人投递后，B 端可查看原始简历、结构化结果、AI 证据和人工结论。
- DeepSeek 不可用时，招聘和资产核心流程仍可运行。
- 未创建 Supabase 项目时页面明确显示“未配置”；真实联通后才显示“已配置”。
