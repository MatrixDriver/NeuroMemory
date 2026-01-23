# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

NeuroMemory 是一个神经符号混合记忆系统（Neuro-Symbolic Hybrid Memory），实现 **Memory-as-a-Service** 架构，为主流程 LLM 提供私有上下文检索服务。

**核心设计**：Y 型分流架构
- **同步路径**：立即检索相关记忆，返回结构化 JSON
- **异步路径**：后台执行隐私分类 + 记忆写入（Fire-and-forget）

**双层记忆系统**：
- **关联记忆 (Graph Layer)**: Neo4j 知识图谱，存储实体关系，支持多跳推理
- **语义记忆 (Vector Layer)**: Qdrant 向量数据库，负责语义检索

## 技术栈

| 组件 | 技术 | 说明 |
|------|------|------|
| LLM | DeepSeek / Gemini | 可切换，用于隐私分类和实体提取 |
| Embedding | SiliconFlow / Local / Gemini | 可切换，384/768/1024 维向量 |
| Vector DB | Qdrant | localhost:6400 |
| Graph DB | Neo4j 5.26.0 | localhost:7474 (Web), localhost:17687 (Bolt) |
| Framework | Mem0 + FastAPI | 混合记忆管理 + REST API |

## 常用命令

```bash
# 启动数据库服务
docker-compose up -d

# 停止服务
docker-compose down

# 激活虚拟环境 (PowerShell)
.\.venv\Scripts\Activate.ps1

# 安装依赖
uv pip install -e ".[dev]"

# 运行 CLI 交互模式
python main.py

# 启动 HTTP Server（开发模式）
uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

# 运行测试
pytest                                    # 全部测试
pytest -m "not slow"                      # 跳过 LLM 调用的测试
pytest tests/test_cognitive.py::TestPrivacyFilter  # 运行特定测试类
```

### Python SDK / CLI

`uv pip install -e .` 或 `pip install -e .` 后可使用：

- **SDK**：`from neuromemory import NeuroMemory`；`m = NeuroMemory()`；`m.add(...)` / `m.search(...)` / `m.ask(...)` / `m.get_graph(...)`
- **CLI**：`neuromemory status`、`neuromemory add "..." --user <user>`、`neuromemory graph export --user <user>`、`neuromemory graph visualize` 等

**排错**：若 `neuromemory` 报 `ModuleNotFoundError: No module named 'private_brain'`，检查 `pyproject.toml` 的 `[tool.setuptools]` 是否包含 `py-modules = ["config","private_brain","session_manager","coreference","consolidator","privacy_filter","health_checks"]`，并重新执行 `uv pip install -e .`。

### 验证命令与 Shell

若文档或计划中的验证命令使用 `&&` 串联（Bash 语法），在 **Windows PowerShell** 下应改为 `;`，或注明「Bash」并另给 PowerShell 示例。例如：`cd d:\CODE\NeuroMemory; python -m py_compile neuromemory/__init__.py neuromemory/cli.py`。

## 服务访问

**本地：**
- Neo4j Browser: http://localhost:7474 (用户名: `neo4j`, 密码: `password123`)
- Qdrant API: http://localhost:6400
- REST API: http://localhost:8765 (需手动启动)
- API 文档: http://localhost:8765/docs (Swagger UI)

**ZeaBur 远程：**  
- REST API: https://neuromemory.zeabur.app/ ；API 文档: https://neuromemory.zeabur.app/docs  
- Neo4j Browser: https://neo4j-neuromemory.zeabur.app/  
- Qdrant Web UI: https://qdrant-neuromemory.zeabur.app  
（Neo4j 密码见 ZeaBur 变量 `Neo4jPassword` 或本地 `CREDENTIALS.local.md`；Bolt 端口 7687）

## 核心模块

| 文件 | 职责 |
|------|------|
| `private_brain.py` | 核心类 `PrivateBrain`，实现 Y 型分流架构 |
| `neuromemory/` | Python SDK（`NeuroMemory`）与 CLI（`neuromemory` 命令），封装 `get_brain()` |
| `privacy_filter.py` | LLM 隐私分类器（PRIVATE/PUBLIC） |
| `http_server.py` | FastAPI REST API 入口 |
| `mcp_server.py` | MCP Server 入口（Cursor/Claude Desktop 集成） |
| `config.py` | 模型切换、数据库连接配置 |
| `main.py` | CLI 交互模式入口 |

## 模型切换配置

在 `config.py` 中修改：

```python
LLM_PROVIDER = "deepseek"       # "gemini" 或 "deepseek"
EMBEDDING_PROVIDER = "siliconflow"  # "gemini", "local", "siliconflow"
ENABLE_GRAPH_STORE = True       # 是否启用 Neo4j 图谱
```

## 环境变量

在 `.env` 文件中配置：
```
DEEPSEEK_API_KEY=your-deepseek-api-key
GOOGLE_API_KEY=your-gemini-api-key
SILICONFLOW_API_KEY=your-siliconflow-api-key
```

## REST API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/process` | POST | 处理记忆（生产模式，返回 JSON） |
| `/debug` | POST | 处理记忆（调试模式，返回自然语言报告） |
| `/graph/{user_id}` | GET | 获取用户知识图谱 |
| `/health` | GET | 健康检查 |

## 测试

测试文件位于 `tests/test_cognitive.py`，包含：
- `TestIdentityExtraction` / `TestPronounResolution`：单元测试（无 LLM）
- `TestPrivacyFilter`：隐私分类集成测试
- `TestPrivateBrain`：核心功能测试
- `TestMultiHopRetrieval`：多跳检索端到端测试

使用 `@pytest.mark.slow` 标记需要 LLM 调用的测试。

## 架构说明

详细架构设计参见 `docs/ARCHITECTURE.md` 和 `docs/ARCHITECTURE_V2.md`。

## 工程推进流程

`core_piv_loop`（prime / plan-feature / execute）、`validation`（code-review、execution-report、system-review 等）、`create-prd` 的用法、顺序及与本仓库的衔接，参见 `docs/ENGINEERING_WORKFLOW.md`。

## 开发约定与反模式

**后台周期性任务**：若模块提供“后台任务”或“定期检查”（如 Session 超时检查），必须在**某一明确启动点**被调用：
- HTTP：在 `http_server` 的 `lifespan` 上下文管理器（startup 阶段）中调用 `get_session_manager().start_timeout_checker()`
- MCP：在 `main()` 进入 `stdio_server` 的 async 上下文后、`server.run` 之前调用
- 无 running event loop 时（如 CLI 单次 `asyncio.run`），`start_timeout_checker` 会静默跳过

**API 格式升级**：修改响应格式（如 v2→v3）时，**成功与错误两种响应**、以及端点的 **docstring / OpenAPI** 需一并更新，避免错误分支或文档沿用旧字段名。

**反模式**：不要在 `return` 之后写逻辑，会变成不可达代码；建议在 CI 中启用 unreachable / dead-code 检查（如 pyright）。
