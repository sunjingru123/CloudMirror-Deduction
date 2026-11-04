<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { topologyApi } from '@/api/topology'
import type { TopologySummary } from '@/api/topology'
import { analysisApi } from '@/api/analysis'
import type { AnalysisHistoryItem, AnalysisResult } from '@/api/analysis'
import { extractErrorMessage } from '@/api/errors'
import { impactLevelMeta, faultSeverityMeta, faultTypeLabel } from '@/constants/fault'

// --------------------------------------------------------------------------- //
// 列表状态
// --------------------------------------------------------------------------- //
const topologies = ref<TopologySummary[]>([])
const topologyId = ref<number | null>(null)
const items = ref<AnalysisHistoryItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)

const loadingTopologies = ref(false)
const loadingList = ref(false)
const loadError = ref('')

// --------------------------------------------------------------------------- //
// 详情状态
// --------------------------------------------------------------------------- //
const detailVisible = ref(false)
const detailLoading = ref(false)
const detailError = ref('')
const detail = ref<AnalysisResult | null>(null)

const hasTopology = computed(() => topologyId.value !== null)
const currentTopologyName = computed(
  () => topologies.value.find((item) => item.id === topologyId.value)?.name ?? '',
)

const detailMetrics = computed(() => {
  if (!detail.value) return []
  return [
    { label: '故障源', value: String(detail.value.fault_sources.length), tone: 'danger' },
    { label: '受影响节点', value: String(detail.value.total_affected_count), tone: 'normal' },
    { label: '直接影响', value: String(detail.value.direct_affected_count), tone: 'warn' },
    { label: '间接影响', value: String(detail.value.indirect_affected_count), tone: 'muted' },
    {
      label: '影响比例',
      value: `${(detail.value.impact_ratio * 100).toFixed(1)}%`,
      tone: 'primary',
    },
  ]
})

const detailAffectedNodes = computed(() =>
  detail.value
    ? [...detail.value.affected_nodes].sort(
        (a, b) => a.distance - b.distance || (a.node_id ?? 0) - (b.node_id ?? 0),
      )
    : [],
)

// --------------------------------------------------------------------------- //
// 工具函数
// --------------------------------------------------------------------------- //
function formatTime(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const pad = (input: number) => String(input).padStart(2, '0')
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
  )
}

function percent(value: number): string {
  return `${(value * 100).toFixed(1)}%`
}

function pathText(steps: { node_name: string }[]): string {
  return steps.map((step) => step.node_name).join(' → ')
}

// --------------------------------------------------------------------------- //
// 加载
// --------------------------------------------------------------------------- //
async function loadTopologies() {
  loadingTopologies.value = true
  loadError.value = ''
  try {
    const { data } = await topologyApi.list()
    topologies.value = data
    if (topologyId.value === null && data.length > 0) {
      topologyId.value = data[0].id
      await loadPage(1)
    }
  } catch (error) {
    loadError.value = extractErrorMessage(error, '加载拓扑列表失败')
  } finally {
    loadingTopologies.value = false
  }
}

async function loadPage(targetPage: number) {
  if (topologyId.value === null) {
    items.value = []
    total.value = 0
    return
  }
  loadingList.value = true
  loadError.value = ''
  try {
    const { data } = await analysisApi.history(topologyId.value, targetPage, pageSize.value)
    items.value = data.items
    total.value = data.total
    page.value = data.page
  } catch (error) {
    items.value = []
    total.value = 0
    loadError.value = extractErrorMessage(error, '加载历史分析记录失败')
  } finally {
    loadingList.value = false
  }
}

function onTopologyChange() {
  page.value = 1
  void loadPage(1)
}

function onPageChange(targetPage: number) {
  void loadPage(targetPage)
}

function onPageSizeChange(size: number) {
  pageSize.value = size
  void loadPage(1)
}

function refresh() {
  void loadPage(page.value)
}

