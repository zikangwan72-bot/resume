<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { DeleteOutlined, DownOutlined, EditOutlined, PlusOutlined, UpOutlined } from '@ant-design/icons-vue'
import { message } from 'ant-design-vue'
import type { ApprovalUser, FlowEdgeSchema, FlowNodeSchema, FlowSchema, FlowValidationIssue, FormFieldDefinition } from '@/types/approval'

type ConditionConfig = { field_id: string; operator: string; value: unknown }
type EditableNode = FlowNodeSchema & { name: string; approval_type: 'single' | 'counter_sign'; approver_id: string; approver_ids: string[]; allow_transfer: boolean; timeout_hours: number }

const props = defineProps<{ modelValue: FlowSchema; users: ApprovalUser[]; fields: FormFieldDefinition[] }>()
const emit = defineEmits<{ 'update:modelValue': [value: FlowSchema]; validationChange: [value: FlowValidationIssue[]] }>()

const conditionOperators = [
  { value: 'eq', label: '等于' }, { value: 'ne', label: '不等于' }, { value: 'gt', label: '大于' }, { value: 'gte', label: '大于等于' },
  { value: 'lt', label: '小于' }, { value: 'lte', label: '小于等于' }, { value: 'contains', label: '包含' }, { value: 'not_contains', label: '不包含' },
]
const comparableTypes = new Set(['number', 'money', 'text', 'textarea', 'radio', 'select'])
const userOptions = computed(() => props.users.filter((user) => user.is_active).map((user) => ({ value: user.id, label: `${user.display_name} | ${user.department} | ${user.position}` })))
const eligibleFields = computed(() => props.fields.filter((field) => comparableTypes.has(field.type)))
const primaryNodes = computed(() => {
  const result: FlowNodeSchema[] = []
  let current = graph.value.nodes.find((item) => item.type === 'start')
  const visited = new Set<string>()
  while (current && !visited.has(current.id)) {
    visited.add(current.id)
    result.push(current)
    if (current.type === 'condition' || current.type === 'end') break
    current = node(outgoing(current.id)[0]?.target ?? '')
  }
  const end = graph.value.nodes.find((item) => item.type === 'end')
  if (end && !result.some((item) => item.id === end.id)) result.push(end)
  return result
})
const graph = ref<FlowSchema>({ nodes: [], edges: [] })
const selectedId = ref('start')
const editorOpen = ref(false)
const editing = ref<EditableNode | null>(null)
const editingCondition = ref<ConditionConfig>({ field_id: '', operator: 'eq', value: '' })
let applying = false

