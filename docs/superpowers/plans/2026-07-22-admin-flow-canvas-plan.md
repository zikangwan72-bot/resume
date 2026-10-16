# 后台管理导航 + 角色管理 + 流程画布编辑器 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 为审批系统增加后台管理导航分组、角色管理 CRUD 页、流程模板拖拽画布编辑器（可视化+JSON双模式）。

**Architecture:** 后端新增 2 个 user CRUD 端点；前端在 AppLayout 加导航分组；AdminFlowTemplates 升级为 HTML5 拖拽画布 + Ant Design Drawer 属性面板 + 双模式切换；新增 AdminRoles 角色管理页。

**Tech Stack:** FastAPI + SQLAlchemy + Vue 3 + TypeScript + Ant Design Vue 4 + HTML5 Drag & Drop API

---

### Task 1: 后端——审批用户编辑/删除端点

**Files:**
- Modify: `backend/app/approval/router.py`

在 `admin_list_approval_users` 函数的 `return` 之后、`admin_list_logs` 之前，插入以下两个端点：

```python
@admin_router.put("/users/{user_id}")
def admin_update_user(
    user_id: str,
    body: dict,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    u = db.get(ApprovalUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    for field in ("display_name", "email", "department", "role"):
        if field in body:
            setattr(u, field, body[field])
    db.commit()
    db.refresh(u)
    return {"data": {"id": u.id, "display_name": u.display_name, "role": u.role}}


@admin_router.delete("/users/{user_id}")
def admin_delete_user(
    user_id: str,
    user: User = Depends(require_permission("approval:manage")),
    db: Session = Depends(get_approval_db),
) -> dict[str, Any]:
    u = db.get(ApprovalUser, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    db.delete(u)
    db.commit()
    return {"data": {"deleted": True}}
```

验证：
```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend
.venv\Scripts\python -c "from app.approval.router import admin_router; print([r.path for r in admin_router.routes])"
```

Expected: 路由列表包含 `/api/v1/admin/users/{user_id}` 对 PUT 和 DELETE

---

### Task 2: 前端——新增 `/admin/roles` 路由

**Files:**
- Modify: `frontend/src/router/index.ts`

在现有后台管理路由组中（`admin/approval-logs` 之后）插入角色管理路由：

```typescript
        {
          path: 'admin/roles',
          component: () => import('@/views/approval/AdminRoles.vue'),
          meta: { title: '角色管理', permission: 'approval:manage' },
        },
```

---

### Task 3: 前端——AppLayout 新增"后台管理"导航分组

**Files:**
- Modify: `frontend/src/layouts/AppLayout.vue`

在 `<script setup>` 的 `menuItems` computed 中，新增 `admin` 数组并追加到返回结果中。需要新增图标导入 `SettingOutlined`。

```typescript
// 在 import 区域新增 SettingOutlined
import {
  // ... existing imports ...
  SettingOutlined,  // 新增
  UserOutlined,
} from '@ant-design/icons-vue'

// 在 menuItems 的 computed 中，governance 之后新增 admin 数组
const admin = [
  { key: '/admin/roles', icon: h(UserOutlined), label: '角色管理', permission: 'approval:manage' },
  { key: '/admin/approval-types', icon: h(SettingOutlined), label: '审批类型', permission: 'approval:manage' },
  { key: '/admin/form-templates', icon: h(SettingOutlined), label: '表单模板', permission: 'approval:manage' },
  { key: '/admin/flow-templates', icon: h(SettingOutlined), label: '流程模板', permission: 'approval:manage' },
  { key: '/admin/approval-logs', icon: h(AuditOutlined), label: '审批日志', permission: 'approval:manage' },
]
  .filter((item) => auth.can(item.permission))
  .map(({ permission: _, ...item }) => item)

// 在 return 数组中追加 admin 分组
return [
  { key: '/dashboard', icon: h(BlockOutlined), label: '工作台' },
  ...(modules.length ? [{ type: 'group', label: '业务模块', children: modules }] : []),
  ...(admin.length ? [{ type: 'group', label: '后台管理', children: admin }] : []),
  ...(governance.length ? [{ type: 'group', label: '平台治理', children: governance }] : []),
]
```

