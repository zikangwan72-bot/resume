export interface UserProfile {
  id: string
  email: string
  display_name: string
  department: string
  role: string
  permissions: string[]
}

export interface ModuleSummary {
  key: string
  name: string
  short_name: string
  description: string
  planned_ai: string[]
  permission: string
  accent: 'cyan' | 'orange' | 'green' | 'blue'
  status: string
  stage?: string
  message?: string
}

export interface HealthStatus {
  status: string
  app: string
  database: string
  supabase: string
  ai: string
  timestamp: string
}

export interface PendingItem {
  node_id: number
  node_index: number
  request: {
    id: number
    type_id: number
    applicant_name: string
    title: string
    status: string
    current_node_index: number
    created_at: string
  }
}

export type {
  ApiEnvelope,
  ApprovalAction,
  ApprovalNode,
  ApprovalRequestDetail,
  ApprovalType,
  ApprovalUser,
  FlowNodeDef,
  FormField,
} from './types/approval'
