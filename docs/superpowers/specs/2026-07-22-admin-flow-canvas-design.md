# 后台管理概览 + 流程画布编辑器 + 角色管理 设计文档

> 版本：v1.0 | 日期：2026-07-22 | 基于脑暴讨论

---

## 一、需求摘要

为审批流程系统新增后台管理导航分组，包含角色管理页面，并将现有流程模板管理升级为拖拽画布编辑器。平台管理员可通过低代码方式手工配置流程节点、流转关系及对应角色。

---

## 二、侧边栏导航

在 `AppLayout.vue` 侧边栏新增"后台管理"分组，仅 `approval:manage` 权限用户可见：

```
后台管理
  ├── 角色管理    → /admin/roles
  ├── 审批类型    → /admin/approval-types
  ├── 表单模板    → /admin/form-templates
  ├── 流程模板    → /admin/flow-templates
  └── 审批日志    → /admin/approval-logs
```

现有的 4 个管理页面（AdminTypes / AdminFormTemplates / AdminFlowTemplates / AdminLogs）路由不变、内容保留，仅导航入口统一收归。

---

## 三、角色管理页

### 3.1 路由

`/admin/roles` → `AdminRoles.vue`，权限 `approval:manage`

### 3.2 功能

- 表格展示所有审批用户（姓名、邮箱、部门、角色）
- 新增用户（弹窗表单）
- 编辑用户（弹窗表单，含角色下拉选择）
- 删除用户（确认弹窗）

### 3.3 弹窗表单字段

| 字段 | 类型 | 说明 |
|------|------|------|
| 姓名 | 文本 | display_name |
| 邮箱 | 文本 | email |
| 部门 | 下拉 | 产品研发部/人力资源部/财务管理部 + 自定义 |
| 角色 | 下拉 | 部门经理/分管领导/HR/财务/分管副总 + 自定义 |

### 3.4 后端 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/admin/users` | 已有，用户列表 |
| PUT | `/api/v1/admin/users/{id}` | 新增，编辑用户 |
| DELETE | `/api/v1/admin/users/{id}` | 新增，删除用户 |

---

## 四、流程模板画布编辑器

### 4.1 入口

`AdminFlowTemplates.vue` 中，列表页保留，新建/编辑时提供两种模式切换：
- **可视化模式**（默认）：拖拽画布编辑器
- **JSON 模式**：现有 JSON 文本框编辑器

### 4.2 画布布局

```
┌────────────┬──────────────────────────────────┐
│  工具箱      │   画布                              │
│            │                                    │
│  [单人审批] │   ┌─ 节点1: 部门经理审批 ─┐          │
│  (可拖拽)   │   │  审批人: 张三           │          │
│            │   └──────────────────────┘          │
│  [会签]    │        │ (连线，表示流转顺序)          │
│  (可拖拽)   │        ▼                            │
│            │   ┌─ 节点2: 领导会签 ────┐           │
│            │   │  审批人: 李四 + 孙七    │          │
│            │   └──────────────────────┘          │
│            │        │                            │
│            │        ▼                            │
│            │   ┌─ 节点3: 财务审批 ────┐           │
│            │   │  审批人: 赵六           │          │
│            │   └──────────────────────┘          │
│            │                                    │
│            │                      [保存] [取消]    │
└────────────┴──────────────────────────────────┘
```

### 4.3 交互逻辑

1. **拖入节点**：从工具箱拖"单人审批"或"会签"到画布 → 生成节点方块
2. **连线**：节点自动按顺序从上到下排列，节点间显示箭头连线
3. **调序**：拖拽节点方块可调整顺序
4. **删除节点**：节点方块右上角 × 按钮
5. **配置节点**：点击节点 → 右侧滑出属性面板

### 4.4 属性面板

| 属性 | 控件 | 说明 |
|------|------|------|
| 节点名称 | 输入框 | 如"部门经理审批" |
| 节点类型 | 单选/会签（拖入时已确定，可切换） |
| 审批人 | 下拉选择 | 从审批用户列表获取；会签时可多选 |
| 允许转审 | 开关 | |
| 需要附件 | 开关 | 开启后显示文件类型输入框 |
| 超时时间 | 数字输入 | 单位：小时，0 表示不限 |

### 4.5 数据格式

画布数据保存时序列化为与现有 `flow_templates.nodes` JSON 一致的格式：

```json
[
  {"index": 0, "name": "部门经理审批", "type": "single", "approver_id": "...", "allow_transfer": true, "require_attachment": false, "timeout_hours": 24},
  {"index": 1, "name": "领导会签", "type": "counter_sign", "approver_ids": ["...", "..."], "allow_transfer": true, "require_attachment": false, "timeout_hours": 48},
  {"index": 2, "name": "财务审批", "type": "single", "approver_id": "...", "allow_transfer": false, "require_attachment": true, "attachment_types": ["发票", "合同"], "timeout_hours": 72}
]
```

### 4.6 技术方案

- 拖拽：原生 HTML5 Drag & Drop API（不引入额外库）
- 画布渲染：Vue 3 `v-for` 渲染节点列表 + CSS 连线（伪元素画竖线和箭头）
- 属性面板：Ant Design Drawer 组件从右侧滑出
- 双模式切换：`a-radio-group` 切换"可视化"/"JSON"编辑模式

---

## 五、后端变更

### 5.1 审批用户 CRUD（`router.py` 追加）

在 `admin_router` 中新增：

```python
@admin_router.put("/users/{user_id}")
def admin_update_user(user_id: str, body: dict, ...)  # 编辑用户

@admin_router.delete("/users/{user_id}")
def admin_delete_user(user_id: str, ...)  # 删除用户
```

### 5.2 流程模板 JSON 字段扩展

`flow_templates.nodes` JSON 中的节点对象增加可选字段：
- `require_attachment`: bool（默认 false）
- `attachment_types`: list[str]（如 ["发票", "合同"]）
- `timeout_hours`: int（默认 0 表示不限）

现有种子数据和已有流程不受影响（缺少字段时使用默认值）。

---

## 六、前端文件变更

| 操作 | 文件 | 说明 |
|------|------|------|
| 新增 | `AdminRoles.vue` | 角色管理页 |
| 修改 | `AdminFlowTemplates.vue` | 升级为画布编辑器 + JSON 双模式 |
| 修改 | `AppLayout.vue` | 新增"后台管理"导航分组 |
| 修改 | `router/index.ts` | 新增 `/admin/roles` 路由 |
| 修改 | `styles.css` | 新增画布编辑器样式 |
