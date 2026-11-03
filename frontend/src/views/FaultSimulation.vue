<script setup lang="ts">
const plannedItems = [
  '选择目标服务节点并注入故障（如延迟、错误率、宕机）',
  '基于拓扑关系推演故障传播路径与影响范围',
  '对比不同恢复策略的收敛时间与业务损失',
]
</script>

<template>
  <div>
    <header class="cm-page-header">
      <h1 class="cm-page-title">故障模拟</h1>
      <p class="cm-page-subtitle">
        面向云原生业务系统的故障注入与传播推演入口。当前页面仅完成路由与布局，
        交互逻辑与后端接口尚未实现。
      </p>
    </header>

    <div class="placeholder">
      <el-empty description="故障模拟功能尚未实现">
        <template #description>
          <p class="placeholder-title">故障模拟功能尚未实现</p>
          <p class="placeholder-sub">规划中的能力：</p>
          <ul class="placeholder-list">
            <li v-for="item in plannedItems" :key="item">{{ item }}</li>
          </ul>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<style scoped>
.placeholder {
  padding: 12px 0 32px;
}

.placeholder-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cm-text);
}

.placeholder-sub {
  margin-top: 14px;
  font-size: 13px;
  color: var(--cm-text-muted);
}

.placeholder-list {
  margin: 10px auto 0;
  padding: 0;
  max-width: 460px;
  list-style: none;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.placeholder-list li {
  position: relative;
  padding-left: 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--cm-text-secondary);
}

.placeholder-list li::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--cm-primary);
  opacity: 0.6;
}
</style>
