<script setup lang="ts">
import { computed } from 'vue'
import dayjs, { type Dayjs } from 'dayjs'
import { PaperClipOutlined } from '@ant-design/icons-vue'
import type { DetailColumn, FormField } from '@/types/approval'

type Value = string | number | string[] | Record<string, unknown>[] | null
type UploadInfo = { fileList: Array<{ uid?: string; name: string; size?: number; type?: string }> }

const props = withDefaults(defineProps<{
  field: FormField
  modelValue?: Value
  readonly?: boolean
  preview?: boolean
}>(), { modelValue: null, readonly: false, preview: false })

const emit = defineEmits<{ 'update:modelValue': [value: Value] }>()

const rows = computed(() => Array.isArray(props.modelValue) && props.modelValue.every((item) => typeof item === 'object')
  ? props.modelValue as Record<string, unknown>[]
  : [])
const attachmentFiles = computed(() => (Array.isArray(props.modelValue) ? props.modelValue : []).map((item, index) => {
  const parsed = attachmentMeta(item)
  return { uid: `${index}-${parsed.name}`, status: 'done' as const, ...parsed }
}))

function columnKey(column: DetailColumn) { return column.id || column.key }
function dateValue(value: unknown) { return typeof value === 'string' && value ? dayjs(value) : undefined }
function rangeValue(value: unknown) { return Array.isArray(value) ? value.map(dateValue).filter(Boolean) as Dayjs[] : undefined }
function emitValue(value: Value) { emit('update:modelValue', value) }
function changeDate(value: Dayjs | null) { emitValue(value?.format('YYYY-MM-DD') || null) }
function changeRange(value: Dayjs[] | null) { emitValue(value?.map((item) => item.format('YYYY-MM-DD')) || null) }
function addRow() { emitValue([...rows.value, {}]) }
function updateRow(rowIndex: number, column: DetailColumn, value: unknown) {
  const next = [...rows.value]
  next[rowIndex] = { ...next[rowIndex], [columnKey(column)]: value }
  emitValue(next)
}
function removeRow(rowIndex: number) { emitValue(rows.value.filter((_, index) => index !== rowIndex)) }
function attachmentChange(info: UploadInfo) {
  emitValue(info.fileList.map((file) => JSON.stringify({ name: file.name, size: file.size ?? 0, type: file.type ?? '' })))
}
function attachmentMeta(value: unknown) {
  if (typeof value !== 'string') return { name: String(value ?? ''), size: 0, type: '' }
  try {
    const parsed = JSON.parse(value) as { name?: string; size?: number; type?: string }
    return { name: parsed.name || value, size: parsed.size ?? 0, type: parsed.type ?? '' }
  } catch {
    return { name: value, size: 0, type: '' }
  }
}
function displayValue(value: Value | undefined) {
  if (value == null || value === '') return '-'
  if (Array.isArray(value)) return value.join('，') || '-'
  return String(value)
}
</script>

