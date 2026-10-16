<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowDownOutlined, ArrowUpOutlined, CopyOutlined, DeleteOutlined, HolderOutlined, PlusOutlined,
} from '@ant-design/icons-vue'
import ApprovalFieldControl from '@/components/approval/ApprovalFieldControl.vue'
import type { DetailColumn, DetailColumnType, FormField, FormSchema } from '@/types/approval'

const props = defineProps<{ modelValue: FormSchema }>()
const emit = defineEmits<{ 'update:modelValue': [value: FormSchema] }>()

type FieldType = FormField['type']
const palette: Array<{ type: FieldType; label: string }> = [
  { type: 'text', label: '单行文本' }, { type: 'textarea', label: '多行文本' },
  { type: 'number', label: '数字' }, { type: 'money', label: '金额' },
  { type: 'date', label: '日期' }, { type: 'date_range', label: '日期范围' },
  { type: 'radio', label: '单选' }, { type: 'checkbox', label: '多选' }, { type: 'select', label: '下拉选择' },
  { type: 'user', label: '人员' }, { type: 'department', label: '部门' }, { type: 'attachment', label: '附件' },
  { type: 'section', label: '分组标题' }, { type: 'detail_table', label: '明细表格' },
]
const choiceTypes = new Set<FieldType>(['radio', 'checkbox', 'select'])
const numericTypes = new Set<FieldType>(['number', 'money'])
const columnTypes: Array<{ value: DetailColumnType; label: string }> = [
  { value: 'text', label: '文本' }, { value: 'number', label: '数字' }, { value: 'money', label: '金额' }, { value: 'date', label: '日期' }, { value: 'select', label: '下拉选择' },
]
const selectedId = ref<string | null>(null)
const previewValues = ref<Record<string, string | number | string[] | Record<string, unknown>[] | null>>({})
const draggedId = ref<string | null>(null)
const fieldKey = (field: Pick<FormField, 'id' | 'key'>) => field.id || field.key
const selected = computed(() => props.modelValue.fields.find((field) => fieldKey(field) === selectedId.value) ?? null)
const fieldId = () => crypto.randomUUID()
const optionError = (options?: string[]) => {
  const normalized = (options ?? []).map((option) => option.trim())
  if (!normalized.length || normalized.some((option) => !option)) return '选项不能为空'
  return new Set(normalized).size !== normalized.length ? '选项不能重复' : undefined
}

