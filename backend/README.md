# 后端服务（FastAPI）

云镜推演后端，基于 **Python 3.11+ / FastAPI / SQLAlchemy / SQLite**。

> 当前阶段：已实现健康检查、**系统拓扑管理**（拓扑 / 节点 / 依赖的完整 CRUD 与持久化）、
> **故障注入与恢复**，以及**故障传播分析算法**（多源 BFS + 反向传播 + 环路安全）。
> 恢复策略优化、推演历史记录等业务功能尚未实现。

## 依赖方向约定

> **边 `A → B` 表示「A 依赖 B」**：`source_node_id = A`（依赖方）、`target_node_id = B`（被依赖方）。
> 故障传播方向相反：B 故障时 A 可能受影响。

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
│   │   └── faults.py        # 故障注入 / 恢复 / 传播分析接口
│   ├── models/
│   │   ├── topology.py      # Topology / TopologyNode / TopologyEdge
│   │   ├── fault.py         # FaultEvent
│   │   └── analysis.py      # PropagationAnalysis + 子表
│   ├── schemas/
│   │   ├── topology.py      # Pydantic Schema 与枚举
│   │   ├── fault.py         # 故障枚举与 Schema
│   │   └── analysis.py      # 分析请求 / 结果 Schema
│   └── services/
│       ├── exceptions.py    # 业务异常（404 / 409 / 400）
│       ├── topology_service.py
│       ├── fault_service.py        # 故障注入 / 恢复
│       └── propagation_service.py  # 传播分析算法（多源 BFS）
├── tests/
│   ├── conftest.py          # 独立测试数据库与夹具
│   ├── test_health.py
│   ├── test_topology.py
│   ├── test_faults.py
│   └── test_propagation.py
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
当前共 **56** 个用例（健康检查 3 + 拓扑 22 + 故障 16 + 传播算法 15）。

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

## 数据库表

- `topology`：拓扑基本信息。
- `topology_node`：节点（类型 / 状态 / 坐标）。
- `topology_edge`：依赖关系，含唯一约束（防重复边）与检查约束（防自依赖）。
- `fault_event`：故障事件（类型 / 严重程度 / 状态 / 恢复时间）。
- `propagation_analysis`：分析汇总指标。
- `analysis_fault_source` / `analysis_affected_node` / `analysis_path_step`：
  分析结果的规范化子表（故障源快照、受影响节点、传播路径步骤），不使用无约束 JSON 大字段。

初始化使用 `create_all`，幂等，不会清空已有数据。