<template>
  <h3 v-if="field.type === 'section'" class="form-section">{{ field.label }}</h3>

  <template v-else-if="readonly">
    <a-table v-if="field.type === 'detail_table'" :data-source="rows" :pagination="false" size="small" :scroll="{ x: true }" row-key="__row">
      <a-table-column v-for="column in field.columns || []" :key="columnKey(column)" :title="column.label">
        <template #default="{ record }">{{ displayValue(record[columnKey(column)]) }}</template>
      </a-table-column>
    </a-table>
    <ul v-else-if="field.type === 'attachment'" class="attachment-list">
      <li v-for="file in attachmentFiles" :key="file.uid"><PaperClipOutlined /> {{ file.name }}</li>
      <li v-if="!attachmentFiles.length">-</li>
    </ul>
    <span v-else class="readonly-value">{{ displayValue(modelValue) }}</span>
  </template>

  <a-textarea
    v-else-if="field.type === 'textarea'"
    :value="modelValue as string"
    :placeholder="field.placeholder || `请输入${field.label}`"
    :aria-label="field.label"
    :aria-required="field.required"
    :rows="3"
    @update:value="emitValue($event)"
  />
  <a-input-number
    v-else-if="field.type === 'number' || field.type === 'money'"
    :value="modelValue as number"
    :min="field.min"
    :max="field.max"
    :precision="field.precision"
    :aria-label="field.label"
    :aria-required="field.required"
    style="width: 100%"
    @update:value="emitValue($event)"
  />
  <div v-else-if="field.type === 'date'" role="group" :aria-label="field.label" :aria-required="field.required">
    <a-date-picker
      :value="dateValue(modelValue)"
      :input-read-only="false"
      style="width: 100%"
      @update:value="changeDate($event)"
    />
  </div>
  <div v-else-if="field.type === 'date_range'" role="group" :aria-label="field.label" :aria-required="field.required">
    <a-range-picker
      :value="rangeValue(modelValue)"
      :input-read-only="false"
      style="width: 100%"
      @update:value="changeRange($event)"
    />
  </div>
  <a-radio-group
    v-else-if="field.type === 'radio'"
    :value="modelValue"
    :aria-label="field.label"
    :aria-required="field.required"
    @update:value="emitValue($event)"
  >
    <a-radio v-for="option in field.options || []" :key="option" :value="option">{{ option }}</a-radio>
  </a-radio-group>
  <a-checkbox-group
    v-else-if="field.type === 'checkbox'"
    :value="modelValue as string[]"
    :options="field.options"
    :aria-label="field.label"
    :aria-required="field.required"
    @update:value="emitValue($event)"
  />
  <a-select
    v-else-if="['select', 'user', 'department'].includes(field.type)"
    :value="modelValue"
    :aria-label="field.label"
    :aria-required="field.required"
    allow-clear
    style="width: 100%"
    @update:value="emitValue($event)"
  >
    <a-select-option v-for="option in field.options || []" :key="option" :value="option">{{ option }}</a-select-option>
  </a-select>
  <a-upload
    v-else-if="field.type === 'attachment'"
    :file-list="attachmentFiles"
    :before-upload="() => false"
    @change="attachmentChange"
  >
    <a-button :aria-label="field.label" :aria-required="field.required"><PaperClipOutlined />选择附件</a-button>
  </a-upload>
  <template v-else-if="field.type === 'detail_table'">
    <a-table :data-source="rows" :pagination="false" size="small" :scroll="{ x: true }">
      <a-table-column v-for="column in field.columns || []" :key="columnKey(column)" :title="column.label">
        <template #default="{ record, index }">
          <a-input-number
            v-if="column.type === 'number' || column.type === 'money'"
            :value="record[columnKey(column)] as number"
            :min="column.min"
            :max="column.max"
            :precision="column.precision"
            :aria-label="`${field.label} 第${index + 1}行 ${column.label}`"
            :aria-required="column.required"
            @update:value="updateRow(index, column, $event)"
          />
          <a-date-picker
            v-else-if="column.type === 'date'"
            :value="dateValue(record[columnKey(column)])"
            :aria-label="`${field.label} 第${index + 1}行 ${column.label}`"
            :aria-required="column.required"
            @update:value="updateRow(index, column, $event?.format('YYYY-MM-DD'))"
          />
          <a-select
            v-else-if="column.type === 'select'"
            :value="record[columnKey(column)]"
            :aria-label="`${field.label} 第${index + 1}行 ${column.label}`"
            :aria-required="column.required"
            @update:value="updateRow(index, column, $event)"
          >
            <a-select-option v-for="option in column.options || []" :key="option" :value="option">{{ option }}</a-select-option>
          </a-select>
          <a-input
            v-else
            :value="record[columnKey(column)] as string"
            :aria-label="`${field.label} 第${index + 1}行 ${column.label}`"
            :aria-required="column.required"
            @update:value="updateRow(index, column, $event)"
          />
        </template>
      </a-table-column>
      <a-table-column title="操作" fixed="right" :width="64">
        <template #default="{ index }"><a-button type="text" danger :aria-label="`删除第${index + 1}行`" @click="removeRow(index)">删除</a-button></template>
      </a-table-column>
    </a-table>
    <a-button type="dashed" block class="add-row" @click="addRow">添加明细行</a-button>
  </template>
  <a-input
    v-else
    :value="modelValue as string"
    :placeholder="field.placeholder || `请输入${field.label}`"
    :aria-label="field.label"
    :aria-required="field.required"
    @update:value="emitValue($event)"
  />
</template>

<style scoped>
.form-section { margin: 24px 0 12px; padding-bottom: 8px; border-bottom: 1px solid #d9e2e8; }
.readonly-value { white-space: pre-wrap; }
.attachment-list { display: grid; gap: 4px; margin: 0; padding: 0; list-style: none; }
.add-row { margin-top: 8px; }
:deep(.ant-table-wrapper) { overflow-x: auto; }
</style>
