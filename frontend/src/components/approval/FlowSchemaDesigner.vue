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
    if (current.type === 'end') break
    current = current.type === 'condition'
      ? node(findMergeId(current.id) ?? '')
      : node(outgoing(current.id)[0]?.target ?? '')
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
  emit('update:modelValue', copy(value))
  emit('validationChange', validate(value))
}
function outgoing(nodeId: string, value = graph.value) { return value.edges.filter((edge) => edge.source === nodeId) }
function incoming(nodeId: string, value = graph.value) { return value.edges.filter((edge) => edge.target === nodeId) }
function node(nodeId: string, value = graph.value) { return value.nodes.find((item) => item.id === nodeId) }
function nodeName(nodeId: string) {
  const item = node(nodeId)
  if (!item) return nodeId
  return String(item.name || item.label || (item.type === 'start' ? '开始' : item.type === 'end' ? '结束' : item.type === 'condition' ? '条件分支' : isCountersign(item) ? '会签步骤' : '审批步骤'))
}
function isDefault(edge: FlowEdgeSchema) { return edge.default === true }
function isCountersign(item: FlowNodeSchema | undefined) { return item?.type === 'countersign' || (item?.type === 'approval' && item.approval_type === 'counter_sign') }
function userName(id: string) { return props.users.find((user) => user.id === id)?.display_name ?? '待选择审批人' }
function approverSummary(item: FlowNodeSchema) {
  return isCountersign(item)
    ? (item.approver_ids?.length ? item.approver_ids.map(userName).join('、') : '待选择审批人')
    : userName(String(item.approver_id ?? ''))
}
function distancesFrom(startId: string) {
  const distances = new Map<string, number>([[startId, 0]])
  const queue = [startId]
  while (queue.length) {
    const id = queue.shift()!
    for (const edge of outgoing(id)) {
      if (distances.has(edge.target)) continue
      distances.set(edge.target, (distances.get(id) ?? 0) + 1)
      queue.push(edge.target)
    }
  }
  return distances
}
function findMergeId(conditionId: string) {
  const branches = outgoing(conditionId)
  if (branches.length < 2) return branches[0]?.target
  const distances = branches.map((edge) => distancesFrom(edge.target))
  const common = [...distances[0].keys()].filter((id) => distances.every((items) => items.has(id)))
  common.sort((left, right) => {
    const leftDistances = distances.map((items) => items.get(left) ?? Number.MAX_SAFE_INTEGER)
    const rightDistances = distances.map((items) => items.get(right) ?? Number.MAX_SAFE_INTEGER)
    return Math.max(...leftDistances) - Math.max(...rightDistances)
      || leftDistances.reduce((sum, value) => sum + value, 0) - rightDistances.reduce((sum, value) => sum + value, 0)
  })
  return common[0]
}
function branchPath(edge: FlowEdgeSchema, mergeId?: string) {
  const result: FlowNodeSchema[] = []; const seen = new Set<string>(); let current = node(edge.target)
  while (current && current.id !== mergeId && !seen.has(current.id)) {
    if (current.id === edge.source) break
    result.push(current)
    seen.add(current.id)
    if (current.type === 'condition' || current.type === 'end') break
    current = node(outgoing(current.id)[0]?.target ?? '')
  }
  return result
}
function conditionLabel(edge: FlowEdgeSchema) {
  if (isDefault(edge)) return '其他情况'
  const condition = edge.condition as Partial<ConditionConfig> | undefined
  if (!condition?.field_id) return '待配置条件'
  const field = props.fields.find((item) => item.id === condition.field_id)
  const operator = conditionOperators.find((item) => item.value === condition.operator)
  const rawValue = condition.value
  const value = typeof rawValue === 'number' && Number.isFinite(rawValue) ? rawValue.toLocaleString('zh-CN') : String(rawValue ?? '')
  return `${field?.label ?? condition.field_id} ${operator?.label ?? ''} ${value}${field?.type === 'money' ? ' 元' : ''}`
}
function selectedNode() { return node(selectedId.value) }
function selectNode(id: string) { selectedId.value = id }
function commitAndSelect(next: FlowSchema, id: string, configure = true) { setGraph(next); selectedId.value = id; if (configure) void openEditor(id) }
function branchEdgeForAdd(source: string, value: FlowSchema) { return outgoing(source, value).find((edge) => !isDefault(edge)) ?? outgoing(source, value)[0] }