function copy<T>(value: T): T { return JSON.parse(JSON.stringify(value)) as T }
function createId(prefix: string) { return `${prefix}-${crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`}` }
function fixedGraph(value: FlowSchema | undefined): FlowSchema {
  const next = copy(value ?? { nodes: [], edges: [] })
  next.nodes = Array.isArray(next.nodes) ? next.nodes : []
  next.edges = Array.isArray(next.edges) ? next.edges : []
  if (!next.nodes.some((node) => node.type === 'start')) next.nodes.unshift({ id: 'start', type: 'start', name: '开始' })
  if (!next.nodes.some((node) => node.type === 'end')) next.nodes.push({ id: 'end', type: 'end', name: '结束' })
  const start = next.nodes.find((node) => node.type === 'start')!
  const end = next.nodes.find((node) => node.type === 'end')!
  if (!next.edges.length && start.id !== end.id) next.edges.push({ source: start.id, target: end.id })
  return next
}
function setGraph(value: FlowSchema) {
  graph.value = copy(value)
  applying = true
  emit('update:modelValue', copy(value))
  emit('validationChange', validate(value))
  queueMicrotask(() => { applying = false })
}
function outgoing(nodeId: string, value = graph.value) { return value.edges.filter((edge) => edge.source === nodeId) }
function incoming(nodeId: string, value = graph.value) { return value.edges.filter((edge) => edge.target === nodeId) }
function node(nodeId: string, value = graph.value) { return value.nodes.find((item) => item.id === nodeId) }
function nodeName(nodeId: string) { return node(nodeId)?.name || node(nodeId)?.label || nodeId }
function isDefault(edge: FlowEdgeSchema) { return edge.default === true }
function conditionLabel(edge: FlowEdgeSchema) {
  if (isDefault(edge)) return '默认分支'
  const condition = edge.condition as Partial<ConditionConfig> | undefined
  if (!condition?.field_id) return '待配置条件'
  const field = props.fields.find((item) => item.id === condition.field_id)
  const operator = conditionOperators.find((item) => item.value === condition.operator)
  return `${field?.label ?? condition.field_id} ${operator?.label ?? ''} ${String(condition.value ?? '')}`
}
function selectedNode() { return node(selectedId.value) }
function selectNode(id: string) { selectedId.value = id }
function commitAndSelect(next: FlowSchema, id: string, configure = true) { setGraph(next); selectedId.value = id; if (configure) void openEditor(id) }
function branchEdgeForAdd(source: string, value: FlowSchema) { return outgoing(source, value).find((edge) => !isDefault(edge)) ?? outgoing(source, value)[0] }

function addNode(kind: 'approval' | 'countersign' | 'condition') {
  const current = selectedNode()
  if (!current || current.type === 'end') return
  if (kind === 'condition' && !eligibleFields.value.length) { message.warning('请先在表单中添加可比较字段'); return }
  const next = copy(graph.value)
  const parentEdge = current.type === 'condition' ? branchEdgeForAdd(current.id, next) : outgoing(current.id, next)[0]
  if (!parentEdge) { message.warning('当前节点无法安全插入后续节点'); return }
  const target = parentEdge.target
  const id = createId(kind)
  const nextNode: FlowNodeSchema = kind === 'approval'
    ? { id, type: 'approval', name: '审批节点', approval_type: 'single', approver_id: '', allow_transfer: false, timeout_hours: 0 }
    : kind === 'countersign'
      ? { id, type: 'countersign', name: '会签节点', approval_type: 'counter_sign', approver_ids: [], allow_transfer: false, timeout_hours: 0 }
      : { id, type: 'condition', name: '条件分支' }
  parentEdge.target = id
  next.nodes.push(nextNode)
  if (kind === 'condition') {
    const field = eligibleFields.value[0]
    next.edges.push({ source: id, target, condition: { field_id: field.id, operator: 'eq', value: field.type === 'number' || field.type === 'money' ? 0 : '' } })
    next.edges.push({ source: id, target, default: true })
  } else next.edges.push({ source: id, target })
  commitAndSelect(next, id)
}

function startEditorValue(item: FlowNodeSchema): EditableNode {
  return {
    ...copy(item), name: String(item.name ?? item.label ?? ''), approval_type: item.approval_type ?? (item.type === 'countersign' ? 'counter_sign' : 'single'),
    approver_id: String(item.approver_id ?? ''), approver_ids: Array.isArray(item.approver_ids) ? [...item.approver_ids] : [],
    allow_transfer: item.allow_transfer === true, timeout_hours: Number(item.timeout_hours ?? 0),
  }
}
async function openEditor(id = selectedId.value) {
  const item = node(id)
  if (!item || item.type === 'start' || item.type === 'end') return
  selectedId.value = id
  editing.value = startEditorValue(item)
  if (item.type === 'condition') {
    const edge = outgoing(item.id).find((candidate) => !isDefault(candidate))
    const condition = edge?.condition as Partial<ConditionConfig> | undefined
    editingCondition.value = { field_id: String(condition?.field_id ?? eligibleFields.value[0]?.id ?? ''), operator: String(condition?.operator ?? 'eq'), value: condition?.value ?? '' }
  }
  editorOpen.value = true
  await nextTick()
}
function typedConditionValue(value: unknown, fieldId: string) {
  const field = props.fields.find((item) => item.id === fieldId)
  if (field && ['number', 'money'].includes(field.type)) return Number(value)
  return value
}
function applyEditor() {
  if (!editing.value) return
  const next = copy(graph.value)
  const index = next.nodes.findIndex((item) => item.id === editing.value!.id)
  if (index < 0) return
  const current = editing.value
  if (!current.name.trim()) { message.error('节点名称不能为空'); return }
  if (current.type === 'approval' && !current.approver_id) { message.error('请选择审批人'); return }
  if (current.type === 'countersign' && (current.approver_ids.length < 2 || new Set(current.approver_ids).size !== current.approver_ids.length)) { message.error('会签至少需要两名不同审批人'); return }
  if (current.type === 'condition' && (!currentConditionValid())) { message.error('请完成条件字段、比较方式和比较值'); return }
  const saved: FlowNodeSchema = { ...current, name: current.name.trim(), timeout_hours: Math.max(0, Number(current.timeout_hours) || 0) }
  if (saved.type === 'approval') { saved.approval_type = 'single'; saved.approver_ids = undefined; saved.allow_transfer = current.allow_transfer; saved.approver_id = current.approver_id }
  if (saved.type === 'countersign') { saved.approval_type = 'counter_sign'; saved.approver_id = undefined; saved.approver_ids = [...current.approver_ids]; saved.allow_transfer = current.allow_transfer }
  next.nodes[index] = saved
  if (saved.type === 'condition') {
    const edge = outgoing(saved.id, next).find((candidate) => !isDefault(candidate))
    if (edge) edge.condition = { field_id: editingCondition.value.field_id, operator: editingCondition.value.operator, value: typedConditionValue(editingCondition.value.value, editingCondition.value.field_id) }
  }
  setGraph(next); editorOpen.value = false
}
function currentConditionValid() { return Boolean(editingCondition.value.field_id && editingCondition.value.operator && editingCondition.value.value !== '' && editingCondition.value.value !== null && editingCondition.value.value !== undefined) }

function deleteSelected() {
  const current = selectedNode()
  if (!current || current.type === 'start' || current.type === 'end') return
  const previous = incoming(current.id)
  const following = outgoing(current.id)
  if (previous.length !== 1 || following.length !== 1) { message.warning('该节点包含分支，无法在不破坏流程的情况下删除'); return }
  const next = copy(graph.value)
  const parent = next.edges.find((edge) => edge.source === previous[0].source && edge.target === current.id)
  if (!parent) return
  parent.target = following[0].target
  next.edges = next.edges.filter((edge) => edge.source !== current.id && edge.target !== current.id)
  next.nodes = next.nodes.filter((item) => item.id !== current.id)
  commitAndSelect(next, parent.source, false)
}
function canMove(direction: 'up' | 'down') {
  const current = selectedNode()
  if (!current || !['approval', 'countersign'].includes(current.type)) return false
  if (direction === 'up') return Boolean(incoming(current.id).find((edge) => ['approval', 'countersign'].includes(node(edge.source)?.type ?? '')))
  const nextId = outgoing(current.id)[0]?.target
  return Boolean(nextId && ['approval', 'countersign'].includes(node(nextId)?.type ?? ''))
}
function moveSelected(direction: 'up' | 'down') {
  if (!canMove(direction)) return
  const current = selectedNode()!
  const next = copy(graph.value)
  if (direction === 'up') {
    const before = incoming(current.id, next).find((edge) => ['approval', 'countersign'].includes(node(edge.source, next)?.type ?? ''))!
    const previous = before.source
    const parentEdges = incoming(previous, next)
    const currentOut = outgoing(current.id, next)[0]
    parentEdges.forEach((edge) => { edge.target = current.id })
    before.target = currentOut.target
    currentOut.target = previous
  } else {
    const currentOut = outgoing(current.id, next)[0]
    const following = currentOut.target
    const parentEdges = incoming(current.id, next)
    const followingOut = outgoing(following, next)[0]
    parentEdges.forEach((edge) => { edge.target = following })
    currentOut.target = followingOut.target
    followingOut.target = current.id
  }
  setGraph(next)
}

function validate(value: FlowSchema): FlowValidationIssue[] {
  const errors: FlowValidationIssue[] = []
  const nodes = Array.isArray(value.nodes) ? value.nodes : []
  const edges = Array.isArray(value.edges) ? value.edges : []
  const ids = new Set<string>(); const byId = new Map<string, FlowNodeSchema>()
  for (const item of nodes) {
    if (!item.id || ids.has(item.id)) errors.push({ code: !item.id ? 'invalid_node_id' : 'duplicate_node_id', message: '流程节点必须使用不重复的稳定 ID', target_id: item.id })
    else { ids.add(item.id); byId.set(item.id, item) }
  }
  const starts = nodes.filter((item) => item.type === 'start'); const ends = nodes.filter((item) => item.type === 'end')
  if (starts.length !== 1) errors.push({ code: 'start_count', message: '流程必须包含一个开始节点' })
  if (ends.length !== 1) errors.push({ code: 'end_count', message: '流程必须包含一个结束节点' })
  if (!nodes.some((item) => item.type === 'approval' || item.type === 'countersign')) errors.push({ code: 'missing_approval_node', message: '流程至少需要一个审批节点' })
  const active = new Set(props.users.filter((user) => user.is_active).map((user) => user.id))
  const outgoingMap = new Map<string, FlowEdgeSchema[]>()
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) errors.push({ code: 'unknown_edge_node', message: '连线引用了不存在的节点' })
    else outgoingMap.set(edge.source, [...(outgoingMap.get(edge.source) ?? []), edge])
  }
  for (const item of nodes) {
    const out = outgoingMap.get(item.id) ?? []
    if (item.type === 'end' && out.length) errors.push({ code: 'invalid_end_outgoing', message: '结束节点不能有出边', target_id: item.id })
    if (item.type !== 'end' && item.type !== 'condition' && out.length !== 1) errors.push({ code: 'invalid_non_condition_branch', message: '非条件节点必须有且仅有一条出边', target_id: item.id })
    if (item.type === 'approval' && (!item.approver_id || !active.has(item.approver_id))) errors.push({ code: 'inactive_approver', message: '审批人必须是启用员工', target_id: item.id })
    if (item.type === 'countersign') {
      const approvers = item.approver_ids ?? []
      if (approvers.length < 2 || new Set(approvers).size !== approvers.length || approvers.some((id) => !active.has(id))) errors.push({ code: 'invalid_countersign_approvers', message: '会签节点至少需要两名不同的启用员工', target_id: item.id })
    }
    if (item.type === 'condition') {
      const defaults = out.filter(isDefault); const conditional = out.filter((edge) => !isDefault(edge))
      if (defaults.length !== 1) errors.push({ code: 'missing_default_branch', message: '条件节点必须包含一个默认分支', target_id: item.id })
      if (!conditional.length) errors.push({ code: 'missing_condition_branch', message: '条件节点至少需要一条条件分支', target_id: item.id })
      conditional.forEach((edge) => {
        const condition = edge.condition as Partial<ConditionConfig> | undefined; const field = props.fields.find((item) => item.id === condition?.field_id)
        if (!condition?.field_id || !condition.operator || condition.value === undefined || condition.value === '') errors.push({ code: 'invalid_condition', message: '条件分支必须配置字段、比较方式和比较值', target_id: item.id })
        else if (!field || !comparableTypes.has(field.type)) errors.push({ code: 'invalid_condition_field_type', message: '条件引用的字段不可比较', target_id: item.id })
        else if (!conditionOperators.some((operator) => operator.value === condition.operator)) errors.push({ code: 'invalid_condition_operator', message: '条件比较方式无效', target_id: item.id })
      })
    }
  }
  const start = starts[0]?.id; const end = ends[0]?.id
  if (start && end) {
    const reachable = new Set<string>(); const stack = [start]
    while (stack.length) { const id = stack.pop()!; if (reachable.has(id)) continue; reachable.add(id); (outgoingMap.get(id) ?? []).forEach((edge) => stack.push(edge.target)) }
    nodes.forEach((item) => { if (!reachable.has(item.id)) errors.push({ code: 'disconnected_node', message: '节点未连接到开始节点', target_id: item.id }) })
    const reverse = new Map<string, string[]>(); edges.forEach((edge) => reverse.set(edge.target, [...(reverse.get(edge.target) ?? []), edge.source]))
    const reachesEnd = new Set<string>(); const reverseStack = [end]
    while (reverseStack.length) { const id = reverseStack.pop()!; if (reachesEnd.has(id)) continue; reachesEnd.add(id); (reverse.get(id) ?? []).forEach((source) => reverseStack.push(source)) }
    reachable.forEach((id) => { if (!reachesEnd.has(id)) errors.push({ code: 'path_does_not_reach_end', message: '从该节点无法到达结束节点', target_id: id }) })
  }
  return errors
}

function focusTarget(id?: string) {
  if (!id) return
  selectedId.value = id
  void nextTick(() => document.querySelector<HTMLElement>(`[data-flow-node-id="${CSS.escape(id)}"]`)?.focus())
}
defineExpose({ focusTarget })

watch(() => props.modelValue, (value) => { if (!applying) { graph.value = fixedGraph(value); emit('validationChange', validate(graph.value)) } }, { deep: true, immediate: true })
watch(() => props.users, () => emit('validationChange', validate(graph.value)), { deep: true })
onMounted(() => { const normalized = fixedGraph(props.modelValue); graph.value = normalized; if (JSON.stringify(normalized) !== JSON.stringify(props.modelValue)) setGraph(normalized); else emit('validationChange', validate(normalized)) })
</script>

<template>
  <section class="flow-designer" aria-label="流程设计器">
    <header class="designer-header"><div><h2>流程设计</h2><p>从选中的节点继续添加。所有修改都会保持可发布的有向流程结构。</p></div><a-tag color="blue">受控流程图</a-tag></header>
    <div class="designer-tools" aria-label="流程节点工具">
      <a-button type="primary" @click="addNode('approval')"><template #icon><PlusOutlined /></template>单人审批</a-button>
      <a-button @click="addNode('countersign')"><template #icon><PlusOutlined /></template>会签</a-button>
      <a-button :disabled="!eligibleFields.length" @click="addNode('condition')"><template #icon><PlusOutlined /></template>条件分支</a-button>
      <span class="tool-separator" />
      <a-tooltip title="上移当前节点"><a-button aria-label="上移节点" :disabled="!canMove('up')" @click="moveSelected('up')"><UpOutlined /></a-button></a-tooltip>
      <a-tooltip title="下移当前节点"><a-button aria-label="下移节点" :disabled="!canMove('down')" @click="moveSelected('down')"><DownOutlined /></a-button></a-tooltip>
      <a-tooltip title="删除当前节点"><a-button danger aria-label="删除节点" :disabled="selectedNode()?.type === 'start' || selectedNode()?.type === 'end'" @click="deleteSelected"><DeleteOutlined /></a-button></a-tooltip>
    </div>

    <div class="flow-canvas" aria-label="审批流程图">
      <div class="primary-lane">
        <template v-for="item in primaryNodes" :key="item.id">
          <button class="flow-node" :class="[{ selected: selectedId === item.id }, item.type]" :data-flow-node-id="item.id" type="button" @click="selectNode(item.id)" @dblclick="openEditor(item.id)">
            <span class="node-kicker">{{ item.type === 'start' ? '起点' : item.type === 'end' ? '终点' : item.type === 'countersign' ? '会签' : '审批' }}</span>
            <strong>{{ item.name || item.label || (item.type === 'start' ? '开始' : '结束') }}</strong>
            <small v-if="item.type === 'approval'">{{ userOptions.find((user) => user.value === item.approver_id)?.label || '待选择审批人' }}</small>
            <small v-if="item.type === 'countersign'">{{ item.approver_ids?.length ? `${item.approver_ids.length} 名审批人` : '待选择审批人' }}</small>
          </button>
          <span v-if="item.type !== 'end'" class="connector" aria-hidden="true">↓</span>
        </template>
      </div>
      <div v-if="graph.nodes.some((item) => item.type === 'condition')" class="condition-area">
        <article v-for="conditionNode in graph.nodes.filter((item) => item.type === 'condition')" :key="conditionNode.id" class="condition-block">
          <button class="flow-node condition" :class="{ selected: selectedId === conditionNode.id }" :data-flow-node-id="conditionNode.id" type="button" @click="selectNode(conditionNode.id)" @dblclick="openEditor(conditionNode.id)"><span class="node-kicker">条件</span><strong>{{ conditionNode.name || '条件分支' }}</strong><small>按顺序匹配，未命中进入默认分支</small></button>
          <div class="branch-lanes">
            <div v-for="edge in outgoing(conditionNode.id)" :key="`${edge.source}-${edge.target}-${edge.default ? 'default' : JSON.stringify(edge.condition)}`" class="branch-lane" :class="{ default: isDefault(edge) }">
              <span class="branch-label">{{ isDefault(edge) ? '默认分支' : '条件分支' }}</span>
              <span v-if="!isDefault(edge)" class="branch-rule">{{ conditionLabel(edge) }}</span>
              <button class="branch-target" :data-flow-node-id="edge.target" type="button" @click="selectNode(edge.target)"><strong>{{ nodeName(edge.target) }}</strong><small>{{ node(edge.target)?.type === 'end' ? '汇入结束节点' : '继续审批' }}</small></button>
            </div>
          </div>
        </article>
      </div>
    </div>
    <p class="canvas-hint">双击审批或条件节点可配置；条件分支默认与结束节点重新汇合。</p>

    <a-drawer v-model:open="editorOpen" title="节点配置" placement="right" :width="420" :destroy-on-close="false">
      <a-form v-if="editing" layout="vertical">
        <a-form-item label="节点名称"><a-input v-model:value="editing.name" aria-label="节点名称" maxlength="80" /></a-form-item>
        <template v-if="editing.type === 'approval' || editing.type === 'countersign'">
          <a-form-item label="审批人"><a-select v-if="editing.type === 'countersign'" v-model:value="editing.approver_ids" aria-label="审批人" mode="multiple" :options="userOptions" :max-tag-count="2" /><a-select v-else v-model:value="editing.approver_id" aria-label="审批人" :options="userOptions" /></a-form-item>
          <a-form-item label="允许转审"><a-switch v-model:checked="editing.allow_transfer" /></a-form-item>
          <a-form-item label="超时时间（小时）"><a-input-number v-model:value="editing.timeout_hours" aria-label="超时时间（小时）" :min="0" :precision="0" style="width:100%" /></a-form-item>
        </template>
        <template v-if="editing.type === 'condition'">
          <a-form-item label="条件字段"><select v-model="editingCondition.field_id" aria-label="条件字段" class="native-select"><option v-for="field in eligibleFields" :key="field.id" :value="field.id">{{ field.label }}</option></select></a-form-item>
          <a-form-item label="比较方式"><select v-model="editingCondition.operator" aria-label="比较方式" class="native-select"><option v-for="operator in conditionOperators" :key="operator.value" :value="operator.value">{{ operator.label }}</option></select></a-form-item>
          <a-form-item label="比较值"><a-input v-model:value="editingCondition.value" aria-label="比较值" /></a-form-item>
          <a-alert type="info" show-icon message="默认分支为必填，未命中任何条件时自动进入默认分支。" />
        </template>
      </a-form>
      <template #footer><a-button @click="editorOpen = false">取消</a-button><a-button type="primary" @click="applyEditor">应用节点配置</a-button></template>
    </a-drawer>
  </section>
</template>

<style scoped>
.flow-designer { display: grid; gap: 16px; min-width: 0; color: #172033; } .designer-header, .designer-tools { display: flex; align-items: center; justify-content: space-between; gap: 12px; } .designer-header h2 { margin: 0; font-size: 18px; font-weight: 700; } .designer-header p, .canvas-hint { margin: 4px 0 0; color: #687386; font-size: 13px; } .designer-tools { justify-content: flex-start; flex-wrap: wrap; padding: 12px 0; border-block: 1px solid #e7ebf1; } .tool-separator { height: 26px; border-left: 1px solid #dce2ea; }
.flow-canvas { overflow: auto; padding: 20px 12px 12px; background: repeating-linear-gradient(0deg, #fff, #fff 27px, #f7f9fb 28px), repeating-linear-gradient(90deg, transparent, transparent 27px, #f7f9fb 28px); border: 1px solid #e5eaf0; min-height: 390px; } .primary-lane { display: flex; align-items: center; justify-content: center; gap: 10px; min-width: 680px; } .connector { color: #6c7b92; font-size: 20px; line-height: 1; } .flow-node, .branch-target { display: grid; gap: 5px; width: 168px; min-height: 100px; padding: 12px; text-align: left; border: 1px solid #cfd8e4; border-radius: 6px; background: #fff; cursor: pointer; box-shadow: 0 1px 2px rgb(22 32 51 / 6%); } .flow-node:hover, .branch-target:hover { border-color: #356ad2; } .flow-node:focus-visible, .branch-target:focus-visible { outline: 3px solid #9ebcf7; outline-offset: 2px; } .flow-node.selected { border-color: #245bbf; box-shadow: 0 0 0 2px rgb(36 91 191 / 16%); } .flow-node.start, .flow-node.end { width: 108px; min-height: 72px; place-items: center; text-align: center; } .flow-node.condition { width: 224px; border-color: #d8a72a; background: #fffdf5; } .node-kicker, .branch-label { color: #67758b; font-size: 12px; } .flow-node strong, .branch-target strong { font-size: 14px; } .flow-node small, .branch-target small, .branch-rule { color: #6d7889; font-size: 12px; line-height: 1.45; } .condition-area { display: grid; gap: 20px; margin-top: 26px; min-width: 680px; } .condition-block { display: grid; justify-items: center; gap: 14px; } .branch-lanes { display: grid; grid-template-columns: repeat(2, minmax(220px, 1fr)); width: min(760px, 100%); gap: 14px; } .branch-lane { display: grid; justify-items: center; gap: 7px; padding: 12px; border-top: 2px solid #4f83dc; background: rgb(79 131 220 / 4%); } .branch-lane.default { border-top-color: #8290a4; background: rgb(130 144 164 / 5%); } .branch-rule { min-height: 34px; text-align: center; } .canvas-hint { margin: 0; } .native-select { width: 100%; height: 32px; padding: 4px 10px; color: #172033; border: 1px solid #d9d9d9; border-radius: 6px; background: #fff; }
@media (max-width: 760px) { .designer-header { align-items: flex-start; } .designer-header .ant-tag { display: none; } .designer-tools { align-items: stretch; } .designer-tools :deep(.ant-btn) { flex: 1 1 108px; } .tool-separator { display: none; } .flow-canvas { padding: 14px 8px; min-height: 330px; } .primary-lane { justify-content: flex-start; } .branch-lanes { grid-template-columns: 1fr 1fr; min-width: 520px; } }
</style>
