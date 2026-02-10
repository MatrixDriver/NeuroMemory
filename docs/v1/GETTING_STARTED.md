# 快速开始

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | >= 3.10 | 推荐 3.11+ |
| Docker | >= 20.0 | 用于运行数据库服务 |
| Docker Compose | >= 2.0 | 容器编排 |
| 内存 | >= 8GB | Neo4j + Qdrant 需要 |

---

## 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory

# 2. 创建虚拟环境
python -m venv .venv

# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
# 创建 .env 文件，填入 API 密钥
echo "DEEPSEEK_API_KEY=your-key-here" > .env
echo "GOOGLE_API_KEY=your-key-here" >> .env

# 5. 启动数据库服务
docker-compose up -d

# 6. 验证服务状态
docker-compose ps
# 确保 memory_graph_db 和 memory_vector_db 状态为 running
```

---

## 服务访问

**本地开发：**

| 服务 | 地址 | 凭证 |
|------|------|------|
| Neo4j Browser | http://localhost:7474 | neo4j / railway2025 |
| Qdrant API | http://localhost:6400 | 无需认证 |
| Qdrant Dashboard | http://localhost:6400/dashboard | 无需认证 |

**Railway 远程（已部署）：**

| 服务 | 地址 | 说明 |
|------|------|------|
| REST API | https://<your-app>.up.railway.app/ | 主接口 |
| API 文档 | https://<your-app>.up.railway.app/docs | Swagger UI |
| 健康检查 | https://<your-app>.up.railway.app/health | 存活探测 |
| **Neo4j** | 通过 Railway 内部网络访问 | 无外部公开 URL，仅内部服务可连接 |
| **Qdrant** | 通过 Railway 内部网络访问 | 无外部公开 URL，仅内部服务可连接 |

**Neo4j 访问说明（Railway）**

Railway 上 Neo4j 和 Qdrant 仅通过内部网络访问，不提供外部公开 URL。如需管理，可通过 Railway 控制台或本地端口转发。

- 用户名：`neo4j`
- 密码：在 Railway 的 Neo4j 服务变量 `Neo4jPassword` 中配置；具体值可记录于项目根目录的 `CREDENTIALS.local.md`（该文件已加入 .gitignore，不提交）
- 应用连接 Neo4j：Bolt 端口 **7687**；内部主机由 Railway 注入。

**Qdrant 访问说明（Railway）**

Qdrant 通过 Railway 内部网络访问。服务间：HTTP 端口 `6400`，gRPC 端口 `6334`。

---

## 运行演示

```bash
# 运行多跳推理演示
python main.py
```

预期输出：

```
==================================================
NeuroMemory 多跳推理演示
当前配置: LLM=deepseek, Embedding=local
==================================================

--- 正在构建初始记忆 ---
[输入] DeepMind 是 Google 的子公司。
[海马体] 激活记忆:
  - [vector] ...
[前额叶] 生成回答:
...
[后台] 知识图谱已更新。

... (更多输出)

--- 测试推理能力 ---
[输入] Demis Hassabis 和 Gemini 模型有什么关系？
[海马体] 激活记忆:
  - [graph] Demis Hassabis 是 DeepMind 的 CEO
  - [graph] Gemini 是 DeepMind 团队研发的
  - ...
[前额叶] 生成回答:
Demis Hassabis 作为 DeepMind 的 CEO，领导了 Gemini 模型的研发...
```

---

## 基础使用 (当前方式)

```python
from mem0 import Memory
from config import MEM0_CONFIG
from main import cognitive_process, create_brain

# 初始化
brain = create_brain()

# 添加记忆
cognitive_process(brain, "张三是李四的老板", user_id="test_user")
cognitive_process(brain, "李四负责人工智能项目", user_id="test_user")

# 查询推理
answer = cognitive_process(brain, "张三管理什么项目？", user_id="test_user")
```

---

## 使用 REST API

主要接口为 REST API，详见 [用户接口文档](USER_API.md)。

```bash
# 启动服务
uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

# 使用 curl 调用
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "张三是李四的老板", "user_id": "test_user"}'
```

## 使用 CLI（调试工具）

```bash
neuromemory status
neuromemory add "张三是李四的老板" --user test_user
neuromemory search "张三管理什么" --user test_user --limit 5
neuromemory ask "张三管理什么项目？" --user test_user
neuromemory graph export --user test_user
neuromemory graph visualize --user test_user
```

---

## 下一步

- [测试指南](TESTING.md) - 运行测试套件，验证系统功能
- [配置参考](CONFIGURATION.md) - 了解模型切换和数据库配置
- [接口设计](API.md) - 查看完整 API 文档
- [部署架构](DEPLOYMENT.md) - 了解部署选项