注意：治理分组中 `审批日志` 之前的 `audit-logs` 菜单项保留（是审计日志，不同）。

---

### Task 4: 前端——AdminRoles.vue 角色管理页

**Files:**
- Create: `frontend/src/views/approval/AdminRoles.vue`

```vue
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import api from '@/api/client'

const users = ref<any[]>([])
const loading = ref(true)
const visible = ref(false)
const editing = ref<any>(null)
const form = ref({ display_name: '', email: '', department: '', role: '' })

const deptOptions = ['产品研发部', '人力资源部', '财务管理部']
const roleOptions = ['部门经理', '分管领导', 'HR', '财务', '分管副总']

onMounted(load)

async function load() {
  loading.value = true
  try { const res = await api.get('/api/v1/admin/users'); users.value = res.data.data } finally { loading.value = false }
}

function openCreate() {
  editing.value = null
  form.value = { display_name: '', email: '', department: '产品研发部', role: '部门经理' }
  visible.value = true
}

function openEdit(u: any) {
  editing.value = u
  form.value = { display_name: u.display_name, email: u.email, department: u.department, role: u.role }
  visible.value = true
}

async function save() {
  if (!form.value.display_name || !form.value.email) return message.warning('姓名和邮箱不能为空')
  try {
    if (editing.value) {
      await api.put(`/api/v1/admin/users/${editing.value.id}`, form.value)
    }
    message.success('保存成功'); visible.value = false; await load()
  } catch { message.error('保存失败') }
}

async function remove(id: string) {
  Modal.confirm({
    title: '确认删除', content: '删除后不可恢复',
    onOk: async () => { await api.delete(`/api/v1/admin/users/${id}`); message.success('已删除'); await load() },
  })
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div><p class="eyebrow">ADMIN</p><h1>角色管理</h1><p>管理审批流程中的所有用户角色</p></div>
    </header>

    <a-table :dataSource="users" :loading="loading" rowKey="id" :pagination="false">
      <a-table-column title="姓名" dataIndex="display_name" />
      <a-table-column title="邮箱" dataIndex="email" />
      <a-table-column title="部门" dataIndex="department" />
      <a-table-column title="角色"><template #default="{ record }"><a-tag>{{ record.role }}</a-tag></template></a-table-column>
      <a-table-column title="操作">
        <template #default="{ record }">
          <a-space>
            <a @click="openEdit(record)">编辑</a>
            <a style="color:#d9682f;" @click="remove(record.id)">删除</a>
          </a-space>
        </template>
      </a-table-column>
    </a-table>

    <a-modal v-model:visible="visible" :title="editing ? '编辑用户' : '查看用户'" @ok="save" :okText="'保存'">
      <a-form layout="vertical">
        <a-form-item label="姓名" required><a-input v-model:value="form.display_name" /></a-form-item>
        <a-form-item label="邮箱" required><a-input v-model:value="form.email" /></a-form-item>
        <a-form-item label="部门">
          <a-select v-model:value="form.department">
            <a-select-option v-for="d in deptOptions" :key="d" :value="d">{{ d }}</a-select-option>
          </a-select>
        </a-form-item>
        <a-form-item label="角色">
          <a-select v-model:value="form.role">
            <a-select-option v-for="r in roleOptions" :key="r" :value="r">{{ r }}</a-select-option>
          </a-select>
        </a-form-item>
      </a-form>
    </a-modal>
  </div>
</template>
```

---

### Task 5: 前端——AdminFlowTemplates.vue 升级为画布编辑器

**Files:**
- Modify: `frontend/src/views/approval/AdminFlowTemplates.vue` — 完全重写