function insertOnEdge(parentEdge: FlowEdgeSchema | undefined, kind: 'approval' | 'countersign' | 'condition') {
  if (kind === 'condition' && !eligibleFields.value.length) { message.warning('请先在表单中添加可比较字段'); return }
  const next = copy(graph.value)
  const edge = parentEdge && next.edges.find((item) => item.source === parentEdge.source && item.target === parentEdge.target && item.default === parentEdge.default && JSON.stringify(item.condition) === JSON.stringify(parentEdge.condition))
  if (!edge) { message.warning('当前步骤无法添加下一步'); return }
  const target = edge.target
  const id = createId(kind)
  const nextNode: FlowNodeSchema = kind === 'approval'
    ? { id, type: 'approval', name: '审批节点', approval_type: 'single', approver_id: '', allow_transfer: false, timeout_hours: 0 }
    : kind === 'countersign'
      ? { id, type: 'countersign', name: '会签节点', approval_type: 'counter_sign', approver_ids: [], allow_transfer: false, timeout_hours: 0 }
      : { id, type: 'condition', name: '条件分支' }
  edge.target = id
  next.nodes.push(nextNode)
  if (kind === 'condition') {
    const field = eligibleFields.value[0]
    next.edges.push({ source: id, target, condition: { field_id: field.id, operator: 'eq', value: field.type === 'number' || field.type === 'money' ? 0 : '' } })
    next.edges.push({ source: id, target, default: true })
  } else next.edges.push({ source: id, target })
  commitAndSelect(next, id)
}
function insertAfter(anchorId: string, kind: 'approval' | 'countersign' | 'condition') {
  const anchor = node(anchorId)
  if (!anchor || anchor.type === 'end') return
  const edge = anchor.type === 'condition' ? branchEdgeForAdd(anchor.id, graph.value) : outgoing(anchor.id)[0]
  insertOnEdge(edge, kind)
}
function menuKind(key: string | number) {
  return ['approval', 'countersign', 'condition'].includes(String(key)) ? String(key) as 'approval' | 'countersign' | 'condition' : null
}
function handleInsert(anchorId: string, info: { key: string | number }) {
  const kind = menuKind(info.key)
  if (kind) insertAfter(anchorId, kind)
}
function handleBranchInsert(edge: FlowEdgeSchema, info: { key: string | number }) {
  const kind = menuKind(info.key)
  if (kind) insertOnEdge(edge, kind)
}

