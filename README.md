# 云镜推演 (CloudMirror Deduction)

> 面向云原生业务系统的**故障传播分析**与**恢复策略优化**平台。

## 项目状态

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 第一阶段 | 工程初始化、健康检查、前后端基础联调 | ✅ 已完成 |
| 第二阶段 | 系统拓扑管理与数据建模（拓扑 / 节点 / 依赖 CRUD + Vue Flow 编辑器） | ✅ 已完成 |
| 第三阶段 | 故障注入、故障传播分析算法与传播可视化 | ✅ 已完成 |
| 第四阶段 | 恢复策略优化、策略对比与推演历史记录管理 | ✅ 已完成 |

已实现的功能均可通过真实后端 API 操作并持久化到 SQLite；前端各页面数据均来自真实接口，
不含演示假数据。恢复策略的恢复时间、成本、影响节点数与评分均为**规则模拟估算值**，
不是生产环境测量值；完整的冗余关系建模、真实执行恢复动作等仍未实现（详见
[`docs/技术方案.md`](docs/技术方案.md) 的「尚未实现」章节）。

## 依赖方向约定（重要）

> **边 `A → B` 表示「A 依赖 B」。**
> 即 `source_node_id = A`（依赖方）、`target_node_id = B`（被依赖方）。

- Vue Flow 画布中，箭头由 A 指向 B（指向被依赖方），与后端字段完全一致。
- 故障传播方向与依赖方向**相反**：依赖边 `A → B` 对应传播路径 `B → A`，
  即 **B 故障时 A 可能受影响**。
- 该约定在 `backend/app/models/topology.py`、`backend/app/api/topologies.py`、
  `backend/app/services/propagation_service.py` 与
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
| 故障注入 / 查询 / 恢复（`fault_event` 持久化） | ✅ 已实现 |
| 故障传播分析算法（多源 BFS、反向传播、环路安全、路径与影响等级） | ✅ 已实现 |
| 故障模拟页面（真实 API 注入 / 恢复 / 分析 + Vue Flow 传播高亮） | ✅ 已实现 |
| 恢复策略模型与规则推荐（重启 / 切换 / 隔离，含适用性与不适用原因） | ✅ 已实现 |
| 恢复策略对比页面（指标对比、评分明细、推荐理由） | ✅ 已实现 |
| 推演历史分页查询与单条详情回看（含故障源快照） | ✅ 已实现 |
| 历史记录页面（真实分页接口 + 详情弹窗） | ✅ 已实现 |
| 显式冗余 / 备用节点关系建模 | 🚧 待开发（当前用「同类型未受影响节点」保守推断） |
| 真实执行恢复动作、对接真实云平台 | 🚧 待开发（当前仅输出策略与模拟估算） |

### 节点类型

`user_entry`（用户入口）、`load_balancer`（负载均衡器）、`app_server`（应用服务器）、
`database`（数据库）、`cache`（缓存）、`message_queue`（消息队列）、`external_api`（外部 API）。

### 节点状态

`healthy`（正常）、`faulty`（故障）、`degraded`（降级）。

### 故障模型

- 故障类型：`node_down`（节点宕机）、`service_unavailable`（服务不可用）、
  `network_latency`（网络延迟）、`network_unreachable`（网络不可达）。
- 严重程度：`low` / `medium` / `high` / `critical`。
- 故障状态：`active`（激活）/ `recovered`（已恢复）。
- 恢复故障只更新状态与恢复时间，不删除历史记录。

> 注意区分三类状态：**节点原始状态**（`topology_node.status`）、
> **激活故障事件**（`fault_event`）、**算法计算出的影响状态**（仅存在于分析结果中）。

## 传播分析算法

- 实现于 `backend/app/services/propagation_service.py`（独立 Service）。
- 传播方向与依赖方向相反：构建反向邻接表 `dependents[B] = [A, ...]`（A 依赖 B），
  从故障源沿 `dependents` 扩散。
- **多源 BFS**：所有激活故障源作为距离 0 的根同时入队；首次发现的层级即最短距离。
- **环路安全**：以已发现集合做访问控制，环路不会死循环、不重复统计。
- **去重**：受影响节点按 `node_id` 去重；多源触达时保留最短距离，距离相同按故障 ID 取先者。
- 距离 1 为 `direct`，距离 ≥ 2 为 `indirect`；故障源本身不计入受影响节点。
- 结果完全由「拓扑 + 故障记录」决定，**不含随机数、不调用大模型**，可复现。

## 恢复策略优化

实现于 `backend/app/services/recovery_service.py`（独立 Service），参数集中在
`backend/app/services/recovery_config.py`。输入为「当前拓扑 + 一次传播分析结果」。

