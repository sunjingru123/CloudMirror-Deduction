import axios from 'axios'

/** 从 Axios 错误中提取可读的中文提示。 */
export function extractErrorMessage(error: unknown, fallback = '请求失败'): string {
  if (axios.isAxiosError(error)) {
    if (!error.response) {
      return '无法连接到后端服务，请确认后端已启动'
    }

    const detail = (error.response.data as { detail?: unknown } | undefined)?.detail

    if (typeof detail === 'string' && detail.length > 0) {
      return detail
    }

    // FastAPI 校验错误（422）为数组结构
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item
            ? String((item as { msg: unknown }).msg)
            : String(item),
        )
        .join('；')
      if (messages) return messages
    }

    return `${error.message}（HTTP ${error.response.status}）`
  }

  if (error instanceof Error) {
    return error.message
  }

  return fallback
}
