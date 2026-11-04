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
import { redundancyApi } from '@/api/redundancy'
import type {
  MemberRole,
  RedundancyGroup,
  RedundancyGroupPayload,
  RedundancyMemberPayload,
  RedundancyType,
} from '@/api/redundancy'
import { extractErrorMessage } from '@/api/errors'
import { NODE_STATUSES, NODE_TYPES, nodeTypeLabel } from '@/constants/topology'
import {
  REDUNDANCY_EDGE_COLOR,
  REDUNDANCY_TYPES,
  isStandbyTopology,
  memberRoleMeta,
  redundancyTypeMeta,
} from '@/constants/redundancy'

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
  redundancyRole: MemberRole | null
  redundancyGroupName: string | null
}

interface FlowEdgeData {
  /** 边类型：依赖关系 / 冗余关系（两者视觉样式不同）。 */
  kind: 'dependency' | 'redundancy'
  /** 依赖边特有：后端 edge id。 */
  edgeId?: number
  description?: string | null
  /** 冗余边特有。 */
  redundancyGroupId?: number
  redundancyLabel?: string
}

// 使用 shallowRef 避免 Vue 对 Vue Flow 复杂泛型类型做深层解包
const flowNodes = shallowRef<Node<FlowNodeData>[]>([])
const flowEdges = shallowRef<Edge<FlowEdgeData>[]>([])
const nodesById = ref<Record<number, ApiNode>>({})

// 冗余关系状态
const redundancyGroups = ref<RedundancyGroup[]>([])
const roleByNodeId = ref<Record<number, { role: MemberRole; groupName: string }>>({})
const groupDialogVisible = ref(false)
const savingGroup = ref(false)
const editingGroupId = ref<number | null>(null)

const groupForm = reactive({
  name: '',
  redundancyType: 'active_standby' as RedundancyType,
  description: '',
  primaryId: null as number | null,
  standbyIds: [] as number[],
  standbyPriorities: {} as Record<number, number>,
  activeIds: [] as number[],
})

const selectedNodeId = ref<number | null>(null)
const selectedEdgeId = ref<number | null>(null)
const savingNode = ref(false)
const savingLayout = ref(false)
const addingNode = ref(false)
const reversingEdge = ref(false)

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

/** 画布中的节点选项（用于冗余组表单）。 */
const nodeOptions = computed(() =>
  Object.values(nodesById.value).sort((left, right) => left.id - right.id),
)

/** 备用节点候选：排除已选主节点。 */
const standbyOptions = computed(() =>
  nodeOptions.value.filter((node) => node.id !== groupForm.primaryId),
)

const standbyMode = computed(() => isStandbyTopology(groupForm.redundancyType))

const selectedEdge = computed(() =>
  selectedEdgeId.value === null
    ? null
    : (flowEdges.value.find((edge) => edge.data?.edgeId === selectedEdgeId.value) ?? null),
)

const selectedEdgeDescription = computed(() => {
  const description = selectedEdge.value?.data?.description
  return typeof description === 'string' ? description : ''
})

/** 用节点名称展示依赖方向，避免只看到 id 造成误判。 */
function nodeName(id: number | string): string {
  const node = nodesById.value[Number(id)]
  return node ? node.name : `#${id}`
}

// --------------------------------------------------------------------------- //
// 数据映射
// --------------------------------------------------------------------------- //
function buildNodeData(node: ApiNode): FlowNodeData {
  const redundancy = roleByNodeId.value[node.id]
  return {
    label: node.name,
    nodeType: node.type,
    status: node.status,
    description: node.description,
    redundancyRole: redundancy?.role ?? null,
    redundancyGroupName: redundancy?.groupName ?? null,
  }
}

function toFlowNode(node: ApiNode): Node<FlowNodeData> {
  return {
    id: String(node.id),
    type: 'topology',
    position: { x: node.position_x, y: node.position_y },
    data: buildNodeData(node),
  }
}

function toFlowEdge(edge: TopologyEdge): Edge<FlowEdgeData> {
  return {
    id: `edge-${edge.id}`,
    source: String(edge.source_node_id),
    target: String(edge.target_node_id),
    markerEnd: MarkerType.ArrowClosed,
    data: { kind: 'dependency', edgeId: edge.id, description: edge.description },
  }
}

