import { http } from './http'

/** 冗余模式。 */
export type RedundancyType = 'active_standby' | 'active_active' | 'manual_standby'

/** 冗余成员角色。 */
export type MemberRole = 'primary' | 'standby' | 'active'

/** 冗余成员。 */
export interface RedundancyMember {
  id: number
  redundancy_group_id: number
  node_id: number
  node_name: string
  member_role: MemberRole
  /** 备用优先级：数值越小优先级越高（主备 / 手动备用模式下备用节点必填） */
  priority: number | null
  created_at: string
}

/**
 * 冗余组。
 *
 * 与依赖关系（`TopologyEdge`）语义不同：冗余关系描述「谁能顶替谁」，
 * 是恢复策略 failover 的输入；依赖关系描述业务调用方向，是故障传播分析的输入。
 */
export interface RedundancyGroup {
  id: number
  topology_id: number
  name: string
  redundancy_type: RedundancyType
  description: string | null
  members: RedundancyMember[]
  created_at: string
  updated_at: string
}

/** 成员创建 / 更新负载。 */
export interface RedundancyMemberPayload {
  node_id: number
  member_role: MemberRole
  priority?: number | null
}

/** 冗余组创建 / 更新负载（一次提交完整成员）。 */
export interface RedundancyGroupPayload {
  name: string
  redundancy_type: RedundancyType
  description?: string | null
  members: RedundancyMemberPayload[]
}

const TOPOLOGY_BASE = '/api/topologies'
const GROUP_BASE = '/api/redundancy-groups'

export const redundancyApi = {
  /** 查询拓扑的冗余组列表。 */
  list: (topologyId: number) =>
    http.get<RedundancyGroup[]>(`${TOPOLOGY_BASE}/${topologyId}/redundancy-groups`),
  /** 创建冗余组（一次请求提交完整主备结构）。 */
  create: (topologyId: number, payload: RedundancyGroupPayload) =>
    http.post<RedundancyGroup>(`${TOPOLOGY_BASE}/${topologyId}/redundancy-groups`, payload),
  /** 查询冗余组详情。 */
  detail: (groupId: number) => http.get<RedundancyGroup>(`${GROUP_BASE}/${groupId}`),
  /** 更新冗余组。 */
  update: (groupId: number, payload: Partial<RedundancyGroupPayload>) =>
    http.put<RedundancyGroup>(`${GROUP_BASE}/${groupId}`, payload),
  /** 删除冗余组。 */
  remove: (groupId: number) => http.delete<void>(`${GROUP_BASE}/${groupId}`),
}
