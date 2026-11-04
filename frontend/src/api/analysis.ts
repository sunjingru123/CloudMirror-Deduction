import { http } from './http'
import type { FaultSeverity, FaultType } from './fault'

/** 影响等级：直接 / 间接。 */
export type ImpactLevel = 'direct' | 'indirect'

/** 传播路径中的一步。 */
export interface PathStep {
  node_id: number | null
  node_name: string
}

/** 参与分析的故障源快照。 */
export interface FaultSource {
  fault_id: number | null
  source_node_id: number | null
  source_node_name: string
  fault_type: FaultType
  severity: FaultSeverity
}

/** 单个受影响节点的影响详情。 */
export interface AffectedNode {
  node_id: number | null
  node_name: string
  impact_level: ImpactLevel
  distance: number
  source_fault_id: number | null
  source_node_id: number | null
  propagation_path: PathStep[]
}

/** 一条完整传播路径。 */
export interface PropagationPath {
  source_fault_id: number | null
  source_node_id: number | null
  target_node_id: number | null
  target_node_name: string
  distance: number
  steps: PathStep[]
}

/** 一次传播分析的完整结果。 */
export interface AnalysisResult {
  analysis_id: number
  topology_id: number
  fault_sources: FaultSource[]
  affected_nodes: AffectedNode[]
  direct_affected_count: number
  indirect_affected_count: number
  total_affected_count: number
  total_node_count: number
  impact_ratio: number
  propagation_paths: PropagationPath[]
  analysis_time: string
}

const TOPOLOGY_BASE = '/api/topologies'

export const analysisApi = {
  /** 执行传播分析；不传 faultIds 时分析全部激活故障。 */
  analyze: (topologyId: number, faultIds?: number[]) =>
    http.post<AnalysisResult>(`${TOPOLOGY_BASE}/${topologyId}/analyze`, {
      fault_ids: faultIds ?? null,
    }),
  latest: (topologyId: number) =>
    http.get<AnalysisResult>(`${TOPOLOGY_BASE}/${topologyId}/analysis/latest`),
}
