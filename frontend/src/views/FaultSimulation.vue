<script setup lang="ts">
import { computed, markRaw, onMounted, reactive, ref, shallowRef } from 'vue'
import { ElMessage } from 'element-plus'
import { MarkerType, VueFlow } from '@vue-flow/core'
import type { Edge, Node, NodeTypesObject } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'

import TopologyNode from '@/components/TopologyNode.vue'
import { topologyApi } from '@/api/topology'
import type {
  NodeStatus,
  NodeType,
  TopologyEdge,
  TopologyNode as ApiNode,
  TopologySummary,
} from '@/api/topology'
import { faultApi } from '@/api/fault'
import type { FaultEvent, FaultSeverity, FaultType } from '@/api/fault'
import { analysisApi } from '@/api/analysis'
import type { AffectedNode, AnalysisResult, FaultSource } from '@/api/analysis'
import { extractErrorMessage } from '@/api/errors'
import {
  FAULT_SEVERITIES,
  FAULT_SOURCE_COLOR,
  FAULT_TYPES,
  IMPACT_LEVELS,
  faultSeverityMeta,
  faultStatusMeta,
  faultTypeLabel,
  impactLevelMeta,
} from '@/constants/fault'
import type { NodeImpact } from '@/constants/fault'
import { nodeTypeLabel } from '@/constants/topology'

interface FlowNodeData {
  label: string
  nodeType: NodeType
  status: NodeStatus
  description: string | null
  impact: NodeImpact | null
  distance: number | null
}

interface FlowEdgeData {
  edgeId: number
}

// --------------------------------------------------------------------------- //
// 状态
// --------------------------------------------------------------------------- //
const topologies = ref<TopologySummary[]>([])
const topologyId = ref<number | null>(null)
const nodes = ref<ApiNode[]>([])
const edges = ref<TopologyEdge[]>([])
const faults = ref<FaultEvent[]>([])
const analysis = ref<AnalysisResult | null>(null)

const loadingTopologies = ref(false)
const loadingTopology = ref(false)
const injectingFault = ref(false)
const recoveringId = ref<number | null>(null)
const analyzing = ref(false)
const loadError = ref('')

const selectedNodeId = ref<number | null>(null)

const faultForm = reactive({
  source_node_id: null as number | null,
  fault_type: 'node_down' as FaultType,
  severity: 'high' as FaultSeverity,
  description: '',
})

const flowNodes = shallowRef<Node<FlowNodeData>[]>([])
const flowEdges = shallowRef<Edge<FlowEdgeData>[]>([])
const nodeTypes = { topology: markRaw(TopologyNode) } as unknown as NodeTypesObject

// --------------------------------------------------------------------------- //
// 派生数据
// --------------------------------------------------------------------------- //
const activeFaults = computed(() => faults.value.filter((fault) => fault.status === 'active'))
const hasTopology = computed(() => topologyId.value !== null)

const selectedNode = computed(() =>
  selectedNodeId.value === null
    ? null
    : (nodes.value.find((node) => node.id === selectedNodeId.value) ?? null),
)

const selectedImpact = computed<{ kind: 'source'; source: FaultSource } | { kind: 'affected'; affected: AffectedNode } | null>(() => {
  if (!analysis.value || selectedNodeId.value === null) return null
  const affected = analysis.value.affected_nodes.find(
    (item) => item.node_id === selectedNodeId.value,
  )
  if (affected) return { kind: 'affected', affected }
  const source = analysis.value.fault_sources.find(
    (item) => item.source_node_id === selectedNodeId.value,
  )
  if (source) return { kind: 'source', source }
  return null
})

const impactSummary = computed(() => {
  if (!analysis.value) return []
  return [
    { label: '故障源', value: String(analysis.value.fault_sources.length), color: FAULT_SOURCE_COLOR },
    {
      label: '受影响节点',
      value: String(analysis.value.total_affected_count),
      color: '#0f172a',
    },
    {
      label: '直接影响',
      value: String(analysis.value.direct_affected_count),
      color: impactLevelMeta('direct').color,
    },
    {
      label: '间接影响',
      value: String(analysis.value.indirect_affected_count),
      color: impactLevelMeta('indirect').color,
    },
    { label: '节点总数', value: String(analysis.value.total_node_count), color: '#5b6b84' },
    {
      label: '影响比例',
      value: `${(analysis.value.impact_ratio * 100).toFixed(1)}%`,
      color: '#1f6feb',
    },
  ]
})