function defaultField(type: FieldType): FormField {
  const label = palette.find((item) => item.type === type)?.label ?? '字段'
  const id = fieldId()
  return { id, key: id, label, type, required: false, options: choiceTypes.has(type) ? ['选项 1'] : undefined, columns: type === 'detail_table' ? [] : undefined }
}
function update(fields: FormField[]) { emit('update:modelValue', { fields }) }
function add(type: FieldType) {
  const field = defaultField(type)
  update([...props.modelValue.fields, field])
  selectedId.value = field.id
}
function patchField(patch: Partial<FormField>) {
  if (!selected.value) return
  update(props.modelValue.fields.map((field) => field.id === selected.value?.id ? { ...field, ...patch } : field))
}
function duplicate(field: FormField) {
  const id = fieldId()
  const copy = { ...field, id, key: id, label: `${field.label}（副本）`, options: field.options ? [...field.options] : undefined, columns: field.columns?.map((column) => { const columnId = fieldId(); return { ...column, id: columnId, key: columnId, options: column.options ? [...column.options] : undefined } }) }
  const index = props.modelValue.fields.indexOf(field)
  update([...props.modelValue.fields.slice(0, index + 1), copy, ...props.modelValue.fields.slice(index + 1)])
  selectedId.value = copy.id
}
function remove(field: FormField) {
  const id = fieldKey(field)
  update(props.modelValue.fields.filter((item) => fieldKey(item) !== id))
  delete previewValues.value[id]
  if (selectedId.value === id) selectedId.value = null
}
function move(field: FormField, direction: -1 | 1) {
  const index = props.modelValue.fields.indexOf(field); const target = index + direction
  if (target < 0 || target >= props.modelValue.fields.length) return
  const fields = [...props.modelValue.fields]; [fields[index], fields[target]] = [fields[target], fields[index]]; update(fields)
}
function startDrag(field: FormField, event: DragEvent) {
  draggedId.value = fieldKey(field)
  event.dataTransfer?.setData('text/plain', draggedId.value)
  if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move'
}
function dropOn(target: FormField) {
  const sourceId = draggedId.value
  draggedId.value = null
  if (!sourceId || sourceId === fieldKey(target)) return
  const fields = [...props.modelValue.fields]
  const sourceIndex = fields.findIndex((field) => fieldKey(field) === sourceId)
  const targetIndex = fields.findIndex((field) => fieldKey(field) === fieldKey(target))
  if (sourceIndex < 0 || targetIndex < 0) return
  const [source] = fields.splice(sourceIndex, 1)
  fields.splice(targetIndex, 0, source)
  update(fields)
}
function updateOption(index: number, value: string) { if (selected.value) patchField({ options: (selected.value.options ?? []).map((option, itemIndex) => itemIndex === index ? value.trim() : option) }) }
function addOption() { if (selected.value) patchField({ options: [...(selected.value.options ?? []), ''] }) }
function removeOption(index: number) { if (selected.value) patchField({ options: (selected.value.options ?? []).filter((_, itemIndex) => itemIndex !== index) }) }
function addColumn() { if (selected.value) { const id = fieldId(); patchField({ columns: [...(selected.value.columns ?? []), { id, key: id, label: '明细列', type: 'text', required: false }] }) } }
function patchColumn(id: string, patch: Partial<DetailColumn>) { if (selected.value) patchField({ columns: (selected.value.columns ?? []).map((column) => column.id === id ? { ...column, ...patch } : column) }) }
function removeColumn(id: string) { if (selected.value) patchField({ columns: (selected.value.columns ?? []).filter((column) => column.id !== id) }) }
function duplicateColumn(column: DetailColumn) { if (selected.value) { const id = fieldId(); const copy = { ...column, id, key: id, label: `${column.label}（副本）`, options: column.options ? [...column.options] : undefined }; const index = selected.value.columns?.indexOf(column) ?? -1; patchField({ columns: [...(selected.value.columns ?? []).slice(0, index + 1), copy, ...(selected.value.columns ?? []).slice(index + 1)] }) } }
function moveColumn(column: DetailColumn, direction: -1 | 1) { if (selected.value) { const columns = [...(selected.value.columns ?? [])]; const index = columns.indexOf(column); const target = index + direction; if (target >= 0 && target < columns.length) { [columns[index], columns[target]] = [columns[target], columns[index]]; patchField({ columns }) } } }
function updateColumnOption(column: DetailColumn, index: number, value: string) { patchColumn(column.id, { options: (column.options ?? []).map((option, itemIndex) => itemIndex === index ? value.trim() : option) }) }
function addColumnOption(column: DetailColumn) { patchColumn(column.id, { options: [...(column.options ?? []), ''] }) }
function removeColumnOption(column: DetailColumn, index: number) { patchColumn(column.id, { options: (column.options ?? []).filter((_, itemIndex) => itemIndex !== index) }) }
</script>

