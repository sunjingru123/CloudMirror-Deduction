# 前端应用（Vue 3 + Vite + TypeScript）

云镜推演前端，基于 **Vue 3 / Vite / TypeScript / Element Plus / Vue Flow / Axios**。

> 当前阶段：已完成项目脚手架、路由、Element Plus 与 Vue Flow 接入、Axios 封装、
> 首页后端连通性检测，**系统拓扑管理**（拓扑列表 + Vue Flow 拓扑编辑器），
> 以及**故障模拟与传播可视化**（真实注入 / 恢复 / 分析 API + 画布高亮）。
> 历史记录页面仍为占位。

## 依赖方向约定

> Vue Flow 中箭头由 A 指向 B 表示 **A 依赖 B**；节点**底部**为 source 连接点，
> **顶部**为 target 连接点，与后端 `source_node_id` / `target_node_id` 一一对应。

## 目录结构

```
frontend/
├── public/favicon.svg
├── src/
│   ├── main.ts                    # Element Plus / 图标 / Vue Flow 样式 / 路由
│   ├── App.vue                    # 顶部导航 + 内容区布局
│   ├── env.d.ts
│   ├── api/
│   │   ├── http.ts                # Axios 实例（统一 baseURL、超时）
│   │   ├── errors.ts              # 错误信息提取
│   │   ├── health.ts              # GET /api/health
│   │   ├── topology.ts            # 拓扑 / 节点 / 依赖接口与类型
│   │   ├── fault.ts               # 故障注入 / 恢复接口与类型
│   │   └── analysis.ts            # 传播分析接口与类型
│   ├── components/TopologyNode.vue # Vue Flow 自定义节点（支持传播高亮）
│   ├── constants/
│   │   ├── topology.ts             # 节点类型 / 状态元数据
│   │   └── fault.ts                # 故障类型 / 严重程度 / 影响等级配色
│   ├── router/index.ts
│   ├── styles/main.css
│   └── views/
│       ├── Dashboard.vue           # 首页（项目介绍 + 后端连接状态）
│       ├── Topology.vue            # 拓扑列表（新建 / 删除 / 进入编辑）
│       ├── TopologyEditor.vue      # Vue Flow 拓扑编辑器
│       ├── FaultSimulation.vue     # 故障注入 / 恢复 / 传播分析与可视化
│       └── History.vue             # 占位
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
└── .env.example
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
npm run build   # vue-tsc 类型检查 + vite build，产物输出到 dist/
```

## 配置

复制 `.env.example` 为 `.env` 或 `.env.local` 后按需修改：

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `VITE_API_BASE_URL` | 后端 API 基础地址（不含 `/api`） | `http://127.0.0.1:8000` |

## 已实现内容

- 路由：`/`、`/topology`（列表）、`/topology/:id`（编辑器）、`/fault-simulation`、`/history`。
- 首页：挂载后请求 `/api/health`，真实展示「已连接 / 后端未连接」，后端不可用时不崩溃。
- 拓扑列表：从后端加载列表，支持新建、删除、点击进入编辑。
- 拓扑编辑器（Vue Flow）：读取后端节点与边并真实渲染；添加不同类型的节点；
  拖动节点并自动保存位置；拖拽连线创建依赖（调用后端，拒绝自依赖与重复边）；
  点击节点编辑名称 / 类型 / 状态 / 描述；删除节点与依赖；重命名拓扑；批量保存布局。
- 故障模拟（FaultSimulation）：选择拓扑并加载其节点与故障；注入故障（节点 / 类型 / 严重程度 / 描述）；
  查看并恢复故障；点击「开始传播分析」调用真实分析 API；进入拓扑时静默加载最近一次分析结果。
- 传播可视化：故障源红色、直接影响橙色、间接影响黄色、正常节点保持原样；
  传播路径边高亮并带流动动画；展示影响等级 / 传播距离 / 来源故障与传播路径；
  分析面板展示故障源数、受影响节点数、直接 / 间接影响数、影响比例与路径明细；支持清除高亮。
- 全部增删改与分析均调用真实后端 API，不使用本地假数据；操作失败时通过 Element Plus 消息提示。

## 未实现内容

- 历史记录页面的业务功能（推演历史查询与回溯）；
- 恢复策略优化与对比分析；
- 拓扑数据的导入 / 导出、撤销等高级编辑能力。