const sortedPaths = computed(() => {
  if (!analysis.value) return []
  return [...analysis.value.propagation_paths].sort(
    (a, b) => a.distance - b.distance || (a.target_node_id ?? 0) - (b.target_node_id ?? 0),
  )
})

// --------------------------------------------------------------------------- //
// 图渲染（含传播高亮）
// --------------------------------------------------------------------------- //
function impactByNodeId(): Map<number, { impact: NodeImpact; distance: number }> {
  const map = new Map<number, { impact: NodeImpact; distance: number }>()
  if (!analysis.value) return map
  for (const source of analysis.value.fault_sources) {
    if (source.source_node_id !== null) {
      map.set(source.source_node_id, { impact: 'fault_source', distance: 0 })
    }
  }
  for (const node of analysis.value.affected_nodes) {
    if (node.node_id !== null) {
      map.set(node.node_id, { impact: node.impact_level, distance: node.distance })
    }
  }
  return map
}

/**
 * 传播路径上的依赖边键集合。
 *
 * 路径步骤为「传播方向」，相邻两步 (from, to) 表示 to 依赖 from，
 * 对应后端依赖边 `to → from`，也即 Vue Flow 中 source=to、target=from。
 */
function highlightedEdgeKeys(): Set<string> {
  const keys = new Set<string>()
  if (!analysis.value) return keys
  for (const path of analysis.value.propagation_paths) {
    for (let index = 0; index + 1 < path.steps.length; index += 1) {
      const from = path.steps[index].node_id
      const to = path.steps[index + 1].node_id
      if (from === null || to === null) continue
      keys.add(`${to}|${from}`)
    }
  }
  return keys
}

function renderGraph() {
  const impacts = impactByNodeId()
  flowNodes.value = nodes.value.map((node) => {
    const impact = impacts.get(node.id)
    return {
      id: String(node.id),
      type: 'topology',
      position: { x: node.position_x, y: node.position_y },
      data: {
        label: node.name,
        nodeType: node.type,
        status: node.status,
        description: node.description,
        impact: impact?.impact ?? null,
        distance: impact?.distance ?? null,
      },
    }
  })

  const keys = highlightedEdgeKeys()
  flowEdges.value = edges.value.map((edge) => {
    const onPath = keys.has(`${edge.source_node_id}|${edge.target_node_id}`)
    return {
      id: `edge-${edge.id}`,
      source: String(edge.source_node_id),
      target: String(edge.target_node_id),
      data: { edgeId: edge.id },
      animated: onPath,
      style: onPath ? { stroke: FAULT_SOURCE_COLOR, strokeWidth: 2.5 } : undefined,
      markerEnd: MarkerType.ArrowClosed,
    }
  })
}

// --------------------------------------------------------------------------- //
// 加载
// --------------------------------------------------------------------------- //
async function loadTopologies() {
  loadingTopologies.value = true
  try {
    const { data } = await topologyApi.list()
    topologies.value = data
    if (topologyId.value === null && data.length > 0) {
      topologyId.value = data[0].id
      await loadTopology()
    }
  } catch (error) {
    loadError.value = extractErrorMessage(error, '加载拓扑列表失败')
  } finally {
    loadingTopologies.value = false
  }
}

async function loadTopology() {
  if (topologyId.value === null) {
    nodes.value = []
    edges.value = []
    faults.value = []
    analysis.value = null
    selectedNodeId.value = null
    renderGraph()
    return
  }

  loadingTopology.value = true
  loadError.value = ''
  selectedNodeId.value = null
  try {
    const { data } = await topologyApi.detail(topologyId.value)
    nodes.value = data.nodes
    edges.value = data.edges
    analysis.value = null
    renderGraph()
    await loadFaults()
    await loadLatestAnalysis()
  } catch (error) {
    loadError.value = extractErrorMessage(error, '加载拓扑详情失败')
  } finally {
    loadingTopology.value = false
  }
}

async function loadFaults() {
  if (topologyId.value === null) {
    faults.value = []
    return
  }
  try {
    const { data } = await faultApi.list(topologyId.value)
    faults.value = data
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '加载故障列表失败'))
  }
}

