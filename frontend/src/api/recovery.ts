import { http } from './http'

/** 恢复策略类型。 */
export type RecoveryStrategyType = 'restart_service' | 'failover' | 'isolate_node'

/** 估算资源成本等级。 */
export type ResourceCost = 'low' | 'medium' | 'high'

/** 操作风险等级。 */
export type RiskLevel = 'low' | 'medium' | 'high'

/** 单项前置条件检查结果（目前仅 failover 使用）。 */
export interface PrerequisiteCheck {
  check_name: string
  passed: boolean
  detail: string
}

/**
 * 一个被评估的备用节点候选。
 *
 * `eligible=true` 仅表示当前模拟模型的规则判定它满足切换前提，
 * 不代表真实生产环境已验证容量、网络、数据同步与配置一致性。
 */
export interface StandbyCandidate {
  node_id: number | null
  node_name: string
  /** 数值越小优先级越高 */
  priority: number | null
  eligible: boolean
  detail: string
}

/** 单个策略的评估结果。 */
export interface RecoveryStrategy {
  strategy_id: number
  strategy_type: RecoveryStrategyType
  strategy_name: string
  description: string
  applicable: boolean
  inapplicable_reason: string | null
  /** 估算恢复时间（秒，模拟估算值） */
  estimated_recovery_time: number
  /** 估算需停机或短暂失去服务的节点数量 */
  estimated_affected_nodes: number
  estimated_resource_cost: ResourceCost
  risk_level: RiskLevel
  advantages: string[]
  disadvantages: string[]
  prerequisites: string[]
  /** 规则加权评分（0-100，模拟估算值） */
  recommendation_score: number

  /* --- 仅 failover 会填充的显式冗余字段 --- */
  redundancy_group_id: number | null
  redundancy_group_name: string | null
  primary_node_id: number | null
  selected_standby_node_id: number | null
  standby_candidates: StandbyCandidate[]
  selection_reason: string | null
  prerequisite_checks: PrerequisiteCheck[]
}

/** 一次恢复策略推荐的完整结果。 */
export interface RecoveryRecommendation {
  plan_id: number
  analysis_id: number
  topology_id: number
  strategies: RecoveryStrategy[]
  recommended_strategy_id: number | null
  recommended_strategy_type: RecoveryStrategyType | null
  recommendation_reason: string
  estimation_notice: string
  created_at: string
}

/** 策略类型配置说明。 */
export interface StrategyTypeInfo {
  strategy_type: RecoveryStrategyType
  strategy_name: string
  description: string
  base_recovery_seconds: number
  per_node_seconds: number
  base_resource_cost: ResourceCost
  base_risk_level: RiskLevel
  prerequisites: string[]
  notes: string[]
}

/** 评分权重（合计 1.00）。 */
export interface ScoringWeights {
  recovery_time: number
  impact: number
  cost: number
  risk: number
  business_recovery: number
}

/** 策略类型与评分配置。 */
export interface StrategyConfig {
  topology_id: number
  strategy_types: StrategyTypeInfo[]
  scoring_weights: ScoringWeights
  reference_recovery_seconds: number
  estimation_notice: string
}

const TOPOLOGY_BASE = '/api/topologies'

export const recoveryApi = {
  /** 生成恢复策略并获取推荐；不传 analysisId 时使用最近一次分析。 */
  recommend: (topologyId: number, analysisId?: number | null) =>
    http.post<RecoveryRecommendation>(
      `${TOPOLOGY_BASE}/${topologyId}/recovery/recommend`,
      { analysis_id: analysisId ?? null },
    ),
  /** 查询策略类型与评分配置。 */
  strategies: (topologyId: number) =>
    http.get<StrategyConfig>(`${TOPOLOGY_BASE}/${topologyId}/recovery/strategies`),
}
