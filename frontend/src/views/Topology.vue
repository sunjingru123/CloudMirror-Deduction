<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { topologyApi } from '@/api/topology'
import type { TopologySummary } from '@/api/topology'
import { extractErrorMessage } from '@/api/errors'

const router = useRouter()

const loading = ref(false)
const loadError = ref('')
const topologies = ref<TopologySummary[]>([])

const dialogVisible = ref(false)
const submitting = ref(false)
const form = reactive({ name: '', description: '' })
const formRef = ref()

const formRules = {
  name: [
    { required: true, message: '请输入拓扑名称', trigger: 'blur' },
    { max: 128, message: '名称不超过 128 个字符', trigger: 'blur' },
  ],
}

async function loadTopologies() {
  loading.value = true
  loadError.value = ''
  try {
    const { data } = await topologyApi.list()
    topologies.value = data
  } catch (error) {
    loadError.value = extractErrorMessage(error, '加载拓扑列表失败')
  } finally {
    loading.value = false
  }
}

function openCreateDialog() {
  form.name = ''
  form.description = ''
  dialogVisible.value = true
}

async function submitCreate() {
  if (!formRef.value) return
  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true
  try {
    const { data } = await topologyApi.create({
      name: form.name.trim(),
      description: form.description.trim() || null,
    })
    ElMessage.success('拓扑创建成功')
    dialogVisible.value = false
    router.push(`/topology/${data.id}`)
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '创建拓扑失败'))
  } finally {
    submitting.value = false
  }
}

function openEditor(topology: TopologySummary) {
  router.push(`/topology/${topology.id}`)
}

async function removeTopology(topology: TopologySummary) {
  try {
    await ElMessageBox.confirm(
      `确认删除拓扑「${topology.name}」？其节点与依赖关系将一并删除。`,
      '删除确认',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  try {
    await topologyApi.remove(topology.id)
    ElMessage.success('拓扑已删除')
    await loadTopologies()
  } catch (error) {
    ElMessage.error(extractErrorMessage(error, '删除拓扑失败'))
  }
}

function formatTime(value: string) {
  return value ? value.replace('T', ' ').slice(0, 19) : '-'
}

onMounted(loadTopologies)
</script>

<template>
  <div class="topology-list">
    <header class="cm-page-header list-header">
      <div>
        <h1 class="cm-page-title">系统拓扑</h1>
        <p class="cm-page-subtitle">
          管理云原生业务系统的拓扑图。依赖方向约定：
          <strong>边 A → B 表示「A 依赖 B」</strong>，箭头指向被依赖方 B；
          当 B 故障时，A 可能受影响。
        </p>
      </div>
      <div class="list-actions">
        <el-button :loading="loading" @click="loadTopologies">刷新</el-button>
        <el-button type="primary" @click="openCreateDialog">新建拓扑</el-button>
      </div>
    </header>

    <el-alert
      v-if="loadError"
      class="list-alert"
      type="error"
      :title="loadError"
      show-icon
      :closable="false"
    >
      <template #default>
        <span>请确认后端服务已启动，然后点击「刷新」重试。</span>
      </template>
    </el-alert>

    <el-table
      v-loading="loading"
      :data="topologies"
      class="list-table"
      empty-text="暂无拓扑，点击右上角「新建拓扑」开始"
      @row-click="(row) => openEditor(row as unknown as TopologySummary)"
    >
      <el-table-column prop="name" label="名称" min-width="180">
        <template #default="{ row }">
          <span class="list-name">{{ row.name }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="description" label="描述" min-width="220">
        <template #default="{ row }">
          <span :class="{ 'cm-muted': !row.description }">
            {{ row.description || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="node_count" label="节点数" width="90" align="center" />
      <el-table-column prop="edge_count" label="依赖数" width="90" align="center" />
      <el-table-column label="更新时间" width="180">
        <template #default="{ row }">
          <span class="cm-muted">{{ formatTime(row.updated_at) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="170" align="right">
        <template #default="{ row }">
          <el-button link type="primary" @click.stop="openEditor(row as unknown as TopologySummary)">
            编辑
          </el-button>
          <el-button link type="danger" @click.stop="removeTopology(row as unknown as TopologySummary)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogVisible" title="新建拓扑" width="460px">
      <el-form
        ref="formRef"
        :model="form"
        :rules="formRules"
        label-position="top"
        @submit.prevent
      >
        <el-form-item label="拓扑名称" prop="name">
          <el-input v-model="form.name" maxlength="128" placeholder="例如：电商订单系统" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input
            v-model="form.description"
            type="textarea"
            :rows="3"
            maxlength="512"
            placeholder="选填，描述该业务系统"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submitting" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.list-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}

.list-actions {
  display: flex;
  gap: 10px;
}

.list-alert {
  margin-bottom: 18px;
}

.list-table {
  --el-table-border-color: var(--cm-border);
  background: transparent;
  border-radius: var(--cm-radius);
  overflow: hidden;
}

.list-table :deep(.el-table__row) {
  cursor: pointer;
}

.list-name {
  font-weight: 600;
  color: var(--cm-primary);
}
</style>