async function loadLatestAnalysis() {
  if (topologyId.value === null) return
  try {
    const { data } = await analysisApi.latest(topologyId.value)
    analysis.value = data
    renderGraph()
  } catch {
    // 尚无分析记录（404）时静默忽略
  }
}

function onTopologyChange() {
  void loadTopology()
}

// --------------------------------------------------------------------------- //
// 故障注入与恢复
// --------------------------------------------------------------------------- //
async function injectFault() {
  if (topologyId.value === null) {
    ElMessage.warning('请先选择拓扑')
    return
  }
  if (faultForm.source_node_id === null) {
    ElMessage.warning('请选择故障节点')
    return
  }

  injectingFault.value = true
  try {
    await faultApi.create(topologyId.value, {
      source_node_id: faultForm.source_node_id,
      fault_type: faultForm.fault_type,
      severity: faultForm.severity,
      description: faultForm.description.trim() || null,
    })
    ElMessage.success('故障已注入')
    faultForm.description = ''
    await loadFaults()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '注入故障失败'))
  } finally {
    injectingFault.value = false
  }
}

async function recoverFault(fault: FaultEvent) {
  recoveringId.value = fault.id
  try {
    await faultApi.recover(fault.id)
    ElMessage.success('故障已恢复')
    await loadFaults()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '恢复故障失败'))
  } finally {
    recoveringId.value = null
  }
}

// --------------------------------------------------------------------------- //
// 传播分析
// --------------------------------------------------------------------------- //
async function runAnalysis() {
  if (topologyId.value === null) {
    ElMessage.warning('请先选择拓扑')
    return
  }
  analyzing.value = true
  try {
    const { data } = await analysisApi.analyze(topologyId.value)
    analysis.value = data
    renderGraph()
    if (data.total_affected_count === 0) {
      ElMessage.info('分析完成：当前没有激活故障造成的影响')
    } else {
      ElMessage.success(`分析完成：受影响节点 ${data.total_affected_count} 个`)
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '传播分析失败'))
  } finally {
    analyzing.value = false
  }
}

function clearHighlight() {
  analysis.value = null
  renderGraph()
  selectedNodeId.value = null
  ElMessage.info('已清除分析高亮')
}

function onNodeClick(payload: { node: Node }) {
  selectedNodeId.value = Number(payload.node.id)
}

function onPaneClick() {
  selectedNodeId.value = null
}

function pathText(steps: { node_name: string }[]): string {
  return steps.map((step) => step.node_name).join(' → ')
}

onMounted(loadTopologies)
</script>