| 策略类型 | 适用条件 | 估算恢复时间 | 资源成本 | 基础风险 |
| --- | --- | --- | --- | --- |
| `restart_service`（服务重启） | 存在 `node_down` / `service_unavailable` 类故障 | `120 + 60 × 可重启节点数` 秒 | 低 | 中 |
| `failover`（备用节点切换） | 每个故障节点都有可用同类型备用节点 | `60 + 30 × 故障节点数` 秒 | 高 | 低 |
| `isolate_node`（故障节点隔离） | 隔离后用户入口仍保留可用依赖 | `30 + 15 × 故障节点数` 秒 | 低 | 低 / 中 |

- **备用节点不做虚构**：当前没有显式冗余关系模型，`failover` 仅在拓扑中存在
  「同类型且不在故障源 / 影响范围内」的节点时判定为适用，否则返回 `applicable=false`
  并给出具体缺失原因。
- **隔离不保证业务恢复**：若隔离会让某个 `user_entry` 节点失去全部直接依赖，
  该策略直接判定为**不适用**且风险为 `high`，永远不会被推荐。
- **评分模型**（可解释的加权规则，权重写入代码与文档）：
  恢复时间 0.25、影响范围 0.20、资源成本 0.15、操作风险 0.20、业务恢复程度 0.20（合计 1.00）。
  各分项归一化后加权求和 ×100 得到 0-100 的评分，参考恢复时间为 600 秒。
- **推荐规则**：在**适用**策略中取评分最高者；同分按固定顺序
  `restart_service → failover → isolate_node` 打破平局。不适用策略仍展示评分，但绝不推荐。
- 不含随机数、不使用机器学习或大模型；相同输入必然得到相同输出，可复现。

## 推演历史

- 每次传播分析都会落库（`propagation_analysis` 及其子表），保存故障源与受影响节点的
  **名称快照**，因此故障恢复或节点删除后仍可完整回看。
- `GET /api/topologies/{id}/analyses` 支持分页（`page`、`page_size`），按时间倒序并返回总数。
- `GET /api/topologies/{id}/analyses/{analysis_id}` 返回当时的完整分析结果，并校验其属于该拓扑。

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
│   │   │   ├── topologies.py        # 拓扑 / 节点 / 依赖接口
│   │   │   ├── faults.py            # 故障注入 / 查询 / 恢复 / 传播分析接口
│   │   │   ├── analyses.py          # 推演历史列表 / 详情接口
│   │   │   └── recovery.py          # 恢复策略推荐 / 策略配置接口
│   │   ├── models/
│   │   │   ├── topology.py          # Topology / TopologyNode / TopologyEdge
│   │   │   ├── fault.py             # FaultEvent
│   │   │   ├── analysis.py          # PropagationAnalysis + 故障源 / 受影响节点 / 路径子表
│   │   │   └── recovery.py          # RecoveryPlan / RecoveryStrategy / RecoveryStrategyNote
│   │   ├── schemas/
│   │   │   ├── topology.py          # Pydantic Schema 与枚举
│   │   │   ├── fault.py             # 故障类型 / 严重程度 / 状态枚举
│   │   │   ├── analysis.py          # 分析请求 / 结果 / 历史分页 Schema
│   │   │   └── recovery.py          # 恢复策略请求 / 响应 Schema
│   │   └── services/
│   │       ├── exceptions.py        # NotFoundError / ConflictError 等
│   │       ├── topology_service.py  # 拓扑业务逻辑
│   │       ├── fault_service.py     # 故障注入 / 恢复业务逻辑
│   │       ├── propagation_service.py  # 故障传播分析算法（多源 BFS）+ 历史查询
│   │       ├── recovery_config.py   # 策略参数 / 评分权重 / 文案
│   │       └── recovery_service.py  # 恢复策略评估与推荐
│   ├── tests/
│   │   ├── conftest.py              # 独立测试数据库与夹具
│   │   ├── test_health.py
│   │   ├── test_topology.py         # 22 个拓扑测试
│   │   ├── test_faults.py           # 16 个故障测试
│   │   ├── test_propagation.py      # 15 个传播算法测试
│   │   ├── test_recovery.py         # 16 个恢复策略测试
│   │   └── test_analysis_history.py # 10 个历史记录测试（共 82 个）
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
│   │   │   ├── topology.ts          # 拓扑接口封装与类型
│   │   │   ├── fault.ts             # 故障注入 / 恢复接口
│   │   │   ├── analysis.ts          # 传播分析 / 历史列表 / 历史详情接口
│   │   │   └── recovery.ts          # 恢复策略推荐 / 策略配置接口
│   │   ├── components/TopologyNode.vue   # Vue Flow 自定义节点（支持传播高亮）
│   │   ├── constants/
│   │   │   ├── topology.ts          # 节点类型 / 状态元数据
│   │   │   ├── fault.ts             # 故障类型 / 严重程度 / 影响等级配色
│   │   │   └── recovery.ts          # 策略类型 / 成本 / 风险标签与配色
│   │   ├── router/index.ts
│   │   ├── styles/main.css
│   │   └── views/
│   │       ├── Dashboard.vue
│   │       ├── Topology.vue          # 拓扑列表（增删 + 进入编辑）
│   │       ├── TopologyEditor.vue    # Vue Flow 拓扑编辑器
│   │       ├── FaultSimulation.vue   # 故障模拟 + 传播可视化
│   │       ├── Recovery.vue          # 恢复策略对比与推荐
│   │       └── History.vue           # 推演历史分页列表 + 详情弹窗
│   ├── vite.config.ts
│   ├── tsconfig.json
│   └── .env.example
├── docs/项目说明.md
├── docs/技术方案.md
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
cd backend && pytest          # 后端测试（82 个）
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
| POST | `/api/topologies/{id}/faults` | 注入故障 |
| GET | `/api/topologies/{id}/faults` | 查询故障事件（含已恢复） |
| POST | `/api/topologies/{id}/analyze` | 执行故障传播分析（body 可选 `fault_ids`） |
| GET | `/api/topologies/{id}/analysis/latest` | 读取最近一次分析结果 |
| GET | `/api/topologies/{id}/analyses` | 分页查询历史分析（`page`、`page_size`，时间倒序） |
| GET | `/api/topologies/{id}/analyses/{analysis_id}` | 读取单次历史分析详情 |
| POST | `/api/topologies/{id}/recovery/recommend` | 生成恢复策略并推荐（body 可选 `analysis_id`） |
| GET | `/api/topologies/{id}/recovery/strategies` | 查询策略类型、估算参数与评分权重 |
| GET | `/api/faults/{fault_id}` | 查询故障详情 |
| POST | `/api/faults/{fault_id}/recover` | 恢复故障 |

