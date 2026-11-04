<script setup lang="ts">
import { computed, markRaw, onMounted, reactive, ref, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MarkerType, VueFlow } from '@vue-flow/core'
import type { Connection, Edge, Node, NodeTypesObject } from '@vue-flow/core'
import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'

import TopologyNode from '@/components/TopologyNode.vue'
import { topologyApi } from '@/api/topology'
import type {
  NodeStatus,
  NodeType,
  TopologyDetail,
  TopologyEdge,
  TopologyNode as ApiNode,
} from '@/api/topology'
import { extractErrorMessage } from '@/api/errors'
import { NODE_STATUSES, NODE_TYPES, nodeTypeLabel } from '@/constants/topology'

const route = useRoute()
const router = useRouter()

const topologyId = computed(() => Number(route.params.id))

const loading = ref(false)
const loadError = ref('')
const topology = ref<TopologyDetail | null>(null)

/** Vue Flow 节点 / 边的自定义 data 结构。 */
interface FlowNodeData {
  label: string
  nodeType: NodeType
  status: NodeStatus
  description: string | null
}

interface FlowEdgeData {
  edgeId: number
  description: string | null
}

// 使用 shallowRef 避免 Vue 对 Vue Flow 复杂泛型类型做深层解包
const flowNodes = shallowRef<Node<FlowNodeData>[]>([])
const flowEdges = shallowRef<Edge<FlowEdgeData>[]>([])
const nodesById = ref<Record<number, ApiNode>>({})

const selectedNodeId = ref<number | null>(null)
const selectedEdgeId = ref<number | null>(null)
const savingNode = ref(false)
const savingLayout = ref(false)
const addingNode = ref(false)

const nodeForm = reactive({
  name: '',
  type: 'app_server' as NodeType,
  status: 'healthy' as NodeStatus,
  description: '',
})

const nodeTypes = { topology: markRaw(TopologyNode) } as unknown as NodeTypesObject
const defaultEdgeOptions = { markerEnd: MarkerType.ArrowClosed }

const selectedNode = computed(() =>
  selectedNodeId.value === null ? null : (nodesById.value[selectedNodeId.value] ?? null),
)

const selectedEdge = computed(() =>
  selectedEdgeId.value === null
    ? null
    : (flowEdges.value.find((edge) => edge.data?.edgeId === selectedEdgeId.value) ?? null),
)

const selectedEdgeDescription = computed(() => {
  const description = selectedEdge.value?.data?.description
  return typeof description === 'string' ? description : ''
})

// --------------------------------------------------------------------------- //
// 数据映射
// --------------------------------------------------------------------------- //
function toFlowNode(node: ApiNode): Node<FlowNodeData> {
  return {
    id: String(node.id),
    type: 'topology',
    position: { x: node.position_x, y: node.position_y },
    data: {
      label: node.name,
      nodeType: node.type,
      status: node.status,
      description: node.description,
    },
  }
}

function toFlowEdge(edge: TopologyEdge): Edge<FlowEdgeData> {
  return {
    id: `edge-${edge.id}`,
    source: String(edge.source_node_id),
    target: String(edge.target_node_id),
    data: { edgeId: edge.id, description: edge.description },
  }
}

function syncFlowNodeData(node: ApiNode) {
  flowNodes.value = flowNodes.value.map((item) =>
    item.id === String(node.id)
      ? {
          ...item,
          data: {
            label: node.name,
            nodeType: node.type,
            status: node.status,
            description: node.description,
          },
        }
      : item,
  )
}

// --------------------------------------------------------------------------- //
// 加载
// --------------------------------------------------------------------------- //
async function loadTopology() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await topologyApi.detail(topologyId.value)
    topology.value = data
    flowNodes.value = data.nodes.map(toFlowNode)
    flowEdges.value = data.edges.map(toFlowEdge)
    nodesById.value = Object.fromEntries(data.nodes.map((node) => [node.id, node]))
    selectedNodeId.value = null
    selectedEdgeId.value = null
  } catch (error) {
    loadError.value = extractErrorMessage(error, '加载拓扑失败')
  } finally {
    loading.value = false
  }
}