<template>
  <div class="fs">
    <header class="cm-page-header">
      <h1 class="cm-page-title">故障模拟</h1>
      <p class="cm-page-subtitle">
        对拓扑中的节点注入故障，调用后端传播分析算法计算影响范围，并在画布中高亮故障源、
        直接与间接受影响节点。所有结果均来自真实 API，不含演示数据。
      </p>
    </header>

    <!-- 拓扑选择与操作 -->
    <div class="fs-toolbar">
      <div class="fs-toolbar-item">
        <span class="fs-toolbar-label">目标拓扑</span>
        <el-select
          v-model="topologyId"
          class="fs-select"
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
      <div class="fs-toolbar-actions">
        <el-button :loading="loadingTopology || loadingTopologies" @click="loadTopology">
          刷新
        </el-button>
        <el-button
          type="primary"
          :loading="analyzing"
          :disabled="!hasTopology"
          @click="runAnalysis"
        >
          开始传播分析
        </el-button>
        <el-button :disabled="!analysis" @click="clearHighlight">清除高亮</el-button>
      </div>
    </div>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="fs-alert"
    >
      <template #default>
        <span>请确认后端服务已启动，然后点击「刷新」重试。</span>
      </template>
    </el-alert>

    <el-empty v-if="!loadingTopologies && topologies.length === 0" description="暂无拓扑">
      <template #description>
        <p class="fs-empty-title">暂无拓扑</p>
        <p class="fs-empty-sub">请先前往「系统拓扑」页面创建拓扑与依赖关系。</p>
      </template>
    </el-empty>

    <template v-else>
      <p class="fs-hint">
        操作提示：选择拓扑后在右侧注入故障；点击「开始传播分析」调用后端算法；
        <strong>红色</strong>为故障源、<strong>橙色</strong>为直接影响、
        <strong>黄色</strong>为间接影响，传播路径上的连线会高亮；点击节点可查看影响详情。
      </p>

      <div class="fs-body">
        <div class="fs-canvas-col">
          <div class="fs-canvas">
            <div v-loading="loadingTopology" class="fs-canvas-inner">
              <VueFlow
                :nodes="flowNodes"
                :edges="flowEdges"
                :node-types="nodeTypes"
                :delete-key-code="null"
                :min-zoom="0.2"
                :nodes-draggable="false"
                :nodes-connectable="false"
                fit-view-on-init
                @node-click="onNodeClick"
                @pane-click="onPaneClick"
              >
                <Background :gap="18" :size="1.4" pattern-color="#dbe4f3" />
                <Controls />
              </VueFlow>

              <div v-if="!loadingTopology && flowNodes.length === 0" class="fs-canvas-empty">
                当前拓扑还没有节点，请先在「系统拓扑」页面添加节点与依赖
              </div>
            </div>
          </div>

          <!-- 分析结果摘要 -->
          <div v-if="analysis" class="fs-summary">
            <div class="fs-summary-head">
              <span class="fs-section-label">分析结果</span>
              <span class="fs-summary-meta">
                分析编号 #{{ analysis.analysis_id }} ·
                {{ new Date(analysis.analysis_time).toLocaleString() }}
              </span>
            </div>

            <div class="fs-metrics">
              <div v-for="metric in impactSummary" :key="metric.label" class="fs-metric">
                <span class="fs-metric-value" :style="{ color: metric.color }">
                  {{ metric.value }}
                </span>
                <span class="fs-metric-label">{{ metric.label }}</span>
              </div>
            </div>

            <div class="fs-legend">
              <span class="fs-legend-item">
                <i class="fs-legend-dot" :style="{ background: FAULT_SOURCE_COLOR }"></i>故障源
              </span>
              <span
                v-for="level in IMPACT_LEVELS"
                :key="level.value"
                class="fs-legend-item"
              >
                <i class="fs-legend-dot" :style="{ background: level.color }"></i>{{ level.label }}
              </span>
            </div>

            <div class="fs-paths">
              <p class="fs-section-label">传播路径明细（{{ sortedPaths.length }}）</p>
              <ul v-if="sortedPaths.length" class="fs-path-list">
                <li v-for="path in sortedPaths" :key="`${path.target_node_id}-${path.source_fault_id}`">
                  <span class="fs-path-distance">距离 {{ path.distance }}</span>
                  <span class="fs-path-text">{{ pathText(path.steps) }}</span>
                  <span
                    class="fs-badge fs-badge-solid"
                    :style="{
                      background: impactLevelMeta(path.distance === 1 ? 'direct' : 'indirect').color,
                    }"
                  >
                    {{ impactLevelMeta(path.distance === 1 ? 'direct' : 'indirect').label }}
                  </span>
                </li>
              </ul>
              <p v-else class="fs-muted">本次分析没有产生传播路径。</p>
            </div>
          </div>
        </div>

        <aside class="fs-inspector">
          <!-- 注入故障 -->
          <p class="fs-section-label">注入故障</p>
          <el-form label-position="top" class="fs-form" @submit.prevent>
            <el-form-item label="故障节点">
              <el-select
                v-model="faultForm.source_node_id"
                class="fs-full"
                placeholder="选择节点"
                :disabled="!hasTopology"
              >
                <el-option
                  v-for="node in nodes"
                  :key="node.id"
                  :label="`${node.name}（${nodeTypeLabel(node.type)}）`"
                  :value="node.id"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="故障类型">
              <el-select v-model="faultForm.fault_type" class="fs-full">
                <el-option
                  v-for="item in FAULT_TYPES"
                  :key="item.value"
                  :label="`${item.label} · ${item.hint}`"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="严重程度">
              <el-radio-group v-model="faultForm.severity">
                <el-radio-button
                  v-for="item in FAULT_SEVERITIES"
                  :key="item.value"
                  :value="item.value"
                >
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="故障描述">
              <el-input
                v-model="faultForm.description"
                type="textarea"
                :rows="2"
                placeholder="可选，例如：主库连接耗尽"
              />
            </el-form-item>
          </el-form>
          <el-button
            type="danger"
            plain
            class="fs-full"
            :loading="injectingFault"
            :disabled="!hasTopology"
            @click="injectFault"
          >
            注入故障
          </el-button>

          <el-divider />

          <!-- 故障列表 -->
          <p class="fs-section-label">
            故障事件（激活 {{ activeFaults.length }} / 共 {{ faults.length }}）
          </p>
          <ul v-if="faults.length" class="fs-fault-list">
            <li v-for="fault in faults" :key="fault.id" class="fs-fault-item">
              <div class="fs-fault-main">
                <span class="fs-fault-node">{{ fault.source_node_name ?? `节点#${fault.source_node_id}` }}</span>
                <span class="fs-fault-type">{{ faultTypeLabel(fault.fault_type) }}</span>
              </div>
              <div class="fs-fault-meta">
                <span
                  class="fs-badge"
                  :style="{
                    color: faultSeverityMeta(fault.severity).color,
                    borderColor: faultSeverityMeta(fault.severity).color,
                  }"
                >
                  {{ faultSeverityMeta(fault.severity).label }}
                </span>
                <span
                  class="fs-badge"
                  :style="{
                    color: faultStatusMeta(fault.status).color,
                    borderColor: faultStatusMeta(fault.status).color,
                  }"
                >
                  {{ faultStatusMeta(fault.status).label }}
                </span>
                <el-button
                  v-if="fault.status === 'active'"
                  size="small"
                  link
                  type="primary"
                  :loading="recoveringId === fault.id"
                  @click="recoverFault(fault)"
                >
                  恢复
                </el-button>
              </div>
              <p v-if="fault.description" class="fs-fault-desc cm-muted">{{ fault.description }}</p>
            </li>
          </ul>
          <p v-else class="fs-muted">当前拓扑还没有故障事件。</p>

          <el-divider />

          <!-- 选中节点影响详情 -->
          <p class="fs-section-label">节点影响详情</p>
          <template v-if="selectedNode">
            <p class="fs-detail-name">{{ selectedNode.name }}</p>
            <template v-if="selectedImpact?.kind === 'source'">
              <p class="fs-detail-line">
                <span class="fs-detail-key">角色</span>
                <span class="fs-detail-value" :style="{ color: FAULT_SOURCE_COLOR }">故障源</span>
              </p>
              <p class="fs-detail-line">
                <span class="fs-detail-key">故障类型</span>
                <span class="fs-detail-value">{{ faultTypeLabel(selectedImpact.source.fault_type) }}</span>
              </p>
              <p class="fs-detail-line">
                <span class="fs-detail-key">严重程度</span>
                <span class="fs-detail-value">
                  {{ faultSeverityMeta(selectedImpact.source.severity).label }}
                </span>
              </p>
            </template>
            <template v-else-if="selectedImpact?.kind === 'affected'">
              <p class="fs-detail-line">
                <span class="fs-detail-key">影响等级</span>
                <span
                  class="fs-detail-value"
                  :style="{ color: impactLevelMeta(selectedImpact.affected.impact_level).color }"
                >
                  {{ impactLevelMeta(selectedImpact.affected.impact_level).label }}
                </span>
              </p>
              <p class="fs-detail-line">
                <span class="fs-detail-key">传播距离</span>
                <span class="fs-detail-value">{{ selectedImpact.affected.distance }}</span>
              </p>
              <p class="fs-detail-line">
                <span class="fs-detail-key">来源故障</span>
                <span class="fs-detail-value">
                  {{ selectedImpact.affected.source_fault_id === null ? '—' : `#${selectedImpact.affected.source_fault_id}` }}
                </span>
              </p>
              <p class="fs-detail-line">
                <span class="fs-detail-key">传播路径</span>
              </p>
              <p class="fs-detail-path">{{ pathText(selectedImpact.affected.propagation_path) }}</p>
            </template>
            <p v-else class="fs-muted">该节点未受当前分析影响（正常节点）。</p>
          </template>
          <p v-else class="fs-muted">在画布中点击一个节点查看其影响详情。</p>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.fs-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-end;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}

