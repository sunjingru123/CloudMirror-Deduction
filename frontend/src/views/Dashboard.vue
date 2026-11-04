<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'

import { API_BASE_URL } from '@/api/http'
import { fetchHealth } from '@/api/health'
import type { HealthResponse } from '@/api/health'

type ConnectionStatus = 'checking' | 'online' | 'offline'

const status = ref<ConnectionStatus>('checking')
const health = ref<HealthResponse | null>(null)
const errorMessage = ref('')

const statusText = computed(() => {
  if (status.value === 'checking') return '检测中…'
  if (status.value === 'online') return '已连接'
  return '后端未连接'
})

const statusDescription = computed(() => {
  if (status.value === 'checking') return '正在请求后端健康检查接口…'
  if (status.value === 'online') return '后端健康检查返回正常，前后端联调可用。'
  return '未能连接到后端服务，请确认后端已在 8000 端口启动。'
})

async function checkConnection() {
  status.value = 'checking'
  health.value = null
  errorMessage.value = ''

  try {
    const { data } = await fetchHealth()
    health.value = data
    status.value = data.status === 'ok' ? 'online' : 'offline'
  } catch (error) {
    status.value = 'offline'
    errorMessage.value = axios.isAxiosError(error)
      ? error.message
      : '未知错误'
  }
}

onMounted(checkConnection)
</script>

<template>
  <div class="dash">
    <section class="dash-hero">
      <p class="dash-eyebrow">Cloud-Native Fault Propagation &amp; Recovery Optimization</p>
      <h1 class="dash-title">云镜推演</h1>
      <p class="dash-en">CloudMirror Deduction</p>
      <p class="dash-desc">
        面向云原生业务系统的故障传播分析与恢复策略优化平台。
        已完成拓扑管理、故障注入与传播分析、恢复策略对比与推演历史回看，
        页面数据均来自真实后端接口。
      </p>
    </section>

    <section class="dash-status">
      <div class="dash-status-main">
        <span class="dot" :class="status"></span>
        <div>
          <div class="dash-status-title">
            后端连接状态
            <span class="dash-status-value" :class="status">{{ statusText }}</span>
          </div>
          <p class="dash-status-desc">{{ statusDescription }}</p>
        </div>
      </div>

      <div class="dash-status-side">
        <code class="dash-endpoint">{{ API_BASE_URL }}/api/health</code>
        <el-button
          text
          type="primary"
          size="small"
          :loading="status === 'checking'"
          @click="checkConnection"
        >
          重新检测
        </el-button>
      </div>
    </section>

    <section v-if="status === 'online' && health" class="dash-meta">
      <div class="dash-meta-item">
        <span class="dash-meta-label">服务状态</span>
        <span class="dash-meta-value">{{ health.status }}</span>
      </div>
      <div class="dash-meta-item">
        <span class="dash-meta-label">项目名称</span>
        <span class="dash-meta-value">{{ health.project_name }}</span>
      </div>
      <div class="dash-meta-item">
        <span class="dash-meta-label">英文名称</span>
        <span class="dash-meta-value">{{ health.project_name_en }}</span>
      </div>
      <div class="dash-meta-item">
        <span class="dash-meta-label">接口版本</span>
        <span class="dash-meta-value">v{{ health.version }}</span>
      </div>
    </section>

    <section v-else-if="status === 'offline'" class="dash-hint">
      <p>后端未连接。请在后端目录启动服务后重新检测：</p>
      <pre><code>cd backend
.venv\Scripts\activate     # Windows
uvicorn app.main:app --reload</code></pre>
      <p v-if="errorMessage" class="dash-error">错误信息：{{ errorMessage }}</p>
    </section>

    <section class="dash-next">
      <h2 class="dash-section-title">功能模块</h2>
      <p class="dash-section-desc">
        以下模块均已接入后端接口与数据库，可按顺序体验完整的推演流程。
      </p>
      <ul class="dash-list">
        <li>
          <RouterLink to="/topology">系统拓扑</RouterLink>
          <span>基于 Vue Flow 的拓扑编辑器，支持节点与依赖关系的增删改查及持久化。</span>
        </li>
        <li>
          <RouterLink to="/fault-simulation">故障模拟</RouterLink>
          <span>注入与恢复故障，调用后端传播分析算法并在画布中高亮影响范围。</span>
        </li>
        <li>
          <RouterLink to="/recovery">恢复策略</RouterLink>
          <span>对比服务重启、备用节点切换、故障节点隔离三类策略并给出规则推荐。</span>
        </li>
        <li>
          <RouterLink to="/history">历史记录</RouterLink>
          <span>分页回看历史传播分析结果，含故障源与影响节点快照。</span>
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.dash {
  display: flex;
  flex-direction: column;
  gap: 36px;
}

