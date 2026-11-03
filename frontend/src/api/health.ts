import { http } from './http'

/** 后端 /api/health 响应结构。 */
export interface HealthResponse {
  status: string
  project_name: string
  project_name_en: string
  version: string
}

/** 请求后端健康检查接口。 */
export function fetchHealth() {
  return http.get<HealthResponse>('/api/health')
}
