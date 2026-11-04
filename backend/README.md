# 后端服务（FastAPI）

云镜推演后端，基于 **Python 3.11+ / FastAPI / SQLAlchemy / SQLite**。

> 当前阶段：已实现健康检查与**系统拓扑管理**（拓扑 / 节点 / 依赖的完整 CRUD 与持久化）。
> 故障传播分析、恢复策略优化等业务功能尚未实现。

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
│   │   └── topologies.py    # 拓扑 / 节点 / 依赖接口
│   ├── models/topology.py   # Topology / TopologyNode / TopologyEdge
│   ├── schemas/topology.py  # Pydantic Schema 与枚举
│   └── services/
│       ├── exceptions.py    # 业务异常（404 / 409 / 400）
│       └── topology_service.py
├── tests/
│   ├── conftest.py          # 独立测试数据库与夹具
│   ├── test_health.py
│   └── test_topology.py
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
| GET | `/` | 项目信息与文档入口（不在接口文档中展示） |

## 数据库表

- `topology`：拓扑基本信息。
- `topology_node`：节点（类型 / 状态 / 坐标）。
- `topology_edge`：依赖关系，含唯一约束（防重复边）与检查约束（防自依赖）。

初始化使用 `create_all`，幂等，不会清空已有数据。