// --------------------------------------------------------------------------- //
// 详情
// --------------------------------------------------------------------------- //
async function openDetail(row: AnalysisHistoryItem) {
  if (topologyId.value === null) return
  detailVisible.value = true
  detailLoading.value = true
  detailError.value = ''
  detail.value = null
  try {
    const { data } = await analysisApi.detail(topologyId.value, row.analysis_id)
    detail.value = data
  } catch (error) {
    detailError.value = extractErrorMessage(error, '加载分析详情失败')
    ElMessage.error(detailError.value)
  } finally {
    detailLoading.value = false
  }
}

onMounted(loadTopologies)
</script>

<template>
  <div class="ht">
    <header class="cm-page-header">
      <h1 class="cm-page-title">历史记录</h1>
      <p class="cm-page-subtitle">
        回溯历次故障传播分析结果。记录保存了当时的故障源与影响节点快照，
        故障恢复或节点删除后仍可完整查看。列表与分页均调用真实后端接口。
      </p>
    </header>

    <div class="ht-toolbar">
      <div class="ht-toolbar-item">
        <span class="ht-toolbar-label">目标拓扑</span>
        <el-select
          v-model="topologyId"
          class="ht-select"
          placeholder="请选择拓扑"
          :loading="loadingTopologies"
          @change="onTopologyChange"
        >
          <el-option
            v-for="item in topologies"
            :key="item.id"
            :label="`${item.name}（${item.node_count} 节点 / ${item.edge_count} 依赖）`"
            :value="item.id"
          />
        </el-select>
      </div>
      <div class="ht-toolbar-actions">
        <el-button :loading="loadingList || loadingTopologies" :disabled="!hasTopology" @click="refresh">
          刷新
        </el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="ht-alert"
    >
      <template #default>
        <span>请确认后端服务已启动，然后点击「刷新」重试。</span>
      </template>
    </el-alert>

    <el-empty v-if="!loadingTopologies && topologies.length === 0" description="暂无拓扑">
      <template #description>
        <p class="ht-empty-title">暂无拓扑</p>
        <p class="ht-empty-sub">请先前往「系统拓扑」页面创建拓扑与依赖关系。</p>
      </template>
    </el-empty>

    <template v-else>
      <div class="ht-summary">
        <span class="ht-summary-name">{{ currentTopologyName || '未选择拓扑' }}</span>
        <span class="ht-summary-count">共 {{ total }} 条分析记录</span>
      </div>

      <el-empty
        v-if="!loadingList && items.length === 0 && total === 0"
        description="暂无历史记录"
      >
        <template #description>
          <p class="ht-empty-title">暂无历史记录</p>
          <p class="ht-empty-sub">
            该拓扑尚未执行过传播分析。请前往「故障模拟」注入故障并执行分析。
          </p>
        </template>
      </el-empty>

      <template v-else>
        <div class="ht-table">
          <div class="ht-row ht-row-head">
            <span>分析时间</span>
            <span>拓扑名称</span>
            <span class="ht-num">故障源</span>
            <span class="ht-num">直接影响</span>
            <span class="ht-num">间接影响</span>
            <span class="ht-num">总影响</span>
            <span class="ht-ratio-col">影响比例</span>
            <span class="ht-action-col">操作</span>
          </div>

          <div v-for="row in items" :key="row.analysis_id" class="ht-row">
            <span class="ht-time">{{ formatTime(row.analysis_time) }}</span>
            <span class="ht-name">{{ row.topology_name }}</span>
            <span class="ht-num">{{ row.fault_source_count }}</span>
            <span class="ht-num">{{ row.direct_affected_count }}</span>
            <span class="ht-num">{{ row.indirect_affected_count }}</span>
            <span class="ht-num ht-num-strong">{{ row.total_affected_count }}</span>
            <span class="ht-ratio-col">
              <span class="ht-ratio-bar">
                <span
                  class="ht-ratio-fill"
                  :style="{ width: `${Math.min(100, row.impact_ratio * 100)}%` }"
                ></span>
              </span>
              <span class="ht-ratio-text">{{ percent(row.impact_ratio) }}</span>
            </span>
            <span class="ht-action-col">
              <el-button text type="primary" size="small" @click="openDetail(row)">
                查看详情
              </el-button>
            </span>
          </div>
        </div>

        <div class="ht-pagination">
          <el-pagination
            :current-page="page"
            :page-size="pageSize"
            :total="total"
            :page-sizes="[10, 20, 50]"
            layout="total, sizes, prev, pager, next"
            background
            @current-change="onPageChange"
            @size-change="onPageSizeChange"
          />
        </div>
      </template>
    </template>

    <el-dialog v-model="detailVisible" title="分析详情" width="760px" top="6vh">
      <div v-loading="detailLoading" class="ht-detail">
        <el-alert
          v-if="detailError"
          type="error"
          :title="detailError"
          show-icon
          :closable="false"
        />
        <template v-if="detail">
          <div class="ht-detail-meta">
            <span class="ht-detail-id">分析 #{{ detail.analysis_id }}</span>
            <span class="ht-detail-time">{{ formatTime(detail.analysis_time) }}</span>
          </div>

          <div class="ht-detail-metrics">
            <div v-for="item in detailMetrics" :key="item.label" class="ht-detail-metric">
              <span class="ht-detail-value" :class="`is-${item.tone}`">{{ item.value }}</span>
              <span class="ht-detail-label">{{ item.label }}</span>
            </div>
          </div>

          <section class="ht-detail-section">
            <h3 class="ht-detail-title">故障源</h3>
            <p v-if="detail.fault_sources.length === 0" class="ht-muted">
              本次分析没有激活故障源。
            </p>
            <ul v-else class="ht-source-list">
              <li v-for="(source, index) in detail.fault_sources" :key="`src-${index}`">
                <span class="ht-source-name">{{ source.source_node_name }}</span>
                <span class="ht-source-meta">
                  {{ faultTypeLabel(source.fault_type) }} ·
                  {{ faultSeverityMeta(source.severity).label }}
                </span>
              </li>
            </ul>
          </section>

          <section class="ht-detail-section">
            <h3 class="ht-detail-title">受影响节点（{{ detail.total_affected_count }}）</h3>
            <p v-if="detailAffectedNodes.length === 0" class="ht-muted">
              本次分析没有识别到受影响节点。
            </p>
            <ul v-else class="ht-affected-list">
              <li v-for="node in detailAffectedNodes" :key="`node-${node.node_id}`">
                <div class="ht-affected-head">
                  <span
                    class="ht-badge"
                    :style="{
                      color: impactLevelMeta(node.impact_level).color,
                      background: `${impactLevelMeta(node.impact_level).color}1a`,
                    }"
                  >
                    {{ impactLevelMeta(node.impact_level).label }}
                  </span>
                  <span class="ht-affected-name">{{ node.node_name }}</span>
                  <span class="ht-affected-distance">距离 {{ node.distance }}</span>
                </div>
                <p class="ht-affected-path">{{ pathText(node.propagation_path) }}</p>
              </li>
            </ul>
          </section>
        </template>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.ht {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.ht-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  padding: 14px 0;
  border-top: 1px solid var(--cm-border);
  border-bottom: 1px solid var(--cm-border);
}