<template>
  <div class="designer" aria-label="表单设计器">
    <aside class="palette" aria-label="字段组件库">
      <h3>字段组件</h3>
      <div class="palette-grid">
        <a-button v-for="item in palette" :key="item.type" :data-field-type="item.type" @click="add(item.type)">{{ item.label }}</a-button>
      </div>
    </aside>
    <main class="canvas" aria-label="表单画布">
      <div class="applicant-lock">
        <strong>申请人信息</strong><span>姓名、邮箱、部门、职位将在提交时自动带入</span>
      </div>
      <a-empty v-if="!modelValue.fields.length" description="从左侧选择字段开始设计" />
      <a-form v-else layout="vertical" class="field-list" aria-label="业务字段">
        <article
          v-for="(field, index) in modelValue.fields"
          :key="fieldKey(field)"
          :data-field-id="fieldKey(field)"
          :class="['design-field', { selected: selectedId === fieldKey(field), dragging: draggedId === fieldKey(field) }]"
          @click="selectedId = fieldKey(field)"
          @dragover.prevent
          @drop.prevent="dropOn(field)"
        >
          <div class="field-actions">
            <a-tooltip title="选择"><a-button type="text" :aria-label="`选择字段 ${field.label}`" @click.stop="selectedId = fieldKey(field)"><PlusOutlined /></a-button></a-tooltip>
            <a-tooltip title="拖动排序"><a-button type="text" draggable="true" aria-label="拖动字段" @dragstart.stop="startDrag(field, $event)" @dragend="draggedId = null"><HolderOutlined /></a-button></a-tooltip>
            <a-tooltip title="上移"><a-button type="text" :disabled="index === 0" aria-label="上移字段" @click.stop="move(field, -1)"><ArrowUpOutlined /></a-button></a-tooltip>
            <a-tooltip title="下移"><a-button type="text" :disabled="index === modelValue.fields.length - 1" aria-label="下移字段" @click.stop="move(field, 1)"><ArrowDownOutlined /></a-button></a-tooltip>
            <a-tooltip title="复制"><a-button type="text" aria-label="复制字段" @click.stop="duplicate(field)"><CopyOutlined /></a-button></a-tooltip>
            <a-tooltip title="删除"><a-button type="text" danger aria-label="删除字段" @click.stop="remove(field)"><DeleteOutlined /></a-button></a-tooltip>
          </div>
          <ApprovalFieldControl v-if="field.type === 'section'" :field="field" preview />
          <a-form-item v-else :label="field.label" :required="field.required" :extra="field.help">
            <ApprovalFieldControl v-model="previewValues[fieldKey(field)]" :field="field" preview />
          </a-form-item>
        </article>
      </a-form>
    </main>
    <aside class="properties" aria-label="字段属性">
      <a-empty v-if="!selected" description="选择一个字段后编辑属性" />
      <a-form v-else layout="vertical" size="small">
        <a-form-item label="字段名称" :validate-status="selected.label.trim() ? undefined : 'error'" :help="selected.label.trim() ? undefined : '字段名称不能为空'">
          <a-input aria-label="字段名称" :value="selected.label" @update:value="patchField({ label: $event })" />
        </a-form-item>
        <a-form-item label="提示文字"><a-input aria-label="提示文字" :value="selected.placeholder" @update:value="patchField({ placeholder: $event })" /></a-form-item>
        <a-form-item label="帮助说明"><a-textarea aria-label="帮助说明" :value="selected.help" :rows="2" @update:value="patchField({ help: $event })" /></a-form-item>
        <a-form-item><a-checkbox :checked="selected.required" @update:checked="patchField({ required: $event })">必填</a-checkbox></a-form-item>
        <template v-if="choiceTypes.has(selected.type)">
          <a-form-item label="选项" :validate-status="optionError(selected.options) ? 'error' : undefined" :help="optionError(selected.options)">
            <div v-for="(option, index) in selected.options" :key="index" class="option-line"><a-input aria-label="选项" :value="option" @update:value="updateOption(index, $event)" /><a-button type="text" danger aria-label="删除选项" @click="removeOption(index)"><DeleteOutlined /></a-button></div>
            <a-button size="small" aria-label="添加选项" @click="addOption"><PlusOutlined /> 添加选项</a-button>
          </a-form-item>
        </template>
        <template v-if="numericTypes.has(selected.type)">
          <a-form-item label="最小值"><a-input-number aria-label="最小值" :value="selected.min" @update:value="patchField({ min: $event ?? undefined })" /></a-form-item>
          <a-form-item label="最大值"><a-input-number aria-label="最大值" :value="selected.max" @update:value="patchField({ max: $event ?? undefined })" /></a-form-item>
          <a-form-item label="小数位"><a-input-number aria-label="小数位" :min="0" :max="6" :value="selected.precision" @update:value="patchField({ precision: $event ?? undefined })" /></a-form-item>
        </template>
        <template v-if="selected.type === 'detail_table'">
          <a-divider orientation="left">明细列</a-divider>
          <div v-for="column in selected.columns" :key="column.id" class="column-editor">
            <a-input aria-label="明细列编号" :value="column.key" @update:value="patchColumn(column.id, { key: $event.trim() })" />
            <a-input aria-label="明细列名称" :value="column.label" @update:value="patchColumn(column.id, { label: $event })" />
            <a-select aria-label="明细列类型" :value="column.type" :options="columnTypes" @update:value="patchColumn(column.id, { type: $event as DetailColumnType, options: $event === 'select' ? (column.options ?? ['']) : undefined })" />
            <a-checkbox :checked="column.required" aria-label="明细列必填" @update:checked="patchColumn(column.id, { required: $event })">必填</a-checkbox>
            <a-tooltip title="上移"><a-button type="text" aria-label="上移明细列" @click="moveColumn(column, -1)"><ArrowUpOutlined /></a-button></a-tooltip><a-tooltip title="下移"><a-button type="text" aria-label="下移明细列" @click="moveColumn(column, 1)"><ArrowDownOutlined /></a-button></a-tooltip><a-tooltip title="复制"><a-button type="text" aria-label="复制明细列" @click="duplicateColumn(column)"><CopyOutlined /></a-button></a-tooltip><a-tooltip title="删除"><a-button type="text" danger aria-label="删除明细列" @click="removeColumn(column.id)"><DeleteOutlined /></a-button></a-tooltip>
            <template v-if="column.type === 'select'"><div v-for="(option, index) in column.options" :key="index" class="option-line column-options"><a-input aria-label="明细列选项" :value="option" @update:value="updateColumnOption(column, index, $event)" /><a-button type="text" danger aria-label="删除明细列选项" @click="removeColumnOption(column, index)"><DeleteOutlined /></a-button></div><a-form-item :validate-status="optionError(column.options) ? 'error' : undefined" :help="optionError(column.options)"><a-button size="small" aria-label="添加明细列选项" @click="addColumnOption(column)"><PlusOutlined /> 添加明细列选项</a-button></a-form-item></template>
          </div>
          <a-button size="small" aria-label="新增明细列" @click="addColumn"><PlusOutlined /> 新增明细列</a-button>
        </template>
      </a-form>
    </aside>
  </div>