这个文件较大，核心改为三个部分：列表页（不变）、可视化编辑弹窗、JSON 编辑弹窗。

完整代码：

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { message, Modal } from 'ant-design-vue'
import { PlusOutlined, DeleteOutlined, CloseOutlined } from '@ant-design/icons-vue'
import api from '@/api/client'

// ── 列表状态 ──
const items = ref<any[]>([])
const loading = ref(true)
const users = ref<any[]>([])

// ── 编辑弹窗 ──
const visible = ref(false)
const editing = ref<any>(null)
const editMode = ref<'visual' | 'json'>('visual')
const form = ref({ name: '', description: '', nodes_json: '[]' })

// ── 画布状态 ──
interface CanvasNode {
  _key: number
  name: string
  type: 'single' | 'counter_sign'
  approver_id: string
  approver_ids: string[]
  allow_transfer: boolean
  require_attachment: boolean
  attachment_types: string
  timeout_hours: number
}
let _nodeKey = 0
const canvasNodes = ref<CanvasNode[]>([])
const selectedNodeIndex = ref<number | null>(null)
const drawerVisible = ref(false)

onMounted(async () => {
  await load()
  try { const res = await api.get('/api/v1/admin/users'); users.value = res.data.data } catch { /* */ }
})

async function load() {
  loading.value = true
  try { const res = await api.get('/api/v1/admin/flow-templates'); items.value = res.data.data } finally { loading.value = false }
}

// ── 画布工具函数 ──
function makeNode(type: 'single' | 'counter_sign'): CanvasNode {
  _nodeKey++
  return {
    _key: _nodeKey,
    name: '',
    type,
    approver_id: '',
    approver_ids: [],
    allow_transfer: true,
    require_attachment: false,
    attachment_types: '',
    timeout_hours: 0,
  }
}

function canvasToJson(): any[] {
  return canvasNodes.value.map((n, i) => {
    const base: any = {
      index: i,
      name: n.name || `节点${i + 1}`,
      type: n.type,
      allow_transfer: n.allow_transfer,
      require_attachment: n.require_attachment,
      timeout_hours: n.timeout_hours,
    }
    if (n.type === 'counter_sign') {
      base.approver_ids = n.approver_ids
    } else {
      base.approver_id = n.approver_id
    }
    if (n.require_attachment) {
      base.attachment_types = n.attachment_types.split(',').map(s => s.trim()).filter(Boolean)
    }
    return base
  })
}

function jsonToCanvas(nodes: any[]) {
  _nodeKey = 0
  canvasNodes.value = (nodes || []).map((n: any) => ({
    _key: ++_nodeKey,
    name: n.name || '',
    type: n.type || 'single',
    approver_id: n.approver_id || (n.approver_ids?.[0] || ''),
    approver_ids: n.approver_ids || [],
    allow_transfer: n.allow_transfer ?? true,
    require_attachment: n.require_attachment ?? false,
    attachment_types: (n.attachment_types || []).join(', '),
    timeout_hours: n.timeout_hours ?? 0,
  }))
}

// ── 拖拽 ──
function onDragStart(e: DragEvent, nodeType: 'single' | 'counter_sign') {
  e.dataTransfer!.setData('nodeType', nodeType)
  e.dataTransfer!.effectAllowed = 'copy'
}

function onCanvasDragOver(e: DragEvent) {
  e.preventDefault()
  e.dataTransfer!.dropEffect = 'copy'
}

function onCanvasDrop(e: DragEvent) {
  e.preventDefault()
  const nodeType = e.dataTransfer!.getData('nodeType') as 'single' | 'counter_sign'
  if (!nodeType) return
  canvasNodes.value.push(makeNode(nodeType))
}

// ── 节点操作 ──
function removeNode(index: number) {
  canvasNodes.value.splice(index, 1)
  if (selectedNodeIndex.value === index) {
    selectedNodeIndex.value = null
    drawerVisible.value = false
  }
}

