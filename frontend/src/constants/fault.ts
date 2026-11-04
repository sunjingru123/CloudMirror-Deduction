import type { FaultSeverity, FaultStatus, FaultType } from '@/api/fault'
import type { ImpactLevel } from '@/api/analysis'

export interface FaultTypeMeta {
  value: FaultType
  label: string
  /** 简要说明，用于表单提示。 */
  hint: string
}

export interface LabeledMeta<T extends string> {
  value: T
  label: string
  color: string
}

/** 故障类型元数据。 */
export const FAULT_TYPES: FaultTypeMeta[] = [
  { value: 'node_down', label: '节点宕机', hint: '节点完全不可用' },
  { value: 'service_unavailable', label: '服务不可用', hint: '服务返回错误' },
  { value: 'network_latency', label: '网络延迟', hint: '响应变慢' },
  { value: 'network_unreachable', label: '网络不可达', hint: '网络中断' },
]

/** 故障严重程度。 */
export const FAULT_SEVERITIES: LabeledMeta<FaultSeverity>[] = [
  { value: 'low', label: '低', color: '#0ea5e9' },
  { value: 'medium', label: '中', color: '#f59e0b' },
  { value: 'high', label: '高', color: '#f97316' },
  { value: 'critical', label: '严重', color: '#dc2626' },
]

/** 故障状态。 */
export const FAULT_STATUSES: LabeledMeta<FaultStatus>[] = [
  { value: 'active', label: '激活', color: '#dc2626' },
  { value: 'recovered', label: '已恢复', color: '#16a34a' },
]

/** 传播影响等级及其可视化配色。 */
export const IMPACT_LEVELS: LabeledMeta<ImpactLevel>[] = [
  { value: 'direct', label: '直接影响', color: '#f97316' },
  { value: 'indirect', label: '间接影响', color: '#eab308' },
]

/** 故障源高亮色（与影响等级区分）。 */
export const FAULT_SOURCE_COLOR = '#dc2626'

/** 传播高亮类型：故障源 / 直接影响 / 间接影响。 */
export type NodeImpact = 'fault_source' | ImpactLevel

const FAULT_TYPE_MAP = new Map(FAULT_TYPES.map((item) => [item.value, item]))
const FAULT_SEVERITY_MAP = new Map(FAULT_SEVERITIES.map((item) => [item.value, item]))
const FAULT_STATUS_MAP = new Map(FAULT_STATUSES.map((item) => [item.value, item]))
const IMPACT_LEVEL_MAP = new Map(IMPACT_LEVELS.map((item) => [item.value, item]))

export function faultTypeLabel(type: FaultType): string {
  return FAULT_TYPE_MAP.get(type)?.label ?? type
}

export function faultSeverityMeta(severity: FaultSeverity): LabeledMeta<FaultSeverity> {
  return FAULT_SEVERITY_MAP.get(severity) ?? { value: severity, label: severity, color: '#64748b' }
}

export function faultStatusMeta(status: FaultStatus): LabeledMeta<FaultStatus> {
  return FAULT_STATUS_MAP.get(status) ?? { value: status, label: status, color: '#64748b' }
}

export function impactLevelMeta(level: ImpactLevel): LabeledMeta<ImpactLevel> {
  return IMPACT_LEVEL_MAP.get(level) ?? { value: level, label: level, color: '#64748b' }
}
