import { http } from './http'

/** 节点类型。 */
export type NodeType =
  | 'user_entry'
  | 'load_balancer'
  | 'app_server'
  | 'database'
  | 'cache'
  | 'message_queue'
  | 'external_api'

/** 节点状态。 */
export type NodeStatus = 'healthy' | 'faulty' | 'degraded'

export interface TopologySummary {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string
  node_count: number
  edge_count: number
}

export interface TopologyNode {
  id: number
  topology_id: number
  name: string
  type: NodeType
  description: string | null
  status: NodeStatus
  position_x: number
  position_y: number
  created_at: string
  updated_at: string
}

/**
 * 依赖关系。
 * 方向：source_node_id 依赖 target_node_id（source → target）。
 */
export interface TopologyEdge {
  id: number
  topology_id: number
  source_node_id: number
  target_node_id: number
  description: string | null
  created_at: string
}

export interface TopologyDetail {
  id: number
  name: string
  description: string | null
  created_at: string
  updated_at: string
  nodes: TopologyNode[]
  edges: TopologyEdge[]
}

export interface TopologyPayload {
  name: string
  description?: string | null
}

export interface NodeCreatePayload {
  name: string
  type: NodeType
  description?: string | null
  status?: NodeStatus
  position_x?: number
  position_y?: number
}

export type NodeUpdatePayload = Partial<NodeCreatePayload>

export interface EdgeCreatePayload {
  source_node_id: number
  target_node_id: number
  description?: string | null
}

const BASE = '/api/topologies'

export const topologyApi = {
  list: () => http.get<TopologySummary[]>(BASE),
  create: (payload: TopologyPayload) => http.post<TopologySummary>(BASE, payload),
  detail: (id: number) => http.get<TopologyDetail>(`${BASE}/${id}`),
  update: (id: number, payload: Partial<TopologyPayload>) =>
    http.put<TopologySummary>(`${BASE}/${id}`, payload),
  remove: (id: number) => http.delete<void>(`${BASE}/${id}`),

  addNode: (topologyId: number, payload: NodeCreatePayload) =>
    http.post<TopologyNode>(`${BASE}/${topologyId}/nodes`, payload),
  updateNode: (topologyId: number, nodeId: number, payload: NodeUpdatePayload) =>
    http.put<TopologyNode>(`${BASE}/${topologyId}/nodes/${nodeId}`, payload),
  removeNode: (topologyId: number, nodeId: number) =>
    http.delete<void>(`${BASE}/${topologyId}/nodes/${nodeId}`),

  addEdge: (topologyId: number, payload: EdgeCreatePayload) =>
    http.post<TopologyEdge>(`${BASE}/${topologyId}/edges`, payload),
  removeEdge: (topologyId: number, edgeId: number) =>
    http.delete<void>(`${BASE}/${topologyId}/edges/${edgeId}`),
}
