# 云镜推演 (CloudMirror Deduction)

> 项目状态：**项目骨架初始化阶段**。当前仓库仅包含目录结构与基础说明文档，业务功能尚未实现。

## 项目简介

**云镜推演 / CloudMirror Deduction** 是一个规划中的前后端分离 Web 应用项目。

项目采用 **FastAPI** 作为后端服务框架、**Vue 3 + Vite** 作为前端框架，目标是在云端构建一套可交互的推演与展示系统。

> 说明：本 README 仅描述项目定位、技术选型与目录约定。具体业务功能、接口与数据模型将随开发推进逐步补充，请勿将「规划中」的内容视为已实现能力。

## 核心功能（规划中）

以下为项目方向，具体实现以后续迭代为准：

- 前端可视化交互界面（Vue 3 SPA）
- 后端 RESTful API 服务（FastAPI）
- 数据存储与推演结果管理
- 前后端联调与部署流程

## 技术栈（规划）

| 层次 | 技术 | 说明 |
| --- | --- | --- |
| 后端 | Python 3.11+ / FastAPI | 提供 RESTful API |
| 后端 | Uvicorn | ASGI 服务器 |
| 前端 | Vue 3 | 组合式 API |
| 前端 | Vite | 构建与开发服务器 |
| 前端 | Node.js 18+ / npm | 前端工具链 |
| 数据 | 待定 | 数据库/存储选型待定 |

## 项目目录结构

```
CloudMirror-Deduction/
├── backend/        # 后端服务（FastAPI）
├── frontend/       # 前端应用（Vue 3 + Vite）
├── docs/           # 项目文档
├── data/           # 数据文件与本地数据集（不入库大文件）
├── screenshots/    # 界面截图与演示图片
├── .gitignore      # Git 忽略规则
└── README.md       # 项目说明
```

## 启动方式

> 后端与前端工程尚未初始化，以下为规划中的启动流程，仅供参考。

### 后端（规划）

```bash
cd backend
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### 前端（规划）

```bash
cd frontend
npm install
npm run dev
```

## 环境与安全约定

- 敏感配置统一通过 `.env` 管理，**严禁提交**到仓库。
- 不提交虚拟环境、`node_modules`、构建产物与密钥文件。
- 详细说明见 [docs/项目说明.md](docs/项目说明.md)。

## 许可证

待定。
