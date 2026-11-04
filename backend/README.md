# 后端服务（FastAPI）

云镜推演后端，基于 **Python 3.11+ / FastAPI / SQLAlchemy / SQLite**。

> 当前阶段：已实现健康检查、**系统拓扑管理**（拓扑 / 节点 / 依赖的完整 CRUD 与持久化）、
> **故障注入与恢复**、**故障传播分析算法**（多源 BFS + 反向传播 + 环路安全）、
> **恢复策略评估与推荐**（重启 / 切换 / 隔离，含适用性与规则评分）、
> **推演历史分页查询与详情回看**，以及**显式冗余关系建模**（冗余组 / 成员，
> 使 `failover` 基于真实备用节点判定）。
> 恢复时间与成本均为**规则模拟估算值**，不是生产测量数据；备用节点「可用」仅为模拟判定，
> 不执行真实切流，也不校验真实容量 / 网络 / 数据同步；真实执行恢复动作尚未实现。

## 依赖方向约定

> **边 `A → B` 表示「A 依赖 B」**：`source_node_id = A`（依赖方）、`target_node_id = B`（被依赖方）。
> 故障传播方向相反：B 故障时 A 可能受影响。

> **冗余关系是独立概念**：`redundancy_group` / `redundancy_member` 描述「谁能顶替谁」，
> 与依赖边无关，不参与传播计算，仅用于恢复策略 `failover` 的备用节点判定。

## 目录结构

```
backend/
├── app/
│   ├── main.py              # 应用入口（CORS / 路由 / 生命周期 / 业务异常处理）
│   ├── core/
│   │   ├── config.py        # 配置（pydantic-settings）
│   │   └── database.py      # 引擎 / 会话 / Base / SQLite 外键 / init_db
│   ├── api/
│   │   ├── router.py        # 路由汇总
│   │   ├── health.py        # GET /api/health
│   │   ├── topologies.py    # 拓扑 / 节点 / 依赖接口
│   │   ├── faults.py        # 故障注入 / 恢复 / 传播分析接口
│   │   ├── analyses.py      # 推演历史列表 / 详情接口
│   │   ├── recovery.py      # 恢复策略推荐 / 策略配置接口
│   │   └── redundancy.py    # 冗余组创建 / 列表 / 详情 / 更新 / 删除
│   ├── models/
│   │   ├── topology.py      # Topology / TopologyNode / TopologyEdge
│   │   ├── fault.py         # FaultEvent
│   │   ├── analysis.py      # PropagationAnalysis + 子表
│   │   ├── recovery.py      # RecoveryPlan / RecoveryStrategy / 子表（备注 / 备用候选 / 前置检查）
│   │   └── redundancy.py    # RedundancyGroup / RedundancyMember
│   ├── schemas/
│   │   ├── topology.py      # Pydantic Schema 与枚举
│   │   ├── fault.py         # 故障枚举与 Schema
│   │   ├── analysis.py      # 分析请求 / 结果 / 历史分页 Schema
│   │   ├── recovery.py      # 恢复策略请求 / 响应 Schema
│   │   └── redundancy.py    # 冗余模式 / 成员角色 / 冗余组 Schema
│   └── services/
│       ├── exceptions.py    # 业务异常（404 / 409 / 400）
│       ├── topology_service.py
│       ├── fault_service.py        # 故障注入 / 恢复
│       ├── propagation_service.py  # 传播分析算法（多源 BFS）+ 历史查询
│       ├── recovery_config.py      # 策略参数 / 评分权重
│       ├── recovery_service.py     # 恢复策略评估与推荐（failover 基于显式冗余）
│       └── redundancy_service.py   # 冗余组校验与 CRUD / 备用节点查询
├── tests/
│   ├── conftest.py          # 独立测试数据库与夹具
│   ├── test_health.py
│   ├── test_topology.py
│   ├── test_faults.py
│   ├── test_propagation.py
│   ├── test_recovery.py
│   ├── test_analysis_history.py
│   ├── test_redundancy.py           # 冗余关系 CRUD / 约束
│   └── test_failover_redundancy.py  # 基于显式冗余的 failover
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

## 本地启动

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

## 运行测试

```bash
cd backend
pip install -r requirements.txt
pytest
```

测试使用独立的数据库文件（`_test_cloudmirror.db`，测试结束后自动删除），不会影响开发数据。
当前共 **113** 个用例：健康检查 3 + 拓扑 22 + 故障 16 + 传播算法 15 + 恢复策略 16 +
历史记录 10 + 冗余关系 18 + failover 显式冗余 13。

## 配置

复制 `.env.example` 为 `.env` 后按需修改。`.env` 已被 `.gitignore` 忽略，请勿提交真实密钥。

| 变量 | 说明 | 默认值 |
| --- | --- | --- |
| `DEBUG` | 调试模式 | `true` |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///./cloudmirror.db` |
| `API_PREFIX` | 接口前缀 | `/api` |
| `CORS_ORIGINS` | 允许跨域来源（逗号分隔） | 本地 5173 / 3000 |