/** 根据后端冗余组生成可视化连线（主节点 → 备用节点，紫色虚线）。 */
function buildRedundancyEdges(groups: RedundancyGroup[]): Edge<FlowEdgeData>[] {
  const edges: Edge<FlowEdgeData>[] = []
  for (const group of groups) {
    const label = `${group.name}（${redundancyTypeMeta(group.redundancy_type).label}）`
    const primary = group.members.find((member) => member.member_role === 'primary')
    const standbys = group.members
      .filter((member) => member.member_role === 'standby')
      .sort((left, right) => (left.priority ?? 0) - (right.priority ?? 0) || left.id - right.id)

    const share = {
      animated: true,
      selectable: false,
      markerEnd: MarkerType.ArrowClosed,
      style: { stroke: REDUNDANCY_EDGE_COLOR, strokeDasharray: '6 4', strokeWidth: 2 },
    }

    if (primary) {
      for (const standby of standbys) {
        edges.push({
          ...share,
          id: `redundancy-${group.id}-${standby.id}`,
          source: String(primary.node_id),
          target: String(standby.node_id),
          data: { kind: 'redundancy', redundancyGroupId: group.id, redundancyLabel: label },
        })
      }
    }

    // 双活模式：成员两两相连，表示互为对等冗余
    const actives = group.members
      .filter((member) => member.member_role === 'active')
      .sort((left, right) => left.id - right.id)
    for (let index = 1; index < actives.length; index += 1) {
      edges.push({
        ...share,
        id: `redundancy-${group.id}-${actives[0].id}-${actives[index].id}`,
        source: String(actives[0].node_id),
        target: String(actives[index].node_id),
        data: { kind: 'redundancy', redundancyGroupId: group.id, redundancyLabel: label },
      })
    }
  }
  return edges
}

function rebuildFlowEdges() {
  const dependencies = (topology.value?.edges ?? []).map(toFlowEdge)
  flowEdges.value = [...dependencies, ...buildRedundancyEdges(redundancyGroups.value)]
}

function syncFlowNodeData(node: ApiNode) {
  flowNodes.value = flowNodes.value.map((item) =>
    item.id === String(node.id) ? { ...item, data: buildNodeData(node) } : item,
  )
}

function applyGroupRoles(groups: RedundancyGroup[]) {
  redundancyGroups.value = groups
  const mapping: Record<number, { role: MemberRole; groupName: string }> = {}
  for (const group of groups) {
    for (const member of group.members) {
      mapping[member.node_id] = { role: member.member_role, groupName: group.name }
    }
  }
  roleByNodeId.value = mapping
  // 同步节点上的冗余徽标
  flowNodes.value = flowNodes.value.map((item) => {
    const node = nodesById.value[Number(item.id)]
    return node ? { ...item, data: buildNodeData(node) } : item
  })
}

// --------------------------------------------------------------------------- //
// 加载
// --------------------------------------------------------------------------- //
async function loadGroups() {
  try {
    const { data } = await redundancyApi.list(topologyId.value)
    applyGroupRoles(data)
  } catch {
    applyGroupRoles([])
  }
  rebuildFlowEdges()
}

async function loadTopology() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await topologyApi.detail(topologyId.value)
    topology.value = data
    nodesById.value = Object.fromEntries(data.nodes.map((node) => [node.id, node]))
    roleByNodeId.value = {}
    flowNodes.value = data.nodes.map(toFlowNode)
    selectedNodeId.value = null
    selectedEdgeId.value = null
    await loadGroups()
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
    delete nodesById.value[id]
    selectedNodeId.value = null
    if (topology.value) {
      topology.value.edges = topology.value.edges.filter(
        (edge) => edge.source_node_id !== id && edge.target_node_id !== id,
      )
    }
    // 后端会同步清理该节点的冗余成员（并可能删除失效的冗余组），重新拉取
    await loadGroups()
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
    topology.value.edges = [...topology.value.edges, data]
    rebuildFlowEdges()
    ElMessage.success(`依赖关系已创建：${nodeName(sourceId)} 依赖 ${nodeName(targetId)}`)
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '创建依赖关系失败'))
  }
}

async function removeSelectedEdge() {
  if (!topology.value || selectedEdgeId.value === null) return
  const edgeId = selectedEdgeId.value
  try {
    await topologyApi.removeEdge(topology.value.id, edgeId)
    topology.value.edges = topology.value.edges.filter((edge) => edge.id !== edgeId)
    rebuildFlowEdges()
    selectedEdgeId.value = null
    ElMessage.success('依赖关系已删除')
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '删除依赖关系失败'))
  }
}

