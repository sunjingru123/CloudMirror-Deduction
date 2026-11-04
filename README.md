# 云镜推演 (CloudMirror Deduction)

> 面向云原生业务系统的**故障传播分析**与**恢复策略优化**平台。

## 项目状态

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 第一阶段 | 工程初始化、健康检查、前后端基础联调 | ✅ 已完成 |
| 第二阶段 | 系统拓扑管理与数据建模（拓扑 / 节点 / 依赖 CRUD + Vue Flow 编辑器） | ✅ 已完成 |
| 第三阶段 | 故障传播分析、恢复策略优化 | 🚧 待开发 |

已实现的功能均可通过真实后端 API 操作并持久化到 SQLite；**尚未实现**故障注入、传播推演、
恢复策略优化与历史记录等业务功能。

## 依赖方向约定（重要）

> **边 `A → B` 表示「A 依赖 B」。**
> 即 `source_node_id = A`（依赖方）、`target_node_id = B`（被依赖方）。

- Vue Flow 画布中，箭头由 A 指向 B（指向被依赖方），与后端字段完全一致。
- 故障传播方向与依赖方向**相反**：依赖边 `A → B` 对应传播路径 `B → A`，
  即 **B 故障时 A 可能受影响**。
- 该约定在 `backend/app/models/topology.py`、`backend/app/api/topologies.py` 与
  前端 `frontend/src/api/topology.ts` 中保持一致，避免箭头方向与算法方向不一致。

## 核心功能

| 功能 | 状态 |
| --- | --- |
| 健康检查联调（`GET /api/health`） | ✅ 已实现 |
| 拓扑的创建 / 列表 / 详情 / 重命名 / 删除 | ✅ 已实现 |
| 节点的添加 / 编辑（名称、类型、状态、描述、位置）/ 删除 | ✅ 已实现 |
| 依赖关系的创建 / 删除（禁止自依赖与重复边） | ✅ 已实现 |
| 删除节点时级联删除相关依赖 | ✅ 已实现 |
| 拓扑、节点、依赖持久化到 SQLite | ✅ 已实现 |
| Vue Flow 真实渲染后端节点与边、拖动保存位置 | ✅ 已实现 |
| 故障注入与传播推演 | 🚧 待开发 |
| 恢复策略优化与对比 | 🚧 待开发 |
| 推演历史记录与回溯 | 🚧 待开发 |

### 节点类型

`user_entry`（用户入口）、`load_balancer`（负载均衡器）、`app_server`（应用服务器）、
`database`（数据库）、`cache`（缓存）、`message_queue`（消息队列）、`external_api`（外部 API）。

### 节点状态

`healthy`（正常）、`faulty`（故障）、`degraded`（降级）。

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、Pydantic、SQLAlchemy、SQLite |
| 前端 | Vue 3、Vite、TypeScript、Element Plus、Vue Flow、Axios |
| 测试 | pytest |
| 包管理 | pip / npm |

## 项目目录结构

```
CloudMirror-Deduction/
├── backend/
│   ├── app/
│   │   ├── main.py                  # 应用入口（CORS / 路由 / 生命周期 / 异常处理）
│   │   ├── core/
│   │   │   ├── config.py            # 配置
│   │   │   └── database.py          # 引擎 / 会话 / Base / SQLite 外键
│   │   ├── api/
│   │   │   ├── health.py            # GET /api/health
│   │   │   └── topologies.py        # 拓扑 / 节点 / 依赖接口
│   │   ├── models/topology.py       # Topology / TopologyNode / TopologyEdge
│   │   ├── schemas/topology.py      # Pydantic Schema 与枚举
│   │   └── services/
│   │       ├── exceptions.py        # NotFoundError / ConflictError 等
│   │       └── topology_service.py  # 拓扑业务逻辑
│   ├── tests/
│   │   ├── conftest.py              # 独立测试数据库与夹具
│   │   ├── test_health.py
│   │   └── test_topology.py         # 22 个拓扑测试
│   ├── requirements.txt
│   ├── pytest.ini
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── main.ts
│   │   ├── App.vue
│   │   ├── api/
│   │   │   ├── http.ts              # Axios 实例
│   │   │   ├── errors.ts            # 错误信息提取
│   │   │   ├── health.ts
│   │   │   └── topology.ts          # 拓扑接口封装与类型
│   │   ├── components/TopologyNode.vue   # Vue Flow 自定义节点
│   │   ├── constants/topology.ts         # 节点类型 / 状态元数据
│   │   ├── router/index.ts
│   │   ├── styles/main.css
│   │   └── views/
│   │       ├── Dashboard.vue
│   │       ├── Topology.vue          # 拓扑列表（增删 + 进入编辑）
│   │       ├── TopologyEditor.vue    # Vue Flow 拓扑编辑器
│   │       ├── FaultSimulation.vue   # 占位
│   │       └── History.vue           # 占位
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── .env.example
├── docs/项目说明.md
├── data/、screenshots/
├── .gitignore
└── README.md
```

