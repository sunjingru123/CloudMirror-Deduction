<script setup lang="ts">
import { RouterLink, RouterView } from 'vue-router'

const navItems = [
  { path: '/', label: '首页' },
  { path: '/topology', label: '系统拓扑' },
  { path: '/fault-simulation', label: '故障模拟' },
  { path: '/recovery', label: '恢复策略' },
  { path: '/history', label: '历史记录' },
]
</script>

<template>
  <div class="cm-app">
    <header class="cm-header">
      <div class="cm-brand">
        <img src="/favicon.svg" alt="CloudMirror logo" />
        <span>云镜推演</span>
        <span class="cm-brand-sub">CloudMirror Deduction</span>
      </div>

      <nav class="cm-nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          class="cm-nav-item"
          :class="{ 'is-active': $route.path === item.path }"
        >
          {{ item.label }}
        </RouterLink>
      </nav>
    </header>

    <main class="cm-main">
      <RouterView v-slot="{ Component }">
        <Transition name="cm-fade" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>

    <footer class="cm-footer">
      云镜推演 · 面向云原生业务系统的故障传播分析与恢复策略优化平台
    </footer>
  </div>
</template>