// --------------------------------------------------------------------------- //
// 节点操作
// --------------------------------------------------------------------------- //
function nextPosition() {
  const count = flowNodes.value.length
  return {
    x: 80 + (count % 5) * 180,
    y: 60 + Math.floor(count / 5) * 150,
  }
}

async function addNode(type: NodeType) {
  if (!topology.value) return
  addingNode.value = true
  const position = nextPosition()
  try {
    const { data } = await topologyApi.addNode(topology.value.id, {
      name: `${nodeTypeLabel(type)} ${flowNodes.value.length + 1}`,
      type,
      position_x: position.x,
      position_y: position.y,
    })
    nodesById.value[data.id] = data
    flowNodes.value = [...flowNodes.value, toFlowNode(data)]
    ElMessage.success('节点已添加')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '添加节点失败'))
  } finally {
    addingNode.value = false
  }
}

function onNodeClick(payload: { node: Node }) {
  const id = Number(payload.node.id)
  const serverNode = nodesById.value[id]
  if (!serverNode) return
  selectedEdgeId.value = null
  selectedNodeId.value = id
  nodeForm.name = serverNode.name
  nodeForm.type = serverNode.type
  nodeForm.status = serverNode.status
  nodeForm.description = serverNode.description ?? ''
}

function onEdgeClick(payload: { edge: Edge }) {
  const edgeId = payload.edge.data?.edgeId
  if (typeof edgeId !== 'number') return
  selectedNodeId.value = null
  selectedEdgeId.value = edgeId
}

function onPaneClick() {
  selectedNodeId.value = null
  selectedEdgeId.value = null
}

async function saveNode() {
  if (!topology.value || selectedNodeId.value === null) return
  if (!nodeForm.name.trim()) {
    ElMessage.warning('节点名称不能为空')
    return
  }

  savingNode.value = true
  try {
    const { data } = await topologyApi.updateNode(topology.value.id, selectedNodeId.value, {
      name: nodeForm.name.trim(),
      type: nodeForm.type,
      status: nodeForm.status,
      description: nodeForm.description.trim() || null,
    })
    nodesById.value[data.id] = data
    syncFlowNodeData(data)
    ElMessage.success('节点已保存')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '保存节点失败'))
  } finally {
    savingNode.value = false
  }
}

async function removeSelectedNode() {
  if (!topology.value || selectedNodeId.value === null) return
  const node = nodesById.value[selectedNodeId.value]
  if (!node) return

  try {
    await ElMessageBox.confirm(
      `确认删除节点「${node.name}」？与其相关的依赖关系将一并删除。`,
      '删除节点',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  const id = selectedNodeId.value
  try {
    await topologyApi.removeNode(topology.value.id, id)
    flowNodes.value = flowNodes.value.filter((item) => item.id !== String(id))
    flowEdges.value = flowEdges.value.filter(
      (edge) => edge.source !== String(id) && edge.target !== String(id),
    )
    delete nodesById.value[id]
    selectedNodeId.value = null
    ElMessage.success('节点已删除')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '删除节点失败'))
  }
}

async function onNodeDragStop(payload: { node: Node }) {
  if (!topology.value) return
  const id = Number(payload.node.id)
  const serverNode = nodesById.value[id]
  if (!serverNode) return

  const { x, y } = payload.node.position
  if (serverNode.position_x === x && serverNode.position_y === y) return

  try {
    const { data } = await topologyApi.updateNode(topology.value.id, id, {
      position_x: x,
      position_y: y,
    })
    nodesById.value[data.id] = data
    ElMessage({ message: '节点位置已保存', type: 'success', grouping: true, duration: 1200 })
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '保存节点位置失败'))
  }
}

async function saveLayout() {
  if (!topology.value) return
  const changed = flowNodes.value.filter((node) => {
    const serverNode = nodesById.value[Number(node.id)]
    if (!serverNode) return false
    return (
      serverNode.position_x !== node.position.x || serverNode.position_y !== node.position.y
    )
  })

  if (changed.length === 0) {
    ElMessage.info('布局未发生变化')
    return
  }

  savingLayout.value = true
  try {
    for (const node of changed) {
      const { data } = await topologyApi.updateNode(topology.value.id, Number(node.id), {
        position_x: node.position.x,
        position_y: node.position.y,
      })
      nodesById.value[data.id] = data
    }
    ElMessage.success(`已保存 ${changed.length} 个节点的位置`)
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '保存布局失败'))
  } finally {
    savingLayout.value = false
  }
}