function startEditorValue(item: FlowNodeSchema): EditableNode {
  return {
    ...copy(item), type: isCountersign(item) ? 'countersign' : item.type, name: String(item.name ?? item.label ?? ''), approval_type: isCountersign(item) ? 'counter_sign' : 'single',
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
  if (!isCountersign(current) && current.type === 'approval' && !current.approver_id) { message.error('请选择审批人'); return }
  if (isCountersign(current) && (current.approver_ids.length < 2 || new Set(current.approver_ids).size !== current.approver_ids.length)) { message.error('会签至少需要两名不同审批人'); return }
  if (current.type === 'condition' && (!currentConditionValid())) { message.error('请完成条件字段、比较方式和比较值'); return }
  const saved: FlowNodeSchema = { ...current, name: current.name.trim(), timeout_hours: Math.max(0, Number(current.timeout_hours) || 0) }
  if (isCountersign(saved)) { saved.type = 'countersign'; saved.approval_type = 'counter_sign'; saved.approver_id = undefined; saved.approver_ids = [...current.approver_ids]; saved.allow_transfer = current.allow_transfer }
  else if (saved.type === 'approval') { saved.approval_type = 'single'; saved.approver_ids = undefined; saved.allow_transfer = current.allow_transfer; saved.approver_id = current.approver_id }
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
function canMove(direction: 'up' | 'down', currentId = selectedId.value) {
  const current = node(currentId)
  if (!current || !['approval', 'countersign'].includes(current.type) && !isCountersign(current)) return false
  if (direction === 'up') return Boolean(incoming(current.id).find((edge) => { const item = node(edge.source); return item?.type === 'approval' || isCountersign(item) }))
  const nextId = outgoing(current.id)[0]?.target
  return Boolean(nextId && (node(nextId)?.type === 'approval' || isCountersign(node(nextId))))
}
function moveSelected(direction: 'up' | 'down') {
  if (!canMove(direction)) return
  const current = selectedNode()!
  const next = copy(graph.value)
  if (direction === 'up') {
    const before = incoming(current.id, next).find((edge) => { const item = node(edge.source, next); return item?.type === 'approval' || isCountersign(item) })!
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
function moveNode(id: string, direction: 'up' | 'down') { selectedId.value = id; moveSelected(direction) }
function deleteNode(id: string) { selectedId.value = id; deleteSelected() }
function canMoveNode(id: string, direction: 'up' | 'down') { return canMove(direction, id) }
function conditionBranches(id: string) { return [...outgoing(id)].sort((left, right) => Number(isDefault(left)) - Number(isDefault(right))) }

function validate(value: FlowSchema): FlowValidationIssue[] {
  const errors: FlowValidationIssue[] = []
  const nodes = Array.isArray(value.nodes) ? value.nodes : []
  const edges = Array.isArray(value.edges) ? value.edges : []
  const ids = new Set<string>(); const byId = new Map<string, FlowNodeSchema>()
  for (const item of nodes) {
    if (!item.id || ids.has(item.id)) errors.push({ code: !item.id ? 'invalid_node_id' : 'duplicate_node_id', message: '每个流程步骤必须唯一', target_id: item.id })
    else { ids.add(item.id); byId.set(item.id, item) }
  }
  const starts = nodes.filter((item) => item.type === 'start'); const ends = nodes.filter((item) => item.type === 'end')
  if (starts.length !== 1) errors.push({ code: 'start_count', message: '流程必须包含一个开始节点' })
  if (ends.length !== 1) errors.push({ code: 'end_count', message: '流程必须包含一个结束节点' })
  if (!nodes.some((item) => item.type === 'approval' || item.type === 'countersign')) errors.push({ code: 'missing_approval_node', message: '流程至少需要一个审批节点' })
  const active = new Set(props.users.filter((user) => user.is_active).map((user) => user.id))
  const outgoingMap = new Map<string, FlowEdgeSchema[]>()
  for (const edge of edges) {
    if (!ids.has(edge.source) || !ids.has(edge.target)) errors.push({ code: 'unknown_edge_node', message: '流程顺序引用了不存在的步骤' })
    else outgoingMap.set(edge.source, [...(outgoingMap.get(edge.source) ?? []), edge])
  }
  const visiting = new Set<string>(); const visited = new Set<string>(); let cycleTarget: string | undefined
  const visit = (id: string): boolean => { if (visiting.has(id)) { cycleTarget = id; return true }; if (visited.has(id)) return false; visiting.add(id); const found = (outgoingMap.get(id) ?? []).some((edge) => visit(edge.target)); visiting.delete(id); visited.add(id); return found }
  if (nodes.some((item) => visit(item.id))) errors.push({ code: 'flow_cycle', message: '流程顺序不能循环', target_id: cycleTarget })
  for (const item of nodes) {
    const out = outgoingMap.get(item.id) ?? []
    if (item.type === 'end' && out.length) errors.push({ code: 'invalid_end_outgoing', message: '结束后不能再有步骤', target_id: item.id })
    if (item.type !== 'end' && item.type !== 'condition' && out.length !== 1) errors.push({ code: 'invalid_non_condition_branch', message: '每个普通步骤必须有一个下一步', target_id: item.id })
    if (!isCountersign(item) && item.type === 'approval' && (!item.approver_id || !active.has(item.approver_id))) errors.push({ code: 'inactive_approver', message: '审批人必须是启用员工', target_id: item.id })
    if (isCountersign(item)) {
      const approvers = item.approver_ids ?? []
      if (approvers.length < 2 || new Set(approvers).size !== approvers.length || approvers.some((id) => !active.has(id))) errors.push({ code: 'invalid_countersign_approvers', message: '会签节点至少需要两名不同的启用员工', target_id: item.id })
    }
    if (item.type === 'condition') {
      const defaults = out.filter(isDefault); const conditional = out.filter((edge) => !isDefault(edge))
      if (defaults.length !== 1) errors.push({ code: 'missing_default_branch', message: '条件判断必须始终保留“其他情况”', target_id: item.id })
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
    nodes.forEach((item) => { if (!reachable.has(item.id)) errors.push({ code: 'disconnected_node', message: '该步骤无法从开始到达', target_id: item.id }) })
    const reverse = new Map<string, string[]>(); edges.forEach((edge) => reverse.set(edge.target, [...(reverse.get(edge.target) ?? []), edge.source]))
    const reachesEnd = new Set<string>(); const reverseStack = [end]
    while (reverseStack.length) { const id = reverseStack.pop()!; if (reachesEnd.has(id)) continue; reachesEnd.add(id); (reverse.get(id) ?? []).forEach((source) => reverseStack.push(source)) }
    reachable.forEach((id) => { if (!reachesEnd.has(id)) errors.push({ code: 'path_does_not_reach_end', message: '该步骤之后无法到达结束', target_id: id }) })
  }
  return errors
}

function focusTarget(id?: string) {
  if (!id) return
  selectedId.value = id
  void nextTick(() => document.querySelector<HTMLElement>(`[data-flow-node-id="${CSS.escape(id)}"]`)?.focus())
}
defineExpose({ focusTarget, insertAfter })

function hydrateAndValidate(value: FlowSchema) {
  graph.value = fixedGraph(value)
  emit('validationChange', validate(graph.value))
}
watch([() => props.modelValue, () => props.users, () => props.fields], ([value]) => hydrateAndValidate(value), { deep: true, immediate: true, flush: 'post' })
onMounted(() => { const normalized = fixedGraph(props.modelValue); if (JSON.stringify(normalized) !== JSON.stringify(props.modelValue)) setGraph(normalized); hydrateAndValidate(props.modelValue) })
</script>

<template>
  <section class="flow-designer" aria-label="流程设计器">
    <header class="designer-header"><div><h2>流程设计</h2><p>按实际执行顺序从上到下阅读，可添加单人审批或会签节点。</p></div></header>

    <div class="flow-canvas" aria-label="审批流程">
      <div class="flow-column">
        <template v-for="item in primaryNodes" :key="item.id">
          <article v-if="item.type === 'condition'" class="condition-block">
            <div class="business-node condition-node" :class="{ selected: selectedId === item.id }">
              <button class="node-main" :data-flow-node-id="item.id" type="button" @click="selectNode(item.id)" @dblclick="openEditor(item.id)"><span class="node-kicker">条件判断</span><strong>{{ nodeName(item.id) }}</strong><small>从左到右匹配，未命中时进入其他情况</small></button>
              <div class="node-actions"><a-tooltip title="编辑"><a-button size="small" :aria-label="`编辑 ${nodeName(item.id)}`" @click="openEditor(item.id)"><EditOutlined /></a-button></a-tooltip><a-tooltip title="删除"><a-button size="small" danger :aria-label="`删除 ${nodeName(item.id)}`" @click="deleteNode(item.id)"><DeleteOutlined /></a-button></a-tooltip></div>
            </div>
            <div class="branch-lanes">
              <section v-for="edge in conditionBranches(item.id)" :key="`${edge.source}-${edge.target}-${edge.default ? 'other' : JSON.stringify(edge.condition)}`" class="branch-card" :class="{ other: isDefault(edge) }">
                <header class="branch-header"><span>{{ isDefault(edge) ? '其他情况' : '满足以下条件' }}</span><strong>{{ conditionLabel(edge) }}</strong></header>
                <div class="branch-flow">
                  <template v-for="branchNode in branchPath(edge, findMergeId(item.id))" :key="branchNode.id">
                    <div class="business-node compact" :class="{ selected: selectedId === branchNode.id }">
                      <button class="node-main" :data-flow-node-id="branchNode.id" type="button" @click="selectNode(branchNode.id)" @dblclick="openEditor(branchNode.id)"><span class="node-kicker">{{ isCountersign(branchNode) ? '会签' : '单人审批' }}</span><strong>{{ nodeName(branchNode.id) }}</strong><small>{{ approverSummary(branchNode) }}</small><small v-if="isCountersign(branchNode)" class="rule-copy">全部同意后继续</small></button>
                      <div v-if="branchNode.type !== 'end'" class="node-actions"><a-tooltip title="编辑"><a-button size="small" :aria-label="`编辑 ${nodeName(branchNode.id)}`" @click="openEditor(branchNode.id)"><EditOutlined /></a-button></a-tooltip><a-tooltip title="删除"><a-button size="small" danger :aria-label="`删除 ${nodeName(branchNode.id)}`" @click="deleteNode(branchNode.id)"><DeleteOutlined /></a-button></a-tooltip></div>
                    </div>
                    <div v-if="branchNode.type !== 'end'" class="inline-add">
                      <span class="flow-line" aria-hidden="true" />
                      <a-dropdown :trigger="['click']"><a-button shape="circle" size="small" :aria-label="`在 ${nodeName(branchNode.id)} 后添加节点`"><PlusOutlined /></a-button><template #overlay><a-menu @click="handleInsert(branchNode.id, $event)"><a-menu-item key="approval">单人审批</a-menu-item><a-menu-item key="countersign">会签</a-menu-item></a-menu></template></a-dropdown>
                      <span class="flow-line" aria-hidden="true" />
                    </div>
                  </template>
                  <div v-if="!branchPath(edge, findMergeId(item.id)).length" class="inline-add branch-empty-add">
                    <span class="flow-line" aria-hidden="true" />
                    <a-dropdown :trigger="['click']"><a-button shape="circle" size="small" :aria-label="`在 ${conditionLabel(edge)} 中添加节点`"><PlusOutlined /></a-button><template #overlay><a-menu @click="handleBranchInsert(edge, $event)"><a-menu-item key="approval">单人审批</a-menu-item><a-menu-item key="countersign">会签</a-menu-item></a-menu></template></a-dropdown>
                    <span class="flow-line" aria-hidden="true" />
                  </div>
                </div>
              </section>
            </div>
            <div class="merge-marker"><span aria-hidden="true" />自动汇合<span aria-hidden="true" /></div>
          </article>

          <div v-else class="business-node" :class="[{ selected: selectedId === item.id }, item.type]">
            <button class="node-main" :data-flow-node-id="item.id" type="button" @click="selectNode(item.id)" @dblclick="openEditor(item.id)">
              <span v-if="item.type !== 'start' && item.type !== 'end'" class="node-kicker">{{ isCountersign(item) ? '会签' : '单人审批' }}</span>
              <strong>{{ item.name || item.label || (item.type === 'start' ? '开始' : '结束') }}</strong>
              <small v-if="item.type === 'approval' || isCountersign(item)">{{ approverSummary(item) }}</small>
              <small v-if="isCountersign(item)" class="rule-copy">全部同意后继续</small>
            </button>
            <div v-if="item.type !== 'start' && item.type !== 'end'" class="node-actions">
              <a-tooltip title="编辑"><a-button size="small" :aria-label="`编辑 ${nodeName(item.id)}`" @click="openEditor(item.id)"><EditOutlined /></a-button></a-tooltip>
              <a-tooltip title="上移"><a-button size="small" :aria-label="`上移 ${nodeName(item.id)}`" :disabled="!canMoveNode(item.id, 'up')" @click="moveNode(item.id, 'up')"><UpOutlined /></a-button></a-tooltip>
              <a-tooltip title="下移"><a-button size="small" :aria-label="`下移 ${nodeName(item.id)}`" :disabled="!canMoveNode(item.id, 'down')" @click="moveNode(item.id, 'down')"><DownOutlined /></a-button></a-tooltip>
              <a-tooltip title="删除"><a-button size="small" danger :aria-label="`删除 ${nodeName(item.id)}`" @click="deleteNode(item.id)"><DeleteOutlined /></a-button></a-tooltip>
            </div>
          </div>
          <div v-if="item.type !== 'end' && item.type !== 'condition'" class="inline-add">
            <span class="flow-line" aria-hidden="true" />
            <a-dropdown :trigger="['click']"><a-button shape="circle" size="small" :aria-label="`在 ${nodeName(item.id)} 后添加节点`"><PlusOutlined /></a-button><template #overlay><a-menu @click="handleInsert(item.id, $event)"><a-menu-item key="approval">单人审批</a-menu-item><a-menu-item key="countersign">会签</a-menu-item></a-menu></template></a-dropdown>
            <span class="flow-line" aria-hidden="true" />
          </div>
        </template>
      </div>
    </div>

    <a-drawer v-model:open="editorOpen" title="步骤设置" placement="right" :width="420" :destroy-on-close="false">
      <a-form v-if="editing" layout="vertical">
        <a-form-item label="节点名称"><a-input v-model:value="editing.name" aria-label="节点名称" :maxlength="80" /></a-form-item>
        <template v-if="editing.type === 'approval' || editing.type === 'countersign'">
          <a-form-item label="审批人"><a-select v-if="isCountersign(editing)" v-model:value="editing.approver_ids" aria-label="审批人" mode="multiple" :options="userOptions" :max-tag-count="2" /><a-select v-else v-model:value="editing.approver_id" aria-label="审批人" :options="userOptions" /></a-form-item>
          <a-form-item label="允许转审"><a-switch v-model:checked="editing.allow_transfer" aria-label="允许转审" /></a-form-item>
          <a-form-item label="超时时间（小时）"><a-input-number v-model:value="editing.timeout_hours" aria-label="超时时间（小时）" :min="0" :precision="0" style="width:100%" /></a-form-item>
        </template>
        <template v-if="editing.type === 'condition'">
          <a-form-item label="条件字段"><select v-model="editingCondition.field_id" aria-label="条件字段" class="native-select"><option v-for="field in eligibleFields" :key="field.id" :value="field.id">{{ field.label }}</option></select></a-form-item>
          <a-form-item label="比较方式"><select v-model="editingCondition.operator" aria-label="比较方式" class="native-select"><option v-for="operator in conditionOperators" :key="operator.value" :value="operator.value">{{ operator.label }}</option></select></a-form-item>
          <a-form-item label="比较值"><a-input v-model:value="editingCondition.value" aria-label="比较值" /></a-form-item>
          <a-alert type="info" show-icon message="“其他情况”由系统自动保留，无需单独配置。" />
        </template>
      </a-form>
      <template #footer><a-button @click="editorOpen = false">取消</a-button><a-button type="primary" @click="applyEditor">应用节点配置</a-button></template>
    </a-drawer>
  </section>
</template>

<style scoped>
.flow-designer { display: grid; gap: 16px; min-width: 0; color: #172033; } .designer-header h2 { margin: 0; font-size: 18px; font-weight: 700; } .designer-header p { margin: 4px 0 0; color: #687386; font-size: 13px; }
.flow-canvas { overflow-x: auto; padding: 24px 16px; border: 1px solid #e5eaf0; background: #f8fafc; min-height: 390px; } .flow-column { display: grid; justify-items: center; width: min(820px, 100%); min-width: 560px; margin: 0 auto; }
.business-node { position: relative; display: grid; grid-template-columns: minmax(0, 1fr) auto; width: 320px; border: 1px solid #cfd8e4; border-radius: 6px; background: #fff; box-shadow: 0 1px 2px rgb(22 32 51 / 6%); } .business-node:hover { border-color: #7a9bd5; } .business-node.selected { border-color: #245bbf; box-shadow: 0 0 0 2px rgb(36 91 191 / 14%); } .business-node.start, .business-node.end { display: block; width: 124px; text-align: center; } .business-node.condition-node { width: 360px; border-color: #d7a623; background: #fffdf6; } .business-node.compact { width: 100%; max-width: 300px; }
.node-main { display: grid; gap: 4px; min-width: 0; padding: 14px 16px; color: inherit; text-align: left; border: 0; background: transparent; cursor: pointer; } .start .node-main, .end .node-main { text-align: center; } .node-main:focus-visible { outline: 3px solid #9ebcf7; outline-offset: 2px; } .node-main strong { overflow-wrap: anywhere; font-size: 14px; } .node-main small { color: #687386; font-size: 12px; line-height: 1.45; } .node-kicker { color: #52627a; font-size: 12px; } .rule-copy { color: #245bbf !important; }
.node-actions { display: flex; align-items: flex-start; gap: 4px; padding: 8px 8px 0 0; } .inline-add { display: grid; justify-items: center; width: 40px; } .flow-line { width: 1px; height: 12px; background: #b7c2d0; } .inline-add :deep(.ant-btn) { color: #245bbf; border-color: #9eb5d8; background: #fff; }
.condition-block { display: grid; justify-items: center; width: 100%; gap: 14px; } .branch-lanes { display: grid; grid-template-columns: repeat(2, minmax(230px, 1fr)); width: 100%; gap: 12px; } .branch-card { display: grid; align-content: start; min-width: 0; padding: 12px; border: 1px solid #bfd0ea; border-top: 3px solid #3f70bd; border-radius: 6px; background: #fff; } .branch-card.other { border-color: #ccd3dc; border-top-color: #7b8797; } .branch-header { display: grid; gap: 4px; min-height: 58px; padding-bottom: 10px; border-bottom: 1px solid #e8ecf1; } .branch-header span { color: #687386; font-size: 12px; } .branch-header strong { overflow-wrap: anywhere; font-size: 14px; } .branch-flow { display: grid; justify-items: center; gap: 0; padding-top: 12px; } .branch-empty-add { margin-top: -12px; } .merge-marker { display: flex; align-items: center; width: 100%; gap: 10px; color: #687386; font-size: 12px; } .merge-marker span { flex: 1; border-top: 1px solid #b7c2d0; }
.native-select { width: 100%; height: 32px; padding: 4px 10px; color: #172033; border: 1px solid #d9d9d9; border-radius: 6px; background: #fff; }
@media (max-width: 760px) { .flow-canvas { padding: 18px 8px; } .flow-column { min-width: 520px; } .business-node { width: 300px; } .branch-lanes { grid-template-columns: repeat(2, minmax(230px, 1fr)); } }
</style>