错误约定：资源不存在 / 分析不属于该拓扑 → `404`；名称重复 / 重复边 / 重复的同类激活故障 → `409`；
自依赖、指定已恢复故障参与分析、分析无激活故障源时请求恢复策略 → `400`；请求体校验失败 → `422`。
所有错误均返回带中文说明的 `{"detail": "..."}`。

> 传播算法的完整说明（方向、环路、多源、去重）见 [`docs/项目说明.md`](docs/项目说明.md)；
> 恢复策略的规则、权重与取舍见 [`docs/技术方案.md`](docs/技术方案.md)。

## 数据库表

| 表 | 说明 |
| --- | --- |
| `topology` | 拓扑：`id`、`name`(唯一)、`description`、`created_at`、`updated_at` |
| `topology_node` | 节点：`id`、`topology_id`(FK, 级联)、`name`、`type`、`description`、`status`、`position_x`、`position_y`、`created_at`、`updated_at` |
| `topology_edge` | 依赖：`id`、`topology_id`(FK, 级联)、`source_node_id`(FK)、`target_node_id`(FK)、`description`、`created_at`；唯一约束 (topology_id, source, target)、检查约束 source ≠ target |
| `fault_event` | 故障事件：`id`、`topology_id`(FK, 级联)、`source_node_id`(FK, 级联)、`fault_type`、`severity`、`description`、`status`、`created_at`、`recovered_at` |
| `propagation_analysis` | 分析汇总：`topology_id`(FK)、故障源 / 直接 / 间接 / 总计受影响数、节点总数、影响比例、分析时间 |
| `analysis_fault_source` | 故障源快照：`analysis_id`(FK, 级联)、`fault_id`、`node_id`、`node_name`、`fault_type`、`severity` |
| `analysis_affected_node` | 受影响节点：`analysis_id`(FK, 级联)、`node_id`、`node_name`、`impact_level`、`distance`、`source_fault_id`、`source_node_id` |
| `analysis_path_step` | 传播路径步骤：`affected_node_id`(FK, 级联)、`step_index`、`node_id`、`node_name` |
| `recovery_plan` | 一次策略推荐：`topology_id`(FK)、`analysis_id`(FK, 置空保留)、`recommended_strategy_id`(软引用)、`recommendation_reason`、`estimation_notice`、`created_at` |
| `recovery_strategy` | 策略评估：`plan_id`(FK, 级联)、`strategy_type`、`applicable`、`inapplicable_reason`、估算指标、`risk_level`、`recommendation_score` |
| `recovery_strategy_note` | 策略条目：`strategy_id`(FK, 级联)、`kind`(advantage/disadvantage/prerequisite)、`position`、`content` |

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