// --------------------------------------------------------------------------- //
// 依赖关系操作
// --------------------------------------------------------------------------- //
async function onConnect(connection: Connection) {
  if (!topology.value) return
  const sourceId = connection.source ? Number(connection.source) : Number.NaN
  const targetId = connection.target ? Number(connection.target) : Number.NaN
  if (!Number.isFinite(sourceId) || !Number.isFinite(targetId)) return

  if (sourceId === targetId) {
    ElMessage.warning('节点不能依赖自身')
    return
  }

  try {
    const { data } = await topologyApi.addEdge(topology.value.id, {
      source_node_id: sourceId,
      target_node_id: targetId,
    })
    flowEdges.value = [...flowEdges.value, toFlowEdge(data)]
    ElMessage.success('依赖关系已创建')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '创建依赖关系失败'))
  }
}

async function removeSelectedEdge() {
  if (!topology.value || selectedEdgeId.value === null) return
  const edgeId = selectedEdgeId.value
  try {
    await topologyApi.removeEdge(topology.value.id, edgeId)
    flowEdges.value = flowEdges.value.filter((edge) => edge.data?.edgeId !== edgeId)
    selectedEdgeId.value = null
    ElMessage.success('依赖关系已删除')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '删除依赖关系失败'))
  }
}

// --------------------------------------------------------------------------- //
// 拓扑基本信息
// --------------------------------------------------------------------------- //
async function renameTopology() {
  if (!topology.value) return
  const result = await ElMessageBox.prompt('请输入新的拓扑名称', '重命名拓扑', {
    inputValue: topology.value.name,
    inputValidator: (value: string) => (value && value.trim().length > 0) || '名称不能为空',
    confirmButtonText: '保存',
    cancelButtonText: '取消',
  }).catch(() => null)

  if (!result) return

  try {
    const { data } = await topologyApi.update(topology.value.id, {
      name: result.value.trim(),
    })
    if (topology.value) topology.value.name = data.name
    ElMessage.success('拓扑名称已更新')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '更新拓扑名称失败'))
  }
}

onMounted(loadTopology)
</script>