.ht-toolbar-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ht-toolbar-label {
  font-size: 13px;
  color: var(--cm-text-muted);
}

.ht-select {
  width: 320px;
}

.ht-alert {
  margin-top: -6px;
}

.ht-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cm-text);
}

.ht-empty-sub {
  margin-top: 8px;
  font-size: 13px;
  color: var(--cm-text-muted);
}

.ht-summary {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.ht-summary-name {
  font-size: 15px;
  font-weight: 600;
}

.ht-summary-count {
  font-size: 12.5px;
  color: var(--cm-text-muted);
}

/* 列表 */
.ht-table {
  border-top: 1px solid var(--cm-border);
}

.ht-row {
  display: grid;
  grid-template-columns: 1.5fr 1.3fr 0.7fr 0.7fr 0.7fr 0.7fr 1.2fr 0.9fr;
  align-items: center;
  gap: 8px;
  padding: 13px 6px;
  border-bottom: 1px solid var(--cm-border);
  font-size: 13px;
}

.ht-row-head {
  font-size: 12px;
  font-weight: 600;
  color: var(--cm-text-muted);
  padding-top: 10px;
  padding-bottom: 10px;
}

.ht-row:not(.ht-row-head):hover {
  background: rgba(31, 111, 235, 0.03);
}

.ht-time {
  font-variant-numeric: tabular-nums;
  color: var(--cm-text-secondary);
}

.ht-name {
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ht-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--cm-text-secondary);
}

