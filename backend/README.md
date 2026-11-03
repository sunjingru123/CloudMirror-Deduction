# 后端服务（FastAPI）

云镜推演后端，基于 **Python 3.11+ / FastAPI / SQLAlchemy / SQLite**。

> 当前阶段：工程初始化。已实现健康检查接口、CORS 配置、SQLite 连接与基础测试；尚未实现业务表与业务接口。

## 目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI 应用入口（CORS / 路由 / 生命周期）
│   ├── core/
│   │   ├── config.py     # 配置（pydantic-settings）
│   │   └── database.py   # SQLAlchemy 引擎 / 会话 / Base
│   ├── api/
│   │   ├── router.py     # 路由汇总
│   │   └── health.py     # GET /api/health
│   ├── models/           # ORM 模型（暂为空）
│   ├── schemas/          # Pydantic Schema
│   └── services/         # 业务服务层（暂为空）
├── tests/
│   └── test_health.py    # 健康检查测试
├── requirements.txt
├── pytest.ini
├── .env.example
└── README.md
```

## 本地启动

```bash
cd backend

# 创建并激活虚拟环境
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
uvicorn app.main:app --reload
```

启动后可访问：

- 健康检查：<http://127.0.0.1:8000/api/health>
- 接口文档：<http://127.0.0.1:8000/docs>

## 运行测试

```bash
cd backend
pip install -r requirements.txt
pytest
```

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
| GET | `/api/health` | 返回服务状态、项目名称与版本 |
| GET | `/` | 项目信息与文档入口（不在接口文档中展示） |
