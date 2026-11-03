# 云镜推演 (CloudMirror Deduction)

> 面向云原生业务系统的**故障传播分析**与**恢复策略优化**平台。

## 项目状态

**第一阶段：工程初始化（已完成）**

当前仓库已包含可运行的 FastAPI 后端与 Vue 3 前端，并完成健康检查接口的前后端联调。

- 已实现：后端健康检查接口、CORS、SQLite/SQLAlchemy 基础初始化、后端测试；
  前端路由、Element Plus、Vue Flow、Axios 封装、首页后端连接状态检测。
- **尚未实现**：故障传播分析、恢复策略优化、系统拓扑数据、故障模拟、历史记录等业务功能。
  各业务页面目前仅为布局占位。

## 核心功能

| 功能 | 状态 |
| --- | --- |
| 前后端健康检查联调（`GET /api/health`） | ✅ 已实现 |
| 首页后端连接状态检测 | ✅ 已实现 |
| 前端页面路由与整体布局（首页 / 拓扑 / 故障模拟 / 历史记录） | ✅ 基础框架 |
| 系统拓扑可视化（Vue Flow 画布） | 🚧 占位示意，未接入数据 |
| 故障注入与传播推演 | 🚧 规划中 |
| 恢复策略优化与对比 | 🚧 规划中 |
| 推演历史记录与回溯 | 🚧 规划中 |

## 技术栈

| 层次 | 技术 |
| --- | --- |
| 后端 | Python 3.11+、FastAPI、Pydantic、SQLAlchemy、SQLite |
| 前端 | Vue 3、Vite、TypeScript、Element Plus、Vue Flow、Axios |
| 测试 | pytest（后端） |
| 包管理 | pip / npm |

## 项目目录结构

```
CloudMirror-Deduction/
├── backend/                     # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # 应用入口（CORS / 路由 / 生命周期）
│   │   ├── core/                # 配置与数据库连接
│   │   ├── api/                 # API 路由（健康检查）
│   │   ├── models/              # ORM 模型（暂为空）
│   │   ├── schemas/             # Pydantic Schema
│   │   └── services/            # 业务服务层（暂为空）
│   ├── tests/                   # 后端测试
│   ├── requirements.txt
│   ├── pytest.ini
│   ├── .env.example
│   └── README.md
├── frontend/                    # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── main.ts              # 应用入口
│   │   ├── App.vue              # 顶部导航 + 内容区布局
│   │   ├── api/                 # Axios 封装与接口定义
│   │   ├── router/              # Vue Router 配置
│   │   ├── styles/              # 全局样式
│   │   └── views/               # 四个页面
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── package.json
│   ├── .env.example
│   └── README.md
├── docs/                        # 项目文档
├── data/                        # 数据目录（大文件不入库）
├── screenshots/                 # 截图目录
├── .gitignore
└── README.md
```

## 快速启动

需要同时启动后端（8000）与前端（5173）。

### 1. 启动后端

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

### 2. 启动前端

```bash
cd frontend
npm install
npm run dev
```

- 访问地址：<http://127.0.0.1:5173>（以终端输出为准）

前端首页加载后会自动请求后端 `/api/health`：

- 后端已启动 → 显示「已连接」及后端返回的项目信息；
- 后端未启动 → 显示「后端未连接」并给出启动提示，页面不会崩溃。

### 3. 生产构建

```bash
cd frontend
npm run build
```

### 4. 后端测试

```bash
cd backend
pytest
```

## 环境配置

两个子工程均提供 `.env.example`，复制为 `.env` 后按需修改；`.env` 已被忽略，请勿提交真实密钥。

| 位置 | 变量 | 说明 |
| --- | --- | --- |
| `backend/.env.example` | `DATABASE_URL` | 数据库连接串，默认 `sqlite:///./cloudmirror.db` |
| `backend/.env.example` | `CORS_ORIGINS` | 允许跨域的前端地址（逗号分隔） |
| `frontend/.env.example` | `VITE_API_BASE_URL` | 后端基础地址，默认 `http://127.0.0.1:8000` |

## 开发约定

- 不提交 `.env`、API Key、数据库文件、虚拟环境、`node_modules`、构建产物。
- 功能开发建议使用独立分支，合并至 `main`。

## 许可证

待定。