.ht-num-strong {
  font-weight: 700;
  color: var(--cm-text);
}

.ht-ratio-col {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-left: 8px;
}

.ht-ratio-bar {
  flex: 1;
  height: 4px;
  border-radius: 999px;
  background: rgba(15, 23, 42, 0.07);
  overflow: hidden;
  min-width: 36px;
}

.ht-ratio-fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: linear-gradient(90deg, #f59e0b, #dc2626);
}

.ht-ratio-text {
  font-size: 12px;
  color: var(--cm-text-secondary);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.ht-action-col {
  text-align: right;
}

.ht-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 8px;
}

/* 详情 */
.ht-detail {
  min-height: 120px;
}

.ht-detail-meta {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.ht-detail-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--cm-primary);
}

.ht-detail-time {
  font-size: 12.5px;
  color: var(--cm-text-muted);
}

.ht-detail-metrics {
  margin-top: 14px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid var(--cm-border);
}

.ht-detail-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.ht-detail-value {
  font-size: 21px;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.ht-detail-value.is-danger {
  color: #dc2626;
}

.ht-detail-value.is-warn {
  color: #f97316;
}

.ht-detail-value.is-muted {
  color: #eab308;
}

.ht-detail-value.is-primary {
  color: var(--cm-primary);
}

.ht-detail-label {
  font-size: 11.5px;
  color: var(--cm-text-muted);
}

.ht-detail-section {
  margin-top: 18px;
}

.ht-detail-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--cm-text);
}

.ht-muted {
  margin-top: 8px;
  font-size: 13px;
  color: var(--cm-text-muted);
}

.ht-source-list,
.ht-affected-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.ht-source-list li {
  display: flex;
  align-items: baseline;
  gap: 10px;
}

.ht-source-name {
  font-size: 13.5px;
  font-weight: 600;
}

.ht-source-meta {
  font-size: 12px;
  color: var(--cm-text-muted);
}

.ht-affected-list li {
  padding: 10px 0;
  border-bottom: 1px dashed var(--cm-border);
}

.ht-affected-head {
  display: flex;
  align-items: center;
  gap: 10px;
}

.ht-badge {
  padding: 1px 8px;
  border-radius: 999px;
  font-size: 11.5px;
  font-weight: 600;
}

.ht-affected-name {
  font-size: 13.5px;
  font-weight: 600;
}

.ht-affected-distance {
  font-size: 11.5px;
  color: var(--cm-text-muted);
}

.ht-affected-path {
  margin-top: 6px;
  font-size: 12.5px;
  color: var(--cm-text-secondary);
  line-height: 1.6;
}

@media (max-width: 900px) {
  .ht-select {
    width: 100%;
  }

  .ht-row {
    grid-template-columns: 1.4fr 1.1fr 0.6fr 0.6fr 0.6fr 0.6fr 1fr 0.8fr;
    font-size: 12px;
  }
}
</style>
