import axios from 'axios'

/** 后端 API 基础地址，可通过 VITE_API_BASE_URL 覆盖。 */
export const API_BASE_URL: string =
  import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

export const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 5000,
  headers: {
    'Content-Type': 'application/json',
  },
})
