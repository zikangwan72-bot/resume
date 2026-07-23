<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  ArrowDownOutlined, ArrowUpOutlined, CopyOutlined, DeleteOutlined, PlusOutlined,
} from '@ant-design/icons-vue'
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
const selected = computed(() => props.modelValue.fields.find((field) => field.id === selectedId.value) ?? null)
const fieldId = () => crypto.randomUUID()

function defaultField(type: FieldType): FormField {
  const label = palette.find((item) => item.type === type)?.label ?? '字段'
  return { id: fieldId(), key: `field_${Date.now()}`, label, type, required: false, options: choiceTypes.has(type) ? ['选项 1'] : undefined, columns: type === 'detail_table' ? [] : undefined }
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
  const copy = { ...field, id: fieldId(), key: `${field.key}_copy`, label: `${field.label}（副本）`, options: field.options ? [...field.options] : undefined, columns: field.columns?.map((column) => ({ ...column, id: fieldId(), options: column.options ? [...column.options] : undefined })) }
  const index = props.modelValue.fields.indexOf(field)
  update([...props.modelValue.fields.slice(0, index + 1), copy, ...props.modelValue.fields.slice(index + 1)])
  selectedId.value = copy.id
}
function remove(field: FormField) { update(props.modelValue.fields.filter((item) => item.id !== field.id)); if (selectedId.value === field.id) selectedId.value = null }
function move(field: FormField, direction: -1 | 1) {
  const index = props.modelValue.fields.indexOf(field); const target = index + direction
  if (target < 0 || target >= props.modelValue.fields.length) return
  const fields = [...props.modelValue.fields]; [fields[index], fields[target]] = [fields[target], fields[index]]; update(fields)
}
function updateOption(index: number, value: string) { if (selected.value) patchField({ options: (selected.value.options ?? []).map((option, itemIndex) => itemIndex === index ? value : option) }) }
function addOption() { if (selected.value) patchField({ options: [...(selected.value.options ?? []), `选项 ${(selected.value.options?.length ?? 0) + 1}`] }) }
function removeOption(index: number) { if (selected.value) patchField({ options: (selected.value.options ?? []).filter((_, itemIndex) => itemIndex !== index) }) }
function addColumn() { if (selected.value) patchField({ columns: [...(selected.value.columns ?? []), { id: fieldId(), label: '明细列', type: 'text', required: false }] }) }
function patchColumn(id: string, patch: Partial<DetailColumn>) { if (selected.value) patchField({ columns: (selected.value.columns ?? []).map((column) => column.id === id ? { ...column, ...patch } : column) }) }
function removeColumn(id: string) { if (selected.value) patchField({ columns: (selected.value.columns ?? []).filter((column) => column.id !== id) }) }
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
      <ul v-else class="field-list" aria-label="业务字段">
        <li v-for="(field, index) in modelValue.fields" :key="field.id" :data-field-id="field.id" :class="['field-row', { selected: selectedId === field.id }]" @click="selectedId = field.id">
          <div class="field-copy"><strong>{{ field.label }}</strong><span>{{ field.type }}</span></div>
          <div class="field-actions">
            <a-tooltip title="上移"><a-button type="text" :disabled="index === 0" aria-label="上移字段" @click.stop="move(field, -1)"><ArrowUpOutlined /></a-button></a-tooltip>
            <a-tooltip title="下移"><a-button type="text" :disabled="index === modelValue.fields.length - 1" aria-label="下移字段" @click.stop="move(field, 1)"><ArrowDownOutlined /></a-button></a-tooltip>
            <a-tooltip title="复制"><a-button type="text" aria-label="复制字段" @click.stop="duplicate(field)"><CopyOutlined /></a-button></a-tooltip>
            <a-tooltip title="删除"><a-button type="text" danger aria-label="删除字段" @click.stop="remove(field)"><DeleteOutlined /></a-button></a-tooltip>
          </div>
        </li>
      </ul>
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
          <a-form-item label="选项" :validate-status="selected.options?.filter(Boolean).length ? undefined : 'error'" :help="selected.options?.filter(Boolean).length ? undefined : '至少保留一个选项'">
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
            <a-input aria-label="明细列名称" :value="column.label" @update:value="patchColumn(column.id, { label: $event })" />
            <a-select aria-label="明细列类型" :value="column.type" :options="columnTypes" @update:value="patchColumn(column.id, { type: $event as DetailColumnType })" />
            <a-button type="text" danger aria-label="删除明细列" @click="removeColumn(column.id)"><DeleteOutlined /></a-button>
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
.canvas { min-width: 0; padding: 20px; background: #f5f5f5; } .applicant-lock { display: flex; flex-direction: column; gap: 4px; padding: 14px; border: 1px solid #91caff; background: #e6f4ff; } .applicant-lock span, .field-copy span { color: #8c8c8c; font-size: 12px; }
.field-list { display: grid; gap: 10px; padding: 0; margin: 16px 0 0; list-style: none; } .field-row { display: flex; min-height: 58px; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border: 1px solid #d9d9d9; background: #fff; cursor: pointer; } .field-row.selected { border-color: #1677ff; box-shadow: 0 0 0 2px #e6f4ff; } .field-copy { display: grid; gap: 2px; min-width: 0; } .field-actions { display: flex; flex: 0 0 auto; }
.option-line, .column-editor { display: flex; gap: 6px; margin-bottom: 8px; align-items: center; } .column-editor :deep(.ant-input), .column-editor :deep(.ant-select) { min-width: 0; flex: 1; }
@media (max-width: 760px) { .designer { grid-template-columns: 1fr; overflow: visible; } .palette, .properties { border: 0; border-bottom: 1px solid #f0f0f0; } .palette-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .canvas { padding: 12px; } .field-actions { gap: 0; } }
</style>