function openDrawer(index: number) {
  selectedNodeIndex.value = index
  drawerVisible.value = true
}

// ── 打开/保存 ──
function openCreate() {
  editing.value = null
  editMode.value = 'visual'
  form.value = { name: '', description: '', nodes_json: '[]' }
  canvasNodes.value = []
  visible.value = true
}

function openEdit(item: any) {
  editing.value = item
  editMode.value = 'visual'
  form.value = { name: item.name, description: item.description || '', nodes_json: JSON.stringify(item.nodes, null, 2) }
  jsonToCanvas(item.nodes || [])
  visible.value = true
}

async function save() {
  let nodes: any[]
  if (editMode.value === 'visual') {
    nodes = canvasToJson()
  } else {
    try { nodes = JSON.parse(form.value.nodes_json) } catch { return message.warning('JSON 格式不正确') }
  }
  try {
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

const selectedNode = computed(() => {
  if (selectedNodeIndex.value === null) return null
  return canvasNodes.value[selectedNodeIndex.value]
})

function getApproverName(id: string) {
  const u = users.value.find((u: any) => u.id === id)
  return u ? u.display_name : id.slice(0, 8)
}
</script>

<template>
  <div class="page-frame">
    <header class="page-heading">
      <div><p class="eyebrow">ADMIN</p><h1>流程模板管理</h1></div>
      <a-button type="primary" @click="openCreate"><PlusOutlined /> 新增模板</a-button>
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

    <!-- 编辑弹窗 -->
    <a-modal v-model:visible="visible" :title="editing ? '编辑流程模板' : '新增流程模板'" @ok="save" width="960px" :bodyStyle="{ padding: '12px 24px' }">
      <a-form layout="vertical" style="margin-bottom:12px;">
        <a-row :gutter="16">
          <a-col :span="12">
            <a-form-item label="名称" required><a-input v-model:value="form.name" /></a-form-item>
          </a-col>
          <a-col :span="12">
            <a-form-item label="编辑模式">
              <a-radio-group v-model:value="editMode" button-style="solid" size="small">
                <a-radio-button value="visual">可视化</a-radio-button>
                <a-radio-button value="json">JSON</a-radio-button>
              </a-radio-group>
            </a-form-item>
          </a-col>
        </a-row>
      </a-form>

      <!-- JSON 模式 -->
      <template v-if="editMode === 'json'">
        <a-textarea v-model:value="form.nodes_json" :rows="16" style="font-family:monospace;font-size:12px;" />
        <small style="color:#999;">
          格式：[{"index":0,"name":"节点名","type":"single","approver_id":"UUID","allow_transfer":true}]
        </small>
      </template>

      <!-- 可视化模式 -->
      <div v-else class="canvas-editor">
        <div class="canvas-toolbox">
          <p class="eyebrow" style="margin-bottom:10px;">工具箱</p>
          <div
            class="toolbox-item"
            draggable="true"
            @dragstart="(e: DragEvent) => onDragStart(e, 'single')"
          >
            <div class="toolbox-icon single">S</div>
            <span>单人审批</span>
          </div>
          <div
            class="toolbox-item"
            draggable="true"
            @dragstart="(e: DragEvent) => onDragStart(e, 'counter_sign')"
          >
            <div class="toolbox-icon multi">M</div>
            <span>会签</span>
          </div>
          <div style="margin-top:16px;color:#999;font-size:11px;line-height:1.6;">
            拖拽节点到右侧画布<br/>点击节点配置属性<br/>拖拽节点上下排序
          </div>
        </div>

        <div
          class="canvas-area"
          @dragover="onCanvasDragOver"
          @drop="onCanvasDrop"
        >
          <div v-if="canvasNodes.length === 0" class="canvas-placeholder">
            从左侧拖入审批节点到此处
          </div>
          <div v-for="(node, index) in canvasNodes" :key="node._key" class="canvas-node-wrapper">
            <div class="canvas-connector" v-if="index > 0"></div>
            <div
              class="canvas-node"
              :class="{ selected: selectedNodeIndex === index, counter: node.type === 'counter_sign' }"
              draggable="true"
              @click="openDrawer(index)"
            >
              <button class="node-remove" @click.stop="removeNode(index)"><CloseOutlined /></button>
              <strong>{{ node.name || `节点${index + 1}` }}</strong>
              <small v-if="node.type === 'single' && node.approver_id">审批人：{{ getApproverName(node.approver_id) }}</small>
              <small v-else-if="node.type === 'counter_sign' && node.approver_ids.length">
                审批人：{{ node.approver_ids.map(getApproverName).join(' + ') }}
              </small>
              <small v-else>点击配置审批人</small>
              <span class="node-badge" :class="node.type">{{ node.type === 'single' ? '单人' : '会签' }}</span>
            </div>
          </div>
        </div>
      </div>
    </a-modal>

    <!-- 属性 Drawer -->
    <a-drawer
      v-model:visible="drawerVisible"
      title="节点属性"
      placement="right"
      :width="380"
    >
      <template v-if="selectedNode">
        <a-form layout="vertical">
          <a-form-item label="节点名称">
            <a-input v-model:value="selectedNode.name" placeholder="如：部门经理审批" />
          </a-form-item>
          <a-form-item label="节点类型">
            <a-radio-group v-model:value="selectedNode.type" button-style="solid" size="small">
              <a-radio-button value="single">单人审批</a-radio-button>
              <a-radio-button value="counter_sign">会签</a-radio-button>
            </a-radio-group>
          </a-form-item>
          <a-form-item v-if="selectedNode.type === 'single'" label="审批人">
            <a-select v-model:value="selectedNode.approver_id" placeholder="选择审批人">
              <a-select-option v-for="u in users" :key="u.id" :value="u.id">{{ u.display_name }} ({{ u.department }})</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item v-else label="审批人（可多选）">
            <a-select v-model:value="selectedNode.approver_ids" mode="multiple" placeholder="选择审批人">
              <a-select-option v-for="u in users" :key="u.id" :value="u.id">{{ u.display_name }} ({{ u.department }})</a-select-option>
            </a-select>
          </a-form-item>
          <a-form-item label="允许转审">
            <a-switch v-model:checked="selectedNode.allow_transfer" />
          </a-form-item>
          <a-form-item label="需要上传附件">
            <a-switch v-model:checked="selectedNode.require_attachment" />
          </a-form-item>
          <a-form-item v-if="selectedNode.require_attachment" label="文件类型（逗号分隔）">
            <a-input v-model:value="selectedNode.attachment_types" placeholder="如：发票,合同,报价单" />
          </a-form-item>
          <a-form-item label="超时时间（小时）">
            <a-input-number v-model:value="selectedNode.timeout_hours" :min="0" style="width:100%" placeholder="0 表示不限" />
          </a-form-item>
        </a-form>
      </template>
    </a-drawer>
  </div>
</template>
```

---

### Task 6: 前端——画布编辑器 CSS 样式

**Files:**
- Modify: `frontend/src/styles.css` — 追加在文件末尾

```css

/* ── 流程画布编辑器 ── */

.canvas-editor { display: flex; gap: 0; border: 1px solid var(--line); min-height: 420px; background: #fff; }

.canvas-toolbox { width: 140px; padding: 16px 12px; border-right: 1px solid var(--line); background: #f8faf9; display: flex; flex-direction: column; }
.toolbox-item { display: flex; align-items: center; gap: 8px; padding: 10px; margin-bottom: 8px; border: 1px dashed #c4d1cc; cursor: grab; user-select: none; font-size: 12px; }
.toolbox-item:active { cursor: grabbing; }
.toolbox-item:hover { border-color: var(--teal); background: #f0f8f6; }
.toolbox-icon { width: 28px; height: 28px; display: grid; place-items: center; border-radius: 4px; font: 700 11px Georgia, serif; color: #fff; flex-shrink: 0; }
.toolbox-icon.single { background: var(--teal); }
.toolbox-icon.multi { background: #d9682f; }

.canvas-area { flex: 1; padding: 24px 32px; overflow-y: auto; min-height: 420px; }
.canvas-placeholder { height: 100%; min-height: 360px; display: flex; align-items: center; justify-content: center; color: #b0beb9; font-size: 14px; border: 2px dashed #e0e7e4; }

.canvas-node-wrapper { position: relative; }
.canvas-connector {
  width: 2px; height: 28px; margin-left: 140px;
  background: linear-gradient(to bottom, var(--teal) 0%, var(--teal) 60%, transparent 60%, transparent 70%, var(--teal) 70%, var(--teal) 100%);
  position: relative;
}
.canvas-connector::after {
  content: ''; position: absolute; bottom: -6px; left: -6px;
  width: 0; height: 0; border-left: 7px solid transparent; border-right: 7px solid transparent; border-top: 8px solid var(--teal);
}

.canvas-node {
  position: relative; width: 280px; padding: 14px 16px; margin: 0 auto;
  border: 2px solid var(--line); background: #fff; cursor: pointer;
  display: flex; flex-direction: column; gap: 4px;
}
.canvas-node:hover { border-color: var(--teal); }
.canvas-node.selected { border-color: var(--teal); box-shadow: 0 0 0 3px rgba(8,126,111,.12); }
.canvas-node.counter { border-style: double; }
.canvas-node strong { font-size: 14px; }
.canvas-node small { color: var(--muted); font-size: 11px; }
.node-remove {
  position: absolute; top: 4px; right: 4px; width: 22px; height: 22px;
  display: grid; place-items: center; border: 1px solid transparent; background: transparent; color: #bbb; cursor: pointer; font-size: 10px;
}
.node-remove:hover { border-color: #e8dbdb; background: #fef5f5; color: #d9682f; }
.node-badge {
  position: absolute; top: -1px; right: -1px; padding: 2px 8px; font-size: 10px; font-weight: 600; color: #fff;
}
.node-badge.single { background: var(--teal); }
.node-badge.counter { background: #d9682f; }
```

---

### Task 7: 验证——构建 + API 测试

- [ ] **Step 1: 前端构建**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\frontend
npm run build 2>&1
```

Expected: Build 成功，无错误。

- [ ] **Step 2: 后端 API 测试**

```powershell
cd C:\Users\万小饱\Desktop\pythoncode\enterprise-ai-suite\backend
Remove-Item approval.db -ErrorAction SilentlyContinue
.venv\Scripts\python -m uvicorn app.main:app --port 8000 &
Start-Sleep -Seconds 4

# 登录管理员
$token = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/auth/demo-login -Method Post -Body '{"role":"platform_admin"}' -ContentType "application/json").data.access_token

# 获取用户列表
$users = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/admin/users -Headers @{Authorization="Bearer $token"}).data
Write-Host "Users: $($users.Count)"

# 编辑用户（改张三的角色）
$zhangsan = $users[0]
Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/admin/users/$($zhangsan.id) -Method Put -Headers @{Authorization="Bearer $token"} -Body '{"role":"分管领导"}' -ContentType "application/json"
Write-Host "Update OK"

# 验证修改
$updated = (Invoke-RestMethod -Uri http://127.0.0.1:8000/api/v1/admin/users -Headers @{Authorization="Bearer $token"}).data | Where-Object { $_.id -eq $zhangsan.id }
Write-Host "Zhang San role: $($updated.role)"

Write-Host "`n=== ALL TESTS PASSED ==="
```

Expected: `Zhang San role: 分管领导`
