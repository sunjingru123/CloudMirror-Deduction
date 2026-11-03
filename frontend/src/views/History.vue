<script setup lang="ts">
// 历史记录页面：当前仅提供布局占位，尚未接入后端与数据库。
</script>

<template>
  <div>
    <header class="cm-page-header">
      <h1 class="cm-page-title">历史记录</h1>
      <p class="cm-page-subtitle">
        记录并回溯历次故障推演与恢复策略对比结果。当前页面仅完成路由与布局，
        数据接口尚未实现。
      </p>
    </header>

    <div class="history-empty">
      <el-empty description="暂无历史记录">
        <template #description>
          <p class="history-title">暂无历史记录</p>
          <p class="history-sub">历史记录的数据存储与查询接口尚未实现。</p>
        </template>
      </el-empty>
    </div>
  </div>
</template>

<style scoped>
.history-empty {
  padding: 12px 0 32px;
}

.history-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--cm-text);
}

.history-sub {
  margin-top: 8px;
  font-size: 13px;
  color: var(--cm-text-muted);
}
</style>
