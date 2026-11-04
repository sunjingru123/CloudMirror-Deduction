<script setup lang="ts">
import { computed } from 'vue'
import { Handle, Position } from '@vue-flow/core'

import type { NodeStatus, NodeType } from '@/api/topology'
import { nodeStatusMeta, nodeTypeMeta } from '@/constants/topology'

export interface TopologyNodeData {
  label: string
  nodeType: NodeType
  status: NodeStatus
  description: string | null
}

const props = defineProps<{
  data: TopologyNodeData
  selected?: boolean
}>()

const typeMeta = computed(() => nodeTypeMeta(props.data.nodeType))
const statusMeta = computed(() => nodeStatusMeta(props.data.status))
const label = computed(() => props.data.label)
</script>

<template>
  <div
    class="tn"
    :class="{ 'is-selected': props.selected }"
    :style="{ '--tn-color': typeMeta.color }"
  >
    <!-- 上方为 target：箭头由依赖方指向被依赖方 -->
    <Handle type="target" :position="Position.Top" />

    <header class="tn-head">
      <span class="tn-type">{{ typeMeta.label }}</span>
      <span class="tn-status" :style="{ color: statusMeta.color }">
        <i class="tn-dot" :style="{ background: statusMeta.color }"></i>
        {{ statusMeta.label }}
      </span>
    </header>

    <div class="tn-name">{{ label }}</div>

    <!-- 下方为 source：从这里拖出连线表示「当前节点依赖目标节点」 -->
    <Handle type="source" :position="Position.Bottom" />
  </div>
</template>

<style scoped>
.tn {
  --tn-color: #64748b;
  min-width: 148px;
  padding: 8px 12px 10px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-left: 3px solid var(--tn-color);
  box-shadow: 0 6px 18px rgba(15, 42, 90, 0.08);
  font-size: 12px;
  transition: box-shadow 0.15s ease, border-color 0.15s ease;
}

.tn.is-selected {
  border-color: var(--cm-primary);
  box-shadow: 0 0 0 2px rgba(31, 111, 235, 0.25), 0 8px 22px rgba(15, 42, 90, 0.12);
}

.tn-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}

.tn-type {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.3px;
  color: var(--tn-color);
}

.tn-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
}

.tn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.tn-name {
  font-size: 13.5px;
  font-weight: 600;
  color: #0f172a;
  word-break: break-all;
}
</style>
