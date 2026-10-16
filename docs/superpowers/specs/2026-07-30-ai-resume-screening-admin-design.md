# AI 简历筛选管理端设计

## 1. 目标

将当前 Enterprise AI Suite 的用户可见范围收缩为一个后台管理端，围绕 AI 简历筛选形成最小可用闭环：配置岗位标准、上传 PDF/DOC/DOCX 简历、调用服务端 AI 进行筛选、查看结果并人工复核。

旧招聘后端表、接口和历史数据第一阶段保留，不从数据库删除；前端导航和公开员工投递入口移除，避免继续扩大产品范围，也避免破坏已有数据。

## 2. 页面与导航

保留：

- 登录
- AI 简历筛选首页/数据看板
- 岗位筛选标准
- 简历库
- 筛选结果详情
- AI 运行记录
- 个人资料与退出登录

移除前端入口：

- 员工公开投递页
- 招聘员工端
- 原招聘管理工作流
- 审批中心、资产管理、IT 服务台及其治理入口

默认登录后进入 AI 简历筛选看板，而不是原工作台。

## 3. 核心数据

### ScreeningJob

- `id`
- `name`
- `description`
- `required_skills`
- `preferred_skills`
- `rejection_conditions`
- `scoring_weights`
- `status`
- `created_at` / `updated_at`

### ResumeDocument

- `id`
- `filename`
- `file_type`
- `storage_path` 或本地文件标识
- `extracted_text`
- `parse_status`
- `created_at`

### ScreeningResult

- `id`
- `resume_id`
- `job_id`
- `score`
- `recommendation`
- `summary`
- `strengths`
- `gaps`
- `risk_flags`
- `evidence`
- `human_status`
- `review_note`
- `created_at`

历史 `JobOpening`、`CandidateApplication` 保留，第一阶段不再作为新页面的数据源。

## 4. 数据流

1. 管理员创建岗位筛选标准。
2. 管理员上传 PDF/DOC/DOCX 文件。
3. 后端校验扩展名、大小和文件内容，提取文本并保存原文元数据。
4. 管理员选择岗位，触发 AI 筛选。
5. 后端读取岗位标准和简历文本，调用已配置的服务端模型适配器。
6. 后端校验模型 JSON 结果，保存评分、依据和 AI 运行记录。
7. 前端展示结果，管理员执行人工复核。

AI 不自动录用或淘汰候选人。结果必须带有“依据”和“需人工复核”状态。

## 5. API 边界

新增或调整为以下接口族：

- `GET/POST/PATCH /api/v1/screening/jobs`
- `GET/POST /api/v1/screening/resumes`
- `POST /api/v1/screening/resumes/{id}/screen`
- `GET /api/v1/screening/results`
- `GET /api/v1/screening/results/{id}`
- `PATCH /api/v1/screening/results/{id}/review`
- `GET /api/v1/screening/dashboard`

上传接口支持 `multipart/form-data`。文件解析失败、模型未配置、模型返回非法 JSON、超时和额度错误都返回明确的可展示错误，不写入伪造成功结果。

## 6. AI 适配

优先复用现有后端 LLM 配置和服务端密钥。模型请求使用结构化 JSON 输出，至少包含：

```json
{
  "score": 0,
  "recommendation": "待复核",
  "summary": "",
  "strengths": [],
  "gaps": [],
  "risk_flags": [],
  "evidence": []
}
```

未配置模型时，页面明确显示“AI 未配置”，不退化成看似真实的 AI 结论。为保证本地验收，可保留一个明确标记为 `local-rules` 的离线测试模式，但不得冒充外部模型结果。

## 7. 界面方向

使用窄而高密度的招聘运营后台：左侧只保留简历筛选域，首页采用“指标 + 待处理列表 + 岗位分布 + 最近运行”布局；上传区突出文件状态和岗位选择；结果页突出评分、证据、风险和人工复核操作。延续现有 Vue 3、Ant Design Vue、Pinia 和 API client，不引入新的 UI 框架。

## 8. 验收标准

- 登录后默认进入 AI 简历筛选看板。
- 侧边栏不再显示员工投递、审批、资产和服务台入口。
- 可创建、编辑、停用岗位筛选标准。
- 可上传 PDF、DOC、DOCX；不支持的格式被拒绝并显示原因。
- 可将一份简历绑定到一个岗位并发起筛选。
- AI 配置正常时，结果包含分数、结论、优势、缺口、风险和依据。
- AI 未配置或调用失败时，不生成虚假成功结果。
- 可对结果执行人工复核并保存备注。
- 看板统计与结果列表数量一致。
- 前端类型检查、生产构建、后端测试通过。

## 9. 第一阶段明确不做

- 员工自助投递
- 外部招聘网站同步
- 自动录用、自动淘汰
- 多 Agent 编排
- 向量数据库和长期记忆
- 自动发送邮件或企业 IM
- 删除旧数据库表和旧后端接口