/** 反转依赖方向：先建反向边（若已存在则后端返回冲突），成功后再删除原边。 */
async function reverseSelectedEdge() {
  if (!topology.value || !selectedEdge.value) return
  const edgeId = selectedEdge.value.data?.edgeId
  if (typeof edgeId !== 'number') return
  const sourceId = Number(selectedEdge.value.source)
  const targetId = Number(selectedEdge.value.target)
  if (!Number.isFinite(sourceId) || !Number.isFinite(targetId)) return

  reversingEdge.value = true
  try {
    // 先创建反向边：若反向依赖已存在，后端返回冲突，原边保持不变
    const { data } = await topologyApi.addEdge(topology.value.id, {
      source_node_id: targetId,
      target_node_id: sourceId,
    })
    topology.value.edges = [...topology.value.edges, data]
    try {
      await topologyApi.removeEdge(topology.value.id, edgeId)
      topology.value.edges = topology.value.edges.filter((item) => item.id !== edgeId)
      selectedEdgeId.value = data.id
      rebuildFlowEdges()
      ElMessage.success(
        `依赖方向已反转：${nodeName(targetId)} 依赖 ${nodeName(sourceId)}`,
      )
    } catch (error) {
      rebuildFlowEdges()
      ElMessage.warning(
        extractErrorMessage(error, '反向依赖已创建，但删除原依赖失败，请检查该拓扑的依赖关系'),
      )
    }
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '反转依赖方向失败'))
  } finally {
    reversingEdge.value = false
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

// --------------------------------------------------------------------------- //
// 冗余关系（显式主备 / 双活）
// --------------------------------------------------------------------------- //
function resetGroupForm() {
  groupForm.name = ''
  groupForm.redundancyType = 'active_standby'
  groupForm.description = ''
  groupForm.primaryId = null
  groupForm.standbyIds = []
  groupForm.standbyPriorities = {}
  groupForm.activeIds = []
}

function openCreateGroup() {
  editingGroupId.value = null
  resetGroupForm()
  groupForm.name = `冗余组 ${redundancyGroups.value.length + 1}`
  groupDialogVisible.value = true
}

function openEditGroup(group: RedundancyGroup) {
  editingGroupId.value = group.id
  resetGroupForm()
  groupForm.name = group.name
  groupForm.redundancyType = group.redundancy_type
  groupForm.description = group.description ?? ''

  const primary = group.members.find((member) => member.member_role === 'primary')
  const standbys = group.members.filter((member) => member.member_role === 'standby')
  groupForm.primaryId = primary?.node_id ?? null
  groupForm.standbyIds = standbys.map((member) => member.node_id)
  const priorities: Record<number, number> = {}
  standbys.forEach((member, index) => {
    priorities[member.node_id] = member.priority ?? index + 1
  })
  groupForm.standbyPriorities = priorities
  groupForm.activeIds = group.members
    .filter((member) => member.member_role === 'active')
    .map((member) => member.node_id)
  groupDialogVisible.value = true
}

function onGroupTypeChange() {
  groupForm.primaryId = null
  groupForm.standbyIds = []
  groupForm.standbyPriorities = {}
  groupForm.activeIds = []
}

function onStandbySelectionChange() {
  const next: Record<number, number> = {}
  groupForm.standbyIds.forEach((nodeId, index) => {
    next[nodeId] = groupForm.standbyPriorities[nodeId] ?? index + 1
  })
  groupForm.standbyPriorities = next
}

function buildGroupPayload(): RedundancyGroupPayload | null {
  if (!groupForm.name.trim()) {
    ElMessage.warning('请填写冗余组名称')
    return null
  }

  const members: RedundancyMemberPayload[] = []
  if (standbyMode.value) {
    if (groupForm.primaryId === null) {
      ElMessage.warning('请选择主节点')
      return null
    }
    if (groupForm.standbyIds.length === 0) {
      ElMessage.warning('请至少选择一个备用节点')
      return null
    }
    members.push({ node_id: groupForm.primaryId, member_role: 'primary', priority: null })
    for (const nodeId of groupForm.standbyIds) {
      members.push({
        node_id: nodeId,
        member_role: 'standby',
        priority: groupForm.standbyPriorities[nodeId] ?? null,
      })
    }
  } else {
    if (groupForm.activeIds.length < 2) {
      ElMessage.warning('双活模式至少需要两个成员')
      return null
    }
    for (const nodeId of groupForm.activeIds) {
      members.push({ node_id: nodeId, member_role: 'active', priority: null })
    }
  }

  return {
    name: groupForm.name.trim(),
    redundancy_type: groupForm.redundancyType,
    description: groupForm.description.trim() || null,
    members,
  }
}

async function submitGroupForm() {
  if (!topology.value) return
  const payload = buildGroupPayload()
  if (!payload) return

  savingGroup.value = true
  try {
    if (editingGroupId.value === null) {
      await redundancyApi.create(topology.value.id, payload)
      ElMessage.success('冗余组已创建')
    } else {
      await redundancyApi.update(editingGroupId.value, payload)
      ElMessage.success('冗余组已更新')
    }
    groupDialogVisible.value = false
    await loadGroups()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '保存冗余组失败'))
  } finally {
    savingGroup.value = false
  }
}

