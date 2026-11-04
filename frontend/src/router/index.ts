import { createRouter, createWebHistory } from 'vue-router'
import type { RouteRecordRaw } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'dashboard',
    component: () => import('@/views/Dashboard.vue'),
    meta: { title: '首页 Dashboard' },
  },
  {
    path: '/topology',
    name: 'topology',
    component: () => import('@/views/Topology.vue'),
    meta: { title: '系统拓扑 Topology' },
  },
  {
    path: '/topology/:id(\\d+)',
    name: 'topology-editor',
    component: () => import('@/views/TopologyEditor.vue'),
    meta: { title: '拓扑编辑 Topology Editor' },
  },
  {
    path: '/fault-simulation',
    name: 'fault-simulation',
    component: () => import('@/views/FaultSimulation.vue'),
    meta: { title: '故障模拟 Fault Simulation' },
  },
  {
    path: '/history',
    name: 'history',
    component: () => import('@/views/History.vue'),
    meta: { title: '历史记录 History' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

const APP_TITLE = '云镜推演 · CloudMirror Deduction'

router.afterEach((to) => {
  const title = to.meta.title as string | undefined
  document.title = title ? `${title} | ${APP_TITLE}` : APP_TITLE
})

export default router
