# 前端应用（Vue 3 + Vite + TypeScript）

云镜推演前端，基于 **Vue 3 / Vite / TypeScript / Element Plus / Vue Flow / Axios**。

> 当前阶段：工程初始化。已完成项目脚手架、路由、Element Plus 与 Vue Flow 接入、
> Axios 封装与首页后端连通性检测；各业务页面仅为布局占位，尚无业务功能。

## 目录结构

```
frontend/
├── public/
│   └── favicon.svg
├── src/
│   ├── main.ts              # 应用入口（Element Plus / 图标 / Vue Flow 样式 / 路由）
│   ├── App.vue              # 顶部导航 + 内容区布局
│   ├── env.d.ts             # 环境变量与 .vue 类型声明
│   ├── api/
│   │   ├── http.ts          # Axios 实例（统一 baseURL、超时）
│   │   └── health.ts        # GET /api/health 封装
│   ├── router/
│   │   └── index.ts         # Vue Router 配置
│   ├── styles/
│   │   └── main.css         # 全局浅色科技风样式
│   └── views/
│       ├── Dashboard.vue        # 首页（项目介绍 + 后端连接状态）
│       ├── Topology.vue         # 系统拓扑（Vue Flow 画布占位）
│       ├── FaultSimulation.vue  # 故障模拟（占位）
│       └── History.vue          # 历史记录（占位）
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
├── .env.example
└── README.md
```

## 本地启动

```bash
cd frontend
npm install
npm run dev
```

默认开发地址：<http://127.0.0.1:5173>

## 生产构建

```bash
npm run build
```

构建产物输出到 `dist/`（已被 `.gitignore` 忽略）。

## 配置

复制 `.env.example` 为 `.env` 或 `.env.local` 后按需修改：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 后端 API 基础地址（不含 `/api`） | `http://127.0.0.1:8000` |

## 已实现内容

- Vue Router：首页、系统拓扑、故障模拟、历史记录四个路由。
- Element Plus 与图标全局注册，浅色科技风全局样式。
- Vue Flow 画布接入（拓扑页占位示意）。
- Axios 实例封装，统一后端基础地址。
- 首页挂载后自动请求 `/api/health`，真实展示「已连接 / 后端未连接」，
  后端不可用时不会崩溃。