async function removeGroup(group: RedundancyGroup) {
  try {
    await ElMessageBox.confirm(
      `确认删除冗余组「${group.name}」？删除后 failover 将不再认为存在该备用节点。`,
      '删除冗余组',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    await redundancyApi.remove(group.id)
    ElMessage.success('冗余组已删除')
    await loadGroups()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '删除冗余组失败'))
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
      从节点<strong>底部</strong>圆点（「依赖对方」）拖到另一节点<strong>顶部</strong>圆点（「被依赖」）创建依赖
      （<strong>箭头方向 = 依赖方向</strong>：A → B 表示 A 依赖 B）；点击节点或连线可在右侧编辑或删除，
      若方向建反，可选中连线后点击「反转依赖方向」。
      冗余关系（主备 / 双活）是<strong>独立于依赖边</strong>的声明，用于恢复策略的备用节点判定，
      可在右侧「冗余关系」区域创建。
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

        <div class="editor-legend">
          <span class="legend-item">
            <span class="legend-line is-dependency"></span>普通依赖关系（实线箭头，箭头指向被依赖方）
          </span>
          <span class="legend-item">
            <span class="legend-line is-redundancy"></span>主备关系（紫色虚线，主节点 → 备用节点）
          </span>
          <span class="legend-item">
            <span class="legend-badge is-primary">主节点</span>冗余组主节点
          </span>
          <span class="legend-item">
            <span class="legend-badge is-standby">备用节点</span>冗余组备用节点
          </span>
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

        <div class="inspector-tools">
          <div class="inspector-tools-head">
            <p class="inspector-label">冗余关系</p>
            <el-button
              link
              type="primary"
              size="small"
              :disabled="flowNodes.length < 2"
              @click="openCreateGroup"
            >
              新建冗余组
            </el-button>
          </div>
          <p v-if="redundancyGroups.length === 0" class="inspector-desc cm-muted">
            尚未声明冗余关系。failover（备用节点切换）只认可显式主备关系，
            不会根据「同类型节点」自动推断备用节点。
          </p>
          <ul v-else class="group-list">
            <li v-for="group in redundancyGroups" :key="group.id" class="group-item">
              <div class="group-item-head">
                <span class="group-name">{{ group.name }}</span>
                <span
                  class="group-type"
                  :style="{ color: redundancyTypeMeta(group.redundancy_type).color }"
                >
                  {{ redundancyTypeMeta(group.redundancy_type).label }}
                </span>
              </div>
              <div class="group-members">
                <span
                  v-for="member in group.members"
                  :key="member.id"
                  class="group-member"
                  :style="{ borderColor: memberRoleMeta(member.member_role).color }"
                >
                  {{ memberRoleMeta(member.member_role).label }}：{{ member.node_name }}
                  <template v-if="member.priority !== null">（P{{ member.priority }}）</template>
                </span>
              </div>
              <div class="group-actions">
                <el-button link type="primary" size="small" @click="openEditGroup(group)">
                  编辑
                </el-button>
                <el-button link type="danger" size="small" @click="removeGroup(group)">
                  删除
                </el-button>
              </div>
            </li>
          </ul>
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
            <strong>{{ nodeName(selectedEdge.source) }}</strong>
            →
            <strong>{{ nodeName(selectedEdge.target) }}</strong>
          </p>
          <p class="inspector-desc cm-muted">
            依赖方向：左侧节点<strong>依赖</strong>右侧节点（箭头指向被依赖方）。
            若方向建反，可点击下方「反转依赖方向」修正，无需删除重建。
          </p>
          <p class="inspector-desc cm-muted">
            {{ selectedEdgeDescription || '无说明' }}
          </p>
          <div class="inspector-actions">
            <el-button
              type="primary"
              plain
              :loading="reversingEdge"
              @click="reverseSelectedEdge"
            >
              反转依赖方向
            </el-button>
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

    <el-dialog
      v-model="groupDialogVisible"
      :title="editingGroupId === null ? '新建冗余组' : '编辑冗余组'"
      width="540px"
    >
      <el-form label-position="top" @submit.prevent>
        <el-form-item label="名称">
          <el-input v-model="groupForm.name" maxlength="128" />
        </el-form-item>
        <el-form-item label="冗余模式">
          <el-select
            v-model="groupForm.redundancyType"
            class="inspector-full"
            @change="onGroupTypeChange"
          >
            <el-option
              v-for="item in REDUNDANCY_TYPES"
              :key="item.value"
              :label="item.label"
              :value="item.value"
            />
          </el-select>
        </el-form-item>

        <template v-if="standbyMode">
          <el-form-item label="主节点">
            <el-select
              v-model="groupForm.primaryId"
              class="inspector-full"
              placeholder="选择主节点"
            >
              <el-option
                v-for="node in nodeOptions"
                :key="node.id"
                :label="`${node.name}（${nodeTypeLabel(node.type)}）`"
                :value="node.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="备用节点（可多选）">
            <el-select
              v-model="groupForm.standbyIds"
              class="inspector-full"
              multiple
              placeholder="选择备用节点"
              @change="onStandbySelectionChange"
            >
              <el-option
                v-for="node in standbyOptions"
                :key="node.id"
                :label="`${node.name}（${nodeTypeLabel(node.type)}）`"
                :value="node.id"
              />
            </el-select>
          </el-form-item>
          <div v-if="groupForm.standbyIds.length > 0" class="priority-list">
            <p class="inspector-label">备用优先级（数值越小越优先）</p>
            <div
              v-for="nodeId in groupForm.standbyIds"
              :key="nodeId"
              class="priority-row"
            >
              <span class="priority-name">{{ nodesById[nodeId]?.name ?? `节点#${nodeId}` }}</span>
              <el-input-number
                v-model="groupForm.standbyPriorities[nodeId]"
                :min="0"
                :step="1"
                size="small"
              />
            </div>
          </div>
        </template>

        <template v-else>
          <el-form-item label="双活成员（至少两个）">
            <el-select
              v-model="groupForm.activeIds"
              class="inspector-full"
              multiple
              placeholder="选择双活成员"
            >
              <el-option
                v-for="node in nodeOptions"
                :key="node.id"
                :label="`${node.name}（${nodeTypeLabel(node.type)}）`"
                :value="node.id"
              />
            </el-select>
          </el-form-item>
        </template>

        <el-form-item label="说明">
          <el-input v-model="groupForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>

      <p class="dialog-hint">
        冗余关系与依赖边（业务调用方向）相互独立：依赖边进入传播分析，冗余关系进入恢复策略。
        当前版本一个节点最多属于一个冗余组，且不会执行真实切流，
        也不校验真实容量、网络与数据同步。
      </p>

      <template #footer>
        <el-button @click="groupDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="savingGroup" @click="submitGroupForm">
          保存
        </el-button>
      </template>
    </el-dialog>
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

.inspector-tools-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.editor-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 20px;
  margin-top: 12px;
  font-size: 12.5px;
  color: var(--cm-text-secondary);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-line {
  display: inline-block;
  width: 34px;
  height: 0;
  border-top-width: 2px;
  border-top-style: solid;
}

.legend-line.is-dependency {
  border-top-color: #94a3b8;
}

.legend-line.is-redundancy {
  border-top-style: dashed;
  border-top-color: v-bind(REDUNDANCY_EDGE_COLOR);
}

.legend-badge {
  display: inline-flex;
  align-items: center;
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px dashed currentColor;
  background: #faf7ff;
  font-size: 11px;
  font-weight: 700;
}

.legend-badge.is-primary {
  color: #7c3aed;
}

.legend-badge.is-standby {
  color: #0ea5e9;
}

.group-list {
  list-style: none;
  margin: 12px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.group-item {
  padding: 10px 12px;
  border-radius: 10px;
  border: 1px dashed #c4b5fd;
  background: #faf8ff;
}

.group-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.group-name {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  word-break: break-all;
}

.group-type {
  font-size: 11.5px;
  font-weight: 600;
  flex: none;
}

.group-members {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}

.group-member {
  padding: 1px 7px;
  border-radius: 999px;
  border: 1px solid var(--cm-border);
  background: #fff;
  font-size: 11.5px;
  color: var(--cm-text-secondary);
}

.group-actions {
  display: flex;
  gap: 4px;
  margin-top: 6px;
}

.priority-list {
  margin-bottom: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: var(--cm-primary-soft);
}

.priority-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 8px;
  font-size: 13px;
}

.priority-name {
  color: var(--cm-text-secondary);
  word-break: break-all;
}

.dialog-hint {
  margin-top: 4px;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--cm-primary-soft);
  font-size: 12px;
  line-height: 1.7;
  color: var(--cm-text-secondary);
}

@media (max-width: 960px) {
  .editor-body {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