<template>
  <div class="editor">
    <header class="editor-header">
      <div class="editor-title-group">
        <el-button link @click="router.push('/topology')">← 返回列表</el-button>
        <h1 class="editor-title">{{ topology?.name ?? '拓扑编辑' }}</h1>
        <el-button v-if="topology" link type="primary" @click="renameTopology">重命名</el-button>
      </div>
      <div class="editor-header-actions">
        <el-button :loading="loading" @click="loadTopology">刷新</el-button>
        <el-button type="primary" :loading="savingLayout" @click="saveLayout">
          保存布局
        </el-button>
      </div>
    </header>

    <el-alert
      v-if="loadError"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
      class="editor-alert"
    >
      <template #default>
        <span>请确认后端服务已启动，然后点击「刷新」重试。</span>
      </template>
    </el-alert>

    <p class="editor-hint">
      操作提示：点击下方按钮添加节点；拖动节点调整位置（松手即自动保存）；
      从节点<strong>底部</strong>圆点拖到另一节点<strong>顶部</strong>圆点创建依赖
      （<strong>箭头方向 = 依赖方向</strong>：A → B 表示 A 依赖 B）；点击节点或连线可在右侧编辑或删除。
    </p>

    <div class="editor-body">
      <div class="editor-canvas">
        <div v-loading="loading" class="editor-canvas-inner">
          <VueFlow
            v-model:nodes="flowNodes"
            v-model:edges="flowEdges"
            :node-types="nodeTypes"
            :default-edge-options="defaultEdgeOptions"
            :delete-key-code="null"
            :min-zoom="0.2"
            fit-view-on-init
            @connect="onConnect"
            @node-click="onNodeClick"
            @edge-click="onEdgeClick"
            @pane-click="onPaneClick"
            @node-drag-stop="onNodeDragStop"
          >
            <Background :gap="18" :size="1.4" pattern-color="#dbe4f3" />
            <Controls />
          </VueFlow>

          <div v-if="!loading && flowNodes.length === 0" class="editor-empty">
            当前拓扑还没有节点，点击上方节点按钮开始添加
          </div>
        </div>
      </div>

      <aside class="editor-inspector">
        <div class="inspector-tools">
          <p class="inspector-label">添加节点</p>
          <div class="inspector-type-list">
            <button
              v-for="item in NODE_TYPES"
              :key="item.value"
              type="button"
              class="type-chip"
              :disabled="addingNode"
              @click="addNode(item.value)"
            >
              <i class="type-chip-dot" :style="{ background: item.color }"></i>
              {{ item.label }}
            </button>
          </div>
        </div>

        <el-divider />

        <template v-if="selectedNode">
          <p class="inspector-label">节点属性</p>
          <el-form label-position="top" class="inspector-form" @submit.prevent>
            <el-form-item label="名称">
              <el-input v-model="nodeForm.name" maxlength="128" />
            </el-form-item>
            <el-form-item label="类型">
              <el-select v-model="nodeForm.type" class="inspector-full">
                <el-option
                  v-for="item in NODE_TYPES"
                  :key="item.value"
                  :label="item.label"
                  :value="item.value"
                />
              </el-select>
            </el-form-item>
            <el-form-item label="状态">
              <el-radio-group v-model="nodeForm.status">
                <el-radio-button
                  v-for="item in NODE_STATUSES"
                  :key="item.value"
                  :value="item.value"
                >
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item label="描述">
              <el-input v-model="nodeForm.description" type="textarea" :rows="3" />
            </el-form-item>
          </el-form>
          <div class="inspector-actions">
            <el-button type="primary" :loading="savingNode" @click="saveNode">保存节点</el-button>
            <el-button type="danger" plain @click="removeSelectedNode">删除节点</el-button>
          </div>
        </template>

        <template v-else-if="selectedEdge">
          <p class="inspector-label">依赖关系</p>
          <p class="inspector-desc">
            <strong>{{ String(selectedEdge.source) }}</strong>
            →
            <strong>{{ String(selectedEdge.target) }}</strong>
            （左侧节点依赖右侧节点）
          </p>
          <p class="inspector-desc cm-muted">
            {{ selectedEdgeDescription || '无说明' }}
          </p>
          <div class="inspector-actions">
            <el-button type="danger" plain @click="removeSelectedEdge">删除依赖关系</el-button>
          </div>
        </template>

        <template v-else>
          <p class="inspector-label">未选中元素</p>
          <p class="inspector-desc cm-muted">
            在画布中点击节点可编辑其属性，点击连线可删除依赖关系。
          </p>
        </template>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.editor-header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.editor-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.editor-title {
  font-size: 22px;
  font-weight: 700;
}

.editor-header-actions {
  display: flex;
  gap: 10px;
}

.editor-alert {
  margin-top: 14px;
}

.editor-hint {
  margin: 14px 0 18px;
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--cm-primary-soft);
  font-size: 13px;
  line-height: 1.8;
  color: var(--cm-text-secondary);
}

.editor-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 20px;
  align-items: start;
}

.editor-canvas {
  position: relative;
}

.editor-canvas-inner {
  position: relative;
  height: 620px;
  border-radius: var(--cm-radius);
  overflow: hidden;
  border: 1px solid var(--cm-border);
  background: #fbfcff;
  box-shadow: var(--cm-shadow);
}

.editor-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13.5px;
  color: var(--cm-text-muted);
  pointer-events: none;
}

.editor-inspector {
  padding: 18px;
  border-radius: var(--cm-radius);
  border: 1px solid var(--cm-border);
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
}

.inspector-label {
  font-size: 12.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--cm-text-muted);
  text-transform: uppercase;
}

.inspector-type-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.type-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--cm-border);
  background: #fff;
  font-size: 12.5px;
  color: var(--cm-text);
  cursor: pointer;
  transition: border-color 0.15s ease, transform 0.15s ease;
}

.type-chip:hover:not(:disabled) {
  border-color: var(--cm-primary);
  transform: translateY(-1px);
}

.type-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.type-chip-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.inspector-form {
  margin-top: 12px;
}

.inspector-full {
  width: 100%;
}

.inspector-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 6px;
}

.inspector-desc {
  margin-top: 10px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--cm-text-secondary);
}

@media (max-width: 960px) {
  .editor-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