.dash-eyebrow {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 1.6px;
  text-transform: uppercase;
  color: var(--cm-primary);
}

.dash-title {
  margin-top: 12px;
  font-size: 44px;
  font-weight: 800;
  letter-spacing: 2px;
  line-height: 1.1;
}

.dash-en {
  margin-top: 4px;
  font-size: 15px;
  font-weight: 600;
  letter-spacing: 2.4px;
  color: var(--cm-text-muted);
  text-transform: uppercase;
}

.dash-desc {
  margin-top: 16px;
  max-width: 720px;
  font-size: 15px;
  line-height: 1.85;
  color: var(--cm-text-secondary);
}

.dash-status {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 0;
  border-top: 1px solid var(--cm-border);
  border-bottom: 1px solid var(--cm-border);
}

.dash-status-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}

.dot {
  margin-top: 6px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--cm-text-muted);
  box-shadow: 0 0 0 4px rgba(138, 151, 171, 0.16);
  flex-shrink: 0;
}

.dot.online {
  background: var(--cm-success);
  box-shadow: 0 0 0 4px rgba(22, 163, 74, 0.16);
}

.dot.offline {
  background: var(--cm-danger);
  box-shadow: 0 0 0 4px rgba(220, 38, 38, 0.14);
}

.dot.checking {
  background: var(--cm-primary);
  box-shadow: 0 0 0 4px rgba(31, 111, 235, 0.16);
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.45;
  }
}

.dash-status-title {
  font-size: 15px;
  font-weight: 600;
}

.dash-status-value {
  margin-left: 8px;
  font-weight: 700;
}

.dash-status-value.online {
  color: var(--cm-success);
}

.dash-status-value.offline {
  color: var(--cm-danger);
}

.dash-status-value.checking {
  color: var(--cm-primary);
}

.dash-status-desc {
  margin-top: 6px;
  font-size: 13.5px;
  color: var(--cm-text-secondary);
}

.dash-status-side {
  display: flex;
  align-items: center;
  gap: 10px;
}

.dash-endpoint {
  padding: 5px 10px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.04);
  font-size: 12.5px;
  color: var(--cm-text-secondary);
}

.dash-meta {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: 18px 24px;
  margin-top: -12px;
}

.dash-meta-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.dash-meta-label {
  font-size: 12px;
  letter-spacing: 0.4px;
  color: var(--cm-text-muted);
}

.dash-meta-value {
  font-size: 16px;
  font-weight: 600;
}

.dash-hint {
  padding: 18px 20px;
  border-left: 3px solid var(--cm-danger);
  background: rgba(220, 38, 38, 0.04);
  font-size: 13.5px;
  color: var(--cm-text-secondary);
  line-height: 1.8;
}

.dash-hint pre {
  margin: 10px 0;
  padding: 12px 14px;
  overflow-x: auto;
  border-radius: 10px;
  background: rgba(15, 23, 42, 0.05);
  font-size: 12.5px;
  color: var(--cm-text);
}

.dash-error {
  color: var(--cm-danger);
  font-size: 12.5px;
}

.dash-section-title {
  font-size: 18px;
  font-weight: 700;
}

.dash-section-desc {
  margin-top: 8px;
  font-size: 13.5px;
  color: var(--cm-text-secondary);
}

.dash-list {
  margin: 20px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dash-list li {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 10px;
  padding: 14px 2px;
  border-bottom: 1px solid var(--cm-border);
}

.dash-list a {
  font-size: 15px;
  font-weight: 600;
  color: var(--cm-primary);
}

.dash-list a:hover {
  text-decoration: underline;
}

.dash-list span {
  font-size: 13px;
  color: var(--cm-text-muted);
}
</style>