## 已实现接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/health` | 服务状态、项目名称与版本 |
| POST | `/api/topologies` | 创建拓扑 |
| GET | `/api/topologies` | 拓扑列表（含节点数 / 依赖数） |
| GET | `/api/topologies/{id}` | 拓扑详情（含 nodes、edges） |
| PUT | `/api/topologies/{id}` | 更新拓扑基本信息 |
| DELETE | `/api/topologies/{id}` | 删除拓扑（级联节点与依赖） |
| POST | `/api/topologies/{id}/nodes` | 添加节点 |
| PUT | `/api/topologies/{id}/nodes/{node_id}` | 编辑节点 |
| DELETE | `/api/topologies/{id}/nodes/{node_id}` | 删除节点（级联相关依赖） |
| POST | `/api/topologies/{id}/edges` | 添加依赖关系 |
| DELETE | `/api/topologies/{id}/edges/{edge_id}` | 删除依赖关系 |
| POST | `/api/topologies/{id}/faults` | 注入故障 |
| GET | `/api/topologies/{id}/faults` | 查询故障事件（含已恢复） |
| POST | `/api/topologies/{id}/analyze` | 执行故障传播分析（body 可选 `fault_ids`） |
| GET | `/api/topologies/{id}/analysis/latest` | 读取最近一次分析结果 |
| GET | `/api/topologies/{id}/analyses` | 分页查询历史分析（`page`、`page_size`） |
| GET | `/api/topologies/{id}/analyses/{analysis_id}` | 读取单次历史分析详情 |
| POST | `/api/topologies/{id}/recovery/recommend` | 生成恢复策略并推荐（body 可选 `analysis_id`） |
| GET | `/api/topologies/{id}/recovery/strategies` | 策略类型、估算参数与评分权重 |
| POST | `/api/topologies/{id}/redundancy-groups` | 创建冗余组（一次提交完整主备结构） |
| GET | `/api/topologies/{id}/redundancy-groups` | 查询拓扑的冗余组列表 |
| GET | `/api/redundancy-groups/{group_id}` | 查询冗余组详情 |
| PUT | `/api/redundancy-groups/{group_id}` | 更新冗余组 |
| DELETE | `/api/redundancy-groups/{group_id}` | 删除冗余组 |
| GET | `/api/faults/{fault_id}` | 查询故障详情 |
| POST | `/api/faults/{fault_id}/recover` | 恢复故障 |
| GET | `/` | 项目信息与文档入口（不在接口文档中展示） |

## 故障传播算法

- 实现于 `app/services/propagation_service.py`（独立 Service）。
- 依赖方向 `A → B` 表示 A 依赖 B；传播方向相反，构建反向邻接表
  `dependents[B] = [A, ...]`，从故障源沿 `dependents` 扩散。
- 多源 BFS：所有激活故障源作为距离 0 的根同时入队；首次发现层级即最短距离。
- 环路安全（已发现集合访问控制）、受影响节点按 `node_id` 去重。
- 距离 1 为 `direct`，距离 ≥ 2 为 `indirect`；结果无随机成分，可复现。

## 恢复策略（规则模拟）

- 实现于 `app/services/recovery_service.py`，参数与权重在 `app/services/recovery_config.py`。
- 输入为「拓扑 + 一次传播分析结果」，输出三类策略的适用性、估算指标与推荐。
- 备用节点不虚构：`failover` **只**认可显式冗余关系（见下节），
  不再按「同类型节点」推断；不满足前置条件时返回 `applicable=false` 并说明原因。
- 隔离若会让用户入口失去全部依赖，则判定为不适用且风险 `high`，不被推荐。
- 评分为可解释的加权规则（恢复时间 0.25 / 影响范围 0.20 / 成本 0.15 / 风险 0.20 /
  业务恢复程度 0.20），不含随机数，结果可复现。详见 `docs/技术方案.md`。

## 显式冗余关系与 failover

- 模型：`redundancy_group`（冗余组）/ `redundancy_member`（成员），
  模式 `active_standby` / `active_active` / `manual_standby`，
  角色 `primary` / `standby` / `active`。实现于 `app/services/redundancy_service.py`。
- 约束：成员必须属于本拓扑；同一节点不在同组重复；主备 / 手动备用必须 1 主 ≥1 备，
  备用必须指定 `priority`；双活至少两个 `active`；**当前一个节点最多属于一个冗余组**。
- 删除节点时清理其成员行，若组因此不满足模式约束（如丢失主节点）则整组删除。
- `failover` **只**使用显式冗余：故障源需属于冗余组且为主节点，备用节点需无激活故障、
  未被传播影响、类型相容、无故障依赖且已明确优先级；多个可用备用节点按 `priority` 升序
  （数值越小越优先）选择，优先级相同按 `node_id` 升序，**不使用随机数**。
- 结果额外返回 `redundancy_group_id`、`redundancy_group_name`、`primary_node_id`、
  `selected_standby_node_id`、`standby_candidates`、`selection_reason` 与 `prerequisite_checks`。
- **提醒**：备用节点「可用」仅为模拟模型判定，不执行真实切流，
  也不校验真实容量 / 网络 / 数据同步 / 配置一致性。详见 `docs/技术方案.md`。

## 数据库表

- `topology`：拓扑基本信息。
- `topology_node`：节点（类型 / 状态 / 坐标）。
- `topology_edge`：依赖关系，含唯一约束（防重复边）与检查约束（防自依赖）。
- `fault_event`：故障事件（类型 / 严重程度 / 状态 / 恢复时间）。
- `propagation_analysis`：分析汇总指标。
- `analysis_fault_source` / `analysis_affected_node` / `analysis_path_step`：
  分析结果的规范化子表（故障源快照、受影响节点、传播路径步骤），不使用无约束 JSON 大字段。
- `recovery_plan`：一次策略推荐（关联分析与拓扑，记录推荐策略与理由）。
- `recovery_strategy`：每种策略的评估结果（适用性、估算指标、风险、评分、failover 冗余字段）。
- `recovery_strategy_note`：策略的优势 / 劣势 / 前置条件条目（有序子表）。
- `recovery_standby_candidate` / `recovery_prerequisite_check`：failover 的备用候选与前置检查（有序子表）。
- `redundancy_group` / `redundancy_member`：显式冗余关系（与依赖边语义不同）。

初始化使用 `create_all`，幂等，不会清空已有数据。
