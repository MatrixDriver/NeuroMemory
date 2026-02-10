# NeuroMemory v1 文档（已弃用）

> ⚠️ **警告**: v1 架构已停止维护，本目录仅作为历史参考。
>
> **新项目请使用 v2**: [../v2/README.md](../v2/README.md)

---

## 为什么弃用 v1？

v1 架构基于 **Neo4j 知识图谱 + Qdrant 向量数据库 + Mem0 框架**，虽然功能强大，但存在以下问题：

1. **部署复杂**: 需要维护 3 个独立服务（Neo4j + Qdrant + API）
2. **运维成本高**: 3 套监控、备份、升级流程
3. **跨库事务困难**: 数据一致性难以保证
4. **学习曲线陡**: 需要学习 Cypher 查询语言和 Qdrant API
5. **成本高**: 企业版 Neo4j 价格昂贵

## v2 的改进

v2 采用 **PostgreSQL + pgvector 统一存储**，带来以下优势：

- ✅ **简化部署**: 只需 2 个服务（API + PostgreSQL）
- ✅ **降低成本**: PostgreSQL 完全开源免费
- ✅ **原生事务**: ACID 事务保证数据一致性
- ✅ **标准 SQL**: 学习曲线平缓
- ✅ **高性能**: pgvector HNSW 索引性能接近专用 VectorDB

---

## v1 文档索引

以下文档描述 v1 架构（Neo4j + Qdrant + Mem0）：

| 文档 | 说明 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | v1 系统架构设计 |
| [HOW_IT_WORKS.md](HOW_IT_WORKS.md) | v1 工作原理和数据流 |
| [API.md](API.md) | v1 REST API 接口 |
| [COMPONENTS.md](COMPONENTS.md) | v1 核心组件说明 |
| [DATA_MODEL.md](DATA_MODEL.md) | v1 数据模型（图 + 向量） |
| [MEM0_DEEP_DIVE.md](MEM0_DEEP_DIVE.md) | Mem0 框架深度解析 |

---

## 迁移到 v2

### 如果你依赖知识图谱功能

- **选项 1**: 继续使用 v1 部署（自行维护）
- **选项 2**: 等待 v2 的 AGE 图数据库支持（Phase 2 计划中）

### 如果你只使用向量检索

直接迁移到 v2，步骤如下：

1. **导出 v1 数据**:
   ```bash
   # 导出 Qdrant 向量数据
   # （需要自行实现导出脚本）
   ```

2. **安装 v2**:
   ```bash
   cd NeuroMemory
   docker compose -f docker-compose.v2.yml up -d
   ```

3. **注册租户**:
   ```bash
   curl -X POST http://localhost:8765/v1/tenants/register \
     -H "Content-Type: application/json" \
     -d '{"name": "MyCompany", "email": "admin@example.com"}'
   ```

4. **导入数据**:
   ```python
   from neuromemory_client import NeuroMemoryClient

   client = NeuroMemoryClient(api_key="nm_xxx")

   # 重新添加记忆（会自动生成 embedding）
   for memory in old_memories:
       client.add_memory(
           user_id=memory["user_id"],
           content=memory["content"],
           memory_type=memory["memory_type"]
       )
   ```

5. **更新客户端代码**:
   - v1 的 `/process` 端点 → v2 的 `/v1/memories` 和 `/v1/search`
   - 添加 API Key 认证头: `Authorization: Bearer nm_xxx`

---

## v1 技术栈（历史参考）

| 组件 | 技术 |
|------|------|
| LLM | DeepSeek / Gemini |
| Embedding | HuggingFace / Gemini / SiliconFlow |
| Vector DB | Qdrant |
| Graph DB | Neo4j 5.26.0 |
| Framework | Mem0 + LangChain |
| API Server | FastAPI |

---

## 支持

v1 相关问题：
- 查看本目录下的文档
- 提交 Issue 并标注 `[v1]` 标签

**推荐**: 迁移到 v2 并参考 [v2 文档](../v2/README.md)

---

**最后更新**: 2026-02-10
