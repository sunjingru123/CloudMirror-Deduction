import type {
  RecoveryStrategyType,
  ResourceCost,
  RiskLevel,
  ScoringWeights,
} from '@/api/recovery'

export interface LabeledMeta<T extends string> {
  value: T
  label: string
  color: string
}

/** 策略类型元数据（顺序即对比展示顺序）。 */
export const STRATEGY_TYPE_METAS: LabeledMeta<RecoveryStrategyType>[] = [
  { value: 'restart_service', label: '服务重启', color: '#1f6feb' },
  { value: 'failover', label: '备用节点切换', color: '#0d9488' },
  { value: 'isolate_node', label: '故障节点隔离', color: '#7c3aed' },
]

/** 资源成本等级。 */
export const RESOURCE_COSTS: LabeledMeta<ResourceCost>[] = [
  { value: 'low', label: '低', color: '#16a34a' },
  { value: 'medium', label: '中', color: '#f59e0b' },
  { value: 'high', label: '高', color: '#dc2626' },
]

/** 风险等级。 */
export const RISK_LEVELS: LabeledMeta<RiskLevel>[] = [
  { value: 'low', label: '低', color: '#16a34a' },
  { value: 'medium', label: '中', color: '#f59e0b' },
  { value: 'high', label: '高', color: '#dc2626' },
]

const STRATEGY_TYPE_MAP = new Map(STRATEGY_TYPE_METAS.map((item) => [item.value, item]))
const RESOURCE_COST_MAP = new Map(RESOURCE_COSTS.map((item) => [item.value, item]))
const RISK_LEVEL_MAP = new Map(RISK_LEVELS.map((item) => [item.value, item]))

export function strategyTypeMeta(type: RecoveryStrategyType): LabeledMeta<RecoveryStrategyType> {
  return (
    STRATEGY_TYPE_MAP.get(type) ?? { value: type, label: type, color: '#64748b' }
  )
}

export function resourceCostMeta(cost: ResourceCost): LabeledMeta<ResourceCost> {
  return RESOURCE_COST_MAP.get(cost) ?? { value: cost, label: cost, color: '#64748b' }
}

export function riskLevelMeta(risk: RiskLevel): LabeledMeta<RiskLevel> {
  return RISK_LEVEL_MAP.get(risk) ?? { value: risk, label: risk, color: '#64748b' }
}

/** 评分权重展示顺序与中文名。 */
export const SCORING_WEIGHT_LABELS: { key: keyof ScoringWeights; label: string }[] = [
  { key: 'recovery_time', label: '恢复时间' },
  { key: 'impact', label: '影响范围' },
  { key: 'cost', label: '资源成本' },
  { key: 'risk', label: '操作风险' },
  { key: 'business_recovery', label: '业务恢复程度' },
]
