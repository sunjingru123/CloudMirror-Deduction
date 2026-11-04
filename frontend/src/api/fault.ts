import { http } from './http'

/** 故障类型。 */
export type FaultType =
  | 'node_down'
  | 'service_unavailable'
  | 'network_latency'
  | 'network_unreachable'

/** 故障严重程度。 */
export type FaultSeverity = 'low' | 'medium' | 'high' | 'critical'

/** 故障状态。 */
export type FaultStatus = 'active' | 'recovered'

/** 故障事件。 */
export interface FaultEvent {
  id: number
  topology_id: number
  source_node_id: number
  source_node_name: string | null
  fault_type: FaultType
  severity: FaultSeverity
  description: string | null
  status: FaultStatus
  created_at: string
  recovered_at: string | null
}

export interface FaultCreatePayload {
  source_node_id: number
  fault_type: FaultType
  severity?: FaultSeverity
  description?: string | null
}

const TOPOLOGY_BASE = '/api/topologies'
const FAULT_BASE = '/api/faults'

export const faultApi = {
  list: (topologyId: number) => http.get<FaultEvent[]>(`${TOPOLOGY_BASE}/${topologyId}/faults`),
  create: (topologyId: number, payload: FaultCreatePayload) =>
    http.post<FaultEvent>(`${TOPOLOGY_BASE}/${topologyId}/faults`, payload),
  detail: (faultId: number) => http.get<FaultEvent>(`${FAULT_BASE}/${faultId}`),
  recover: (faultId: number) => http.post<FaultEvent>(`${FAULT_BASE}/${faultId}/recover`),
}