.fs-toolbar-item {
  display: flex;
  align-items: center;
  gap: 10px;
}

.fs-toolbar-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--cm-text-secondary);
}

.fs-select {
  width: 320px;
}

.fs-toolbar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.fs-alert {
  margin-bottom: 16px;
}

.fs-hint {
  margin: 0 0 18px;
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--cm-primary-soft);
  font-size: 13px;
  line-height: 1.8;
  color: var(--cm-text-secondary);
}

.fs-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 340px;
  gap: 20px;
  align-items: start;
}

.fs-canvas-col {
  display: flex;
  flex-direction: column;
  gap: 18px;
  min-width: 0;
}

.fs-canvas-inner {
  position: relative;
  height: 520px;
  border-radius: var(--cm-radius);
  overflow: hidden;
  border: 1px solid var(--cm-border);
  background: #fbfcff;
  box-shadow: var(--cm-shadow);
}

.fs-canvas-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13.5px;
  color: var(--cm-text-muted);
  pointer-events: none;
}

.fs-summary {
  padding: 18px;
  border-radius: var(--cm-radius);
  border: 1px solid var(--cm-border);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.fs-summary-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 8px;
}

.fs-summary-meta {
  font-size: 12px;
  color: var(--cm-text-muted);
}

.fs-metrics {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(96px, 1fr));
  gap: 12px;
  margin: 14px 0;
}

