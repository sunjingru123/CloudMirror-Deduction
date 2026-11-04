import type { NodeStatus, NodeType } from '@/api/topology'

export interface NodeTypeMeta {
  value: NodeType
  label: string
  color: string
}

export interface NodeStatusMeta {
  value: NodeStatus
  label: string
  color: string
}

/** 节点类型元数据（顺序即工具条展示顺序）。 */
export const NODE_TYPES: NodeTypeMeta[] = [
  { value: 'user_entry', label: '用户入口', color: '#6366f1' },
  { value: 'load_balancer', label: '负载均衡器', color: '#0ea5e9' },
  { value: 'app_server', label: '应用服务器', color: '#1f6feb' },
  { value: 'database', label: '数据库', color: '#0d9488' },
  { value: 'cache', label: '缓存', color: '#f59e0b' },
  { value: 'message_queue', label: '消息队列', color: '#a855f7' },
  { value: 'external_api', label: '外部 API', color: '#64748b' },
]

/** 节点状态元数据。 */
export const NODE_STATUSES: NodeStatusMeta[] = [
  { value: 'healthy', label: '正常', color: '#16a34a' },
  { value: 'faulty', label: '故障', color: '#dc2626' },
  { value: 'degraded', label: '降级', color: '#f59e0b' },
]

const NODE_TYPE_MAP = new Map(NODE_TYPES.map((item) => [item.value, item]))
const NODE_STATUS_MAP = new Map(NODE_STATUSES.map((item) => [item.value, item]))

export function nodeTypeMeta(type: NodeType): NodeTypeMeta {
  return NODE_TYPE_MAP.get(type) ?? { value: type, label: type, color: '#64748b' }
}

export function nodeStatusMeta(status: NodeStatus): NodeStatusMeta {
  return NODE_STATUS_MAP.get(status) ?? { value: status, label: status, color: '#64748b' }
}

export function nodeTypeLabel(type: NodeType): string {
  return nodeTypeMeta(type).label
}

export function nodeStatusLabel(status: NodeStatus): string {
  return nodeStatusMeta(status).label
}