## 快速启动

需要同时启动后端（8000）与前端（5173）。

### 1. 后端

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- 健康检查：<http://127.0.0.1:8000/api/health>
- 接口文档：<http://127.0.0.1:8000/docs>

### 2. 前端

```bash
cd frontend
npm install
npm run dev
```

- 访问地址：<http://127.0.0.1:5173>

### 3. 测试与构建

```bash
cd backend && pytest          # 后端测试
cd frontend && npm run build  # 前端类型检查 + 生产构建
```

## API 清单

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 健康检查 |
| POST | `/api/topologies` | 创建拓扑 |
| GET | `/api/topologies` | 查询拓扑列表 |
| GET | `/api/topologies/{id}` | 获取拓扑详情（含节点与依赖） |
| PUT | `/api/topologies/{id}` | 更新拓扑基本信息 |
| DELETE | `/api/topologies/{id}` | 删除拓扑（级联节点与依赖） |
| POST | `/api/topologies/{id}/nodes` | 添加节点 |
| PUT | `/api/topologies/{id}/nodes/{node_id}` | 编辑节点 |
| DELETE | `/api/topologies/{id}/nodes/{node_id}` | 删除节点（级联相关依赖） |
| POST | `/api/topologies/{id}/edges` | 添加依赖关系（source → target） |
| DELETE | `/api/topologies/{id}/edges/{edge_id}` | 删除依赖关系 |

错误约定：资源不存在 → `404`；名称重复 / 重复边 → `409`；自依赖 → `400`；
请求体校验失败 → `422`。所有错误均返回带中文说明的 `{"detail": "..."}`。

## 数据库表

| 表 | 说明 |
| --- | --- |
| `topology` | 拓扑：`id`、`name`(唯一)、`description`、`created_at`、`updated_at` |
| `topology_node` | 节点：`id`、`topology_id`(FK, 级联)、`name`、`type`、`description`、`status`、`position_x`、`position_y`、`created_at`、`updated_at` |
| `topology_edge` | 依赖：`id`、`topology_id`(FK, 级联)、`source_node_id`(FK)、`target_node_id`(FK)、`description`、`created_at`；唯一约束 (topology_id, source, target)、检查约束 source ≠ target |

数据库初始化使用 `create_all`，**幂等**：重复启动不会清空或重建已有数据。

## 环境配置

复制 `.env.example` 为 `.env` 后按需修改；`.env` 已被忽略，请勿提交真实密钥。

| 位置 | 变量 | 说明 |
| --- | --- | --- |
| `backend/.env.example` | `DATABASE_URL` | 默认 `sqlite:///./cloudmirror.db` |
| `backend/.env.example` | `CORS_ORIGINS` | 允许跨域的前端地址（逗号分隔） |
| `frontend/.env.example` | `VITE_API_BASE_URL` | 默认 `http://127.0.0.1:8000` |

## 开发约定

- 不提交 `.env`、API Key、数据库文件、虚拟环境、`node_modules`、构建产物。
- 功能开发建议使用独立分支，合并至 `main`。

## 许可证

待定。