.fs-metric {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid var(--cm-border);
}

.fs-metric-value {
  font-size: 20px;
  font-weight: 700;
}

.fs-metric-label {
  font-size: 12px;
  color: var(--cm-text-muted);
}

.fs-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-bottom: 14px;
}

.fs-legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  color: var(--cm-text-secondary);
}

.fs-legend-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}

.fs-path-list {
  margin: 10px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 240px;
  overflow-y: auto;
}

.fs-path-list li {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12.5px;
  line-height: 1.6;
}

.fs-path-distance {
  flex: none;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--cm-primary-soft);
  color: var(--cm-primary);
  font-weight: 600;
  font-size: 11.5px;
}

.fs-path-text {
  color: var(--cm-text);
  word-break: break-all;
}

.fs-badge {
  flex: none;
  padding: 1px 8px;
  border-radius: 999px;
  border: 1px solid;
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1.7;
  white-space: nowrap;
}

.fs-badge-solid {
  border: none;
  color: #fff;
}

.fs-inspector {
  padding: 18px;
  border-radius: var(--cm-radius);
  border: 1px solid var(--cm-border);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
  position: sticky;
  top: 88px;
}

.fs-section-label {
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--cm-text-muted);
  text-transform: uppercase;
}

.fs-form {
  margin-top: 12px;
}

.fs-full {
  width: 100%;
}

.fs-fault-list {
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 10px;
  max-height: 300px;
  overflow-y: auto;
}

.fs-fault-item {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px solid var(--cm-border);
  background: rgba(255, 255, 255, 0.7);
}

.fs-fault-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.fs-fault-node {
  font-size: 13px;
  font-weight: 600;
  color: var(--cm-text);
}

.fs-fault-type {
  font-size: 12px;
  color: var(--cm-text-secondary);
}

.fs-fault-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 8px;
}

.fs-fault-desc {
  margin-top: 6px;
  font-size: 12px;
}

.fs-detail-name {
  margin-top: 10px;
  font-size: 14px;
  font-weight: 600;
  color: var(--cm-text);
}

.fs-detail-line {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
  font-size: 12.5px;
}

.fs-detail-key {
  color: var(--cm-text-muted);
}

.fs-detail-value {
  font-weight: 600;
  color: var(--cm-text);
}

.fs-detail-path {
  margin-top: 6px;
  font-size: 12.5px;
  line-height: 1.7;
  color: var(--cm-text-secondary);
  word-break: break-all;
}

.fs-muted {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--cm-text-muted);
}

.fs-empty-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cm-text);
}

.fs-empty-sub {
  margin-top: 8px;
  font-size: 13px;
  color: var(--cm-text-muted);
}

@media (max-width: 1024px) {
  .fs-body {
    grid-template-columns: minmax(0, 1fr);
  }

  .fs-inspector {
    position: static;
  }
}
</style>
