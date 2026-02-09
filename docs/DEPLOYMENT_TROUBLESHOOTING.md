# 部署问题排查指南

> 返回 [主架构文档](ARCHITECTURE.md)
>
> **最后更新**: 2026-01-26

---

## 目录

- [Neo4j 密码问题](#neo4j-密码问题)
- [服务启动问题](#服务启动问题)
- [健康检查失败](#健康检查失败)
- [本地部署常见问题](#本地部署常见问题)

---

## Neo4j 密码问题

### 问题现象

用户无法通过 Neo4j Browser (http://localhost:7474) 登录，提示密码错误。

### 根本原因

**Neo4j 密码持久化机制**：Neo4j 在首次启动时将密码写入数据卷 (`neo4j_data`)，后续修改 `docker-compose.yml` 中的 `NEO4J_AUTH` 不会影响已存在的数据库。

```
docker-compose.yml 修改密码
        ↓
已存在的 neo4j_data 卷
        ↓
密码不生效（数据卷中保存的是旧密码）
```

### 解决方案

**必须删除数据卷后重新初始化**：

```powershell
# 1. 停止服务并删除数据卷
docker-compose down -v   # -v 参数删除关联的数据卷

# 2. 修改配置文件中的密码（如需要）

# 3. 重新启动服务
docker-compose up -d

# 4. 等待 Neo4j 初始化完成（约 15-30 秒）
# 5. 验证登录
```

### 密码配置位置

统一修改以下文件以保持一致性：

| 文件 | 位置 | 说明 |
|------|------|------|
| `docker-compose.yml` | 3 处 | `NEO4J_PASSWORD` 默认值、`NEO4J_AUTH`、healthcheck |
| `config.py` | 第 179 行 | `neo4j_password` 默认值 |
| `CLAUDE.md` | 服务访问章节 | 文档说明 |
| `README.md` | 快速开始章节 | 文档说明 |
| `docs/GETTING_STARTED.md` | 服务访问表格 | 文档说明 |
| `docs/CONFIGURATION.md` | 数据库配置示例 | 文档说明 |
| `docs/COMPONENTS.md` | Mem0 配置示例 | 文档说明 |
| `docs/MEM0_DEEP_DIVE.md` | 配置示例 | 文档说明 |
| `tests/conftest.py` | local 目标配置 | 测试默认值 |

### 当前密码约定

| 环境 | 密码 | 说明 |
|------|------|------|
| 本地开发 | `railway2025` | docker-compose 默认值 |
| Railway 远程 | `railway2025` | Railway 变量 `Neo4jPassword` |

### 关键经验

1. **修改密码后必须删除数据卷**：`docker-compose down -v`
2. **环境变量优先级**：`NEO4J_PASSWORD` 环境变量 > 配置文件默认值
3. **首次初始化原则**：Neo4j 只在数据卷不存在时读取 `NEO4J_AUTH` 设置密码
4. **统一配置**：本地和远程使用相同密码可减少配置复杂度

---

## 服务启动问题

### Docker Compose 启动顺序

```yaml
# docker-compose.yml
services:
  app:
    depends_on:
      - neo4j
      - qdrant
```

`depends_on` 只保证容器启动顺序，不保证服务就绪。Neo4j 初始化需要 15-30 秒。

### 解决方案

1. **使用健康检查**：`docker-compose.yml` 中已配置 Neo4j healthcheck
2. **应用层重试**：`health_checks.py` 中的连接检查有重试机制
3. **手动等待**：首次启动后等待 30 秒再验证

### 验证服务状态

```powershell
# 查看容器状态
docker-compose ps

# 查看容器日志
docker-compose logs -f app
docker logs memory_graph_db --tail 50

# 检查健康状态
curl http://localhost:8765/health
```

---

## 健康检查失败

### `/health` 返回 `neo4j: false`

**可能原因**：

1. Neo4j 容器未完成初始化
2. 密码配置不一致
3. 网络连接问题

**排查步骤**：

```powershell
# 1. 检查 Neo4j 容器状态
docker logs memory_graph_db --tail 20

# 期望看到：
# "Bolt enabled on 0.0.0.0:7687"

# 2. 检查应用容器日志
docker logs neuromemory_app --tail 20

# 3. 手动测试 Neo4j 连接（在容器内）
docker exec -it memory_graph_db cypher-shell -u neo4j -p railway2025 "RETURN 1"
```

### `/health` 返回 `qdrant: false`

**排查步骤**：

```powershell
# 检查 Qdrant 容器状态
docker logs memory_vector_db --tail 20

# 测试 Qdrant API
curl http://localhost:6400/collections
```

### `/health` 返回 `llm: false`

**可能原因**：

1. API 密钥未配置或无效
2. 网络无法访问 API 端点

**排查步骤**：

```powershell
# 检查环境变量
docker exec neuromemory_app env | grep -E "(DEEPSEEK|GOOGLE|SILICONFLOW)"

# 检查 .env 文件
cat .env
```

---

## 本地部署常见问题

### uvicorn 启动问题

#### 问题现象

误以为需要单独执行 `uvicorn` 命令来启动应用服务。

#### 根本原因

**Docker 容器已自动启动 uvicorn**：`Dockerfile` 的 `CMD` 指令已经配置了 uvicorn 启动命令，监听 8765 端口。当通过 `docker-compose up -d` 启动时，应用容器会自动执行该命令。

```dockerfile
# Dockerfile
CMD ["sh", "-c", "uvicorn http_server:app --host 0.0.0.0 --port ${PORT:-8765} --workers 2"]
```

#### 解决方案

**不要单独执行 uvicorn 命令**：

- ❌ **错误做法**：在本地终端执行 `uvicorn http_server:app --host 0.0.0.0 --port 8765`
- ✅ **正确做法**：直接使用 `docker-compose up -d` 启动，容器会自动运行 uvicorn

如果单独执行 uvicorn 命令，会导致端口冲突（8765 端口已被容器占用），出现类似错误：
```
Error: [Errno 48] Address already in use
```

### 代码修改后的启动流程

在本地修改代码后，需要按以下步骤重新启动服务：

#### 启动步骤

1. **手动启动 Docker Desktop**
   - 确保 Docker Desktop 应用已启动并运行

2. **启动所有服务**
   - **方式一（推荐）**：在 PowerShell 中执行
     ```powershell
     docker-compose up -d
     ```
   - **方式二**：在 Docker Desktop GUI 中点击启动按钮

3. **验证服务状态**
   ```powershell
   # 查看容器状态（应看到 3 个服务：app、neo4j、qdrant）
   docker-compose ps
   
   # 等待服务就绪后检查健康状态
   curl http://localhost:8765/health
   ```

#### 说明

- `docker-compose up -d` 会启动 3 个服务：
  - `neuromemory_app`：应用服务（自动运行 uvicorn）
  - `memory_graph_db`：Neo4j 图数据库
  - `memory_vector_db`：Qdrant 向量数据库
- 代码修改后如需重新构建镜像，使用：`docker-compose up -d --build`

### 服务访问地址

本地部署后，各服务的访问地址如下：

| 服务 | 访问地址 | 说明 |
|------|----------|------|
| **Neo4j 管理界面** | http://localhost:7474/ | Neo4j Browser，用于可视化查询和浏览图数据 |
| **Neo4j 数据库连接** | https://localhost:17687 | Bolt 协议连接地址<br>账号：`neo4j`<br>密码：`railway2025` |
| **Qdrant Dashboard** | http://localhost:6400/dashboard | Qdrant 向量数据库管理界面<br>无需密码 |
| **App 健康检查** | http://localhost:8765/health | 应用健康检查端点<br>用于检查数据库连接状态<br>无 Web 页面，返回 JSON |

#### 访问说明

- **Neo4j Browser**：在浏览器中打开 http://localhost:7474/，输入用户名 `neo4j` 和密码 `railway2025` 即可登录
- **Neo4j Bolt 连接**：用于应用程序连接，使用 `bolt://localhost:17687`
- **Qdrant Dashboard**：可直接访问，无需认证
- **App 健康检查**：访问 http://localhost:8765/health 可查看各服务的连接状态，返回格式如：
  ```json
  {
    "status": "healthy",
    "neo4j": true,
    "qdrant": true,
    "llm": true
  }
  ```

---

## 常用排查命令

```powershell
# 完全重置（删除所有数据）
docker-compose down -v
docker-compose up -d

# 重建镜像（代码更新后）
docker-compose up -d --build

# 进入容器调试
docker exec -it neuromemory_app /bin/bash
docker exec -it memory_graph_db /bin/bash

# 查看实时日志
docker-compose logs -f

# 查看资源使用
docker stats
```

---

## 相关文档

- [快速开始](GETTING_STARTED.md) - 安装和运行指南
- [配置参考](CONFIGURATION.md) - 环境变量和模型配置
- [部署架构](DEPLOYMENT.md) - 详细部署配置