</template>

<style scoped>
.designer { display: grid; grid-template-columns: 190px minmax(320px, 1fr) 270px; min-height: 540px; border: 1px solid #d9d9d9; background: #fff; overflow: hidden; }
.palette, .properties { padding: 16px; background: #fafafa; min-width: 0; } .palette { border-right: 1px solid #f0f0f0; } .properties { border-left: 1px solid #f0f0f0; }
h3 { margin: 0 0 12px; font-size: 14px; } .palette-grid { display: grid; grid-template-columns: 1fr; gap: 8px; } .palette-grid :deep(.ant-btn) { text-align: left; }
.canvas { min-width: 0; padding: 20px; background: #f5f5f5; } .applicant-lock { display: flex; flex-direction: column; gap: 4px; padding: 14px; border: 1px solid #91caff; background: #e6f4ff; } .applicant-lock span { color: #8c8c8c; font-size: 12px; }
.field-list { display: grid; gap: 12px; margin: 16px 0 0; } .design-field { position: relative; min-width: 0; padding: 48px 16px 8px; border: 1px solid #d9d9d9; background: #fff; } .design-field.selected { border-color: #1677ff; box-shadow: 0 0 0 2px #e6f4ff; } .design-field.dragging { opacity: .55; } .design-field :deep(.ant-form-item) { margin-bottom: 12px; } .field-actions { position: absolute; z-index: 1; top: 4px; right: 6px; display: flex; flex: 0 0 auto; padding-left: 8px; background: #fff; }
.option-line, .column-editor { display: flex; gap: 6px; margin-bottom: 8px; align-items: center; flex-wrap: wrap; } .column-editor :deep(.ant-input), .column-editor :deep(.ant-select) { min-width: 120px; flex: 1; } .column-options { width: 100%; }
@media (max-width: 899px) { .designer { grid-template-columns: 1fr; overflow: visible; } .palette, .properties { border: 0; border-bottom: 1px solid #f0f0f0; } .palette-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .canvas { padding: 12px; } .design-field { padding-inline: 12px; } .field-actions { gap: 0; } }
</style>
