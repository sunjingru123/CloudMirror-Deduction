<script setup lang="ts">
import { VueFlow } from '@vue-flow/core'
import type { Edge, Node } from '@vue-flow/core'

// 说明：以下节点仅用于验证 Vue Flow 画布渲染能力，
// 属于前端占位示意数据，尚未接入后端拓扑接口。
const nodes: Node[] = [
  { id: 'gateway', label: 'API 网关', position: { x: 40, y: 150 } },
  { id: 'order', label: '订单服务', position: { x: 300, y: 60 } },
  { id: 'payment', label: '支付服务', position: { x: 300, y: 240 } },
  { id: 'inventory', label: '库存服务', position: { x: 560, y: 150 } },
]

const edges: Edge[] = [
  { id: 'e-gateway-order', source: 'gateway', target: 'order', animated: true },
  { id: 'e-gateway-payment', source: 'gateway', target: 'payment', animated: true },
  { id: 'e-order-inventory', source: 'order', target: 'inventory' },
  { id: 'e-payment-inventory', source: 'payment', target: 'inventory' },
]
</script>

<template>
  <div class="topology">
    <header class="cm-page-header">
      <h1 class="cm-page-title">系统拓扑</h1>
      <p class="cm-page-subtitle">
        云原生业务系统的服务依赖关系可视化。当前为 Vue Flow 画布占位示意，
        节点与连线尚未接入后端拓扑数据。
      </p>
    </header>

    <div class="topology-canvas">
      <VueFlow :nodes="nodes" :edges="edges" fit-view-on-init :default-viewport="{ zoom: 1 }" />
    </div>
  </div>
</template>

<style scoped>
.topology-canvas {
  height: 520px;
  border-radius: var(--cm-radius);
  overflow: hidden;
  background: var(--cm-surface);
  box-shadow: var(--cm-shadow);
  border: 1px solid var(--cm-border);
}
</style>
