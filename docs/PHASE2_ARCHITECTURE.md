# Phase 2 架构设计

## 图数据库 (Apache AGE)

### 图数据模型

#### 节点类型 (Vertices)

1. **User** - 用户节点
   ```cypher
   {
     id: uuid,
     user_id: string,
     tenant_id: uuid,
     created_at: timestamp
   }
   ```

2. **Memory** - 记忆节点
   ```cypher
   {
     id: uuid,
     content: string,
     memory_type: string,
     tenant_id: uuid,
     created_at: timestamp
   }
   ```

3. **Concept** - 概念节点
   ```cypher
   {
     id: uuid,
     name: string,
     category: string,
     tenant_id: uuid
   }
   ```

4. **Entity** - 实体节点
   ```cypher
   {
     id: uuid,
     name: string,
     type: string,  // person, organization, location, etc.
     tenant_id: uuid
   }
   ```

#### 边类型 (Edges)

1. **HAS_MEMORY** - 用户拥有记忆
   ```cypher
   (User)-[:HAS_MEMORY {created_at: timestamp}]->(Memory)
   ```

2. **MENTIONS** - 记忆提到实体
   ```cypher
   (Memory)-[:MENTIONS {confidence: float}]->(Entity)
   ```

3. **RELATED_TO** - 记忆相关性
   ```cypher
   (Memory)-[:RELATED_TO {similarity: float, type: string}]->(Memory)
   ```

4. **KNOWS** - 用户认识关系
   ```cypher
   (User)-[:KNOWS {relationship: string, since: timestamp}]->(User)
   ```

5. **ABOUT** - 记忆关于概念
   ```cypher
   (Memory)-[:ABOUT {relevance: float}]->(Concept)
   ```

### 使用场景

#### 1. 社交图谱
```cypher
// 查找共同好友
MATCH (u1:User {user_id: 'alice'})-[:KNOWS]-(mutual)-[:KNOWS]-(u2:User {user_id: 'bob'})
RETURN mutual
```

#### 2. 记忆关联网络
```cypher
// 查找相关记忆
MATCH (m1:Memory {id: 'mem123'})-[:RELATED_TO*1..3]-(related:Memory)
RETURN related, similarity
ORDER BY similarity DESC
LIMIT 10
```

#### 3. 知识图谱
```cypher
// 查找用户的所有知识
MATCH (u:User {user_id: 'alice'})-[:HAS_MEMORY]->(m:Memory)-[:ABOUT]->(c:Concept)
RETURN c.name, COUNT(m) as memory_count
ORDER BY memory_count DESC
```

#### 4. 实体网络
```cypher
// 查找与某人相关的所有记忆
MATCH (e:Entity {name: 'John Smith'})<-[:MENTIONS]-(m:Memory)<-[:HAS_MEMORY]-(u:User)
RETURN u.user_id, m.content
```

### API 设计

#### 创建关系
```http
POST /v1/graph/relationships
{
  "source_type": "user",
  "source_id": "user123",
  "edge_type": "KNOWS",
  "target_type": "user",
  "target_id": "user456",
  "properties": {
    "relationship": "colleague",
    "since": "2024-01-01"
  }
}
```

#### 查询图
```http
POST /v1/graph/query
{
  "cypher": "MATCH (u:User {user_id: $user_id})-[:HAS_MEMORY]->(m:Memory) RETURN m LIMIT 10",
  "params": {
    "user_id": "user123"
  }
}
```

#### 查找路径
```http
GET /v1/graph/paths?from_type=user&from_id=user123&to_type=concept&to_id=concept456&max_depth=3
```

#### 获取邻居
```http
GET /v1/graph/neighbors?node_type=memory&node_id=mem123&edge_types=RELATED_TO,ABOUT&limit=10
```

### 数据库架构

```sql
-- AGE 图模式
CREATE GRAPH neuromem_graph;

-- 设置搜索路径
SET search_path = ag_catalog, "$user", public;

-- 创建节点
SELECT * FROM cypher('neuromem_graph', $$
  CREATE (:User {id: 'u1', user_id: 'alice', tenant_id: 't1'})
$$) as (v agtype);

-- 创建边
SELECT * FROM cypher('neuromem_graph', $$
  MATCH (u:User {user_id: 'alice'}), (m:Memory {id: 'm1'})
  CREATE (u)-[:HAS_MEMORY {created_at: timestamp()}]->(m)
$$) as (e agtype);
```

## LLM 分类器

### 记忆自动分类

#### 分类维度

1. **记忆类型**
   - `fact`: 事实性信息
   - `preference`: 用户偏好
   - `event`: 事件记录
   - `opinion`: 观点看法
   - `instruction`: 指令说明

2. **主题分类**
   - 工作 (work)
   - 生活 (life)
   - 兴趣 (interest)
   - 学习 (learning)
   - 社交 (social)

3. **重要性**
   - `critical`: 关键信息
   - `important`: 重要信息
   - `normal`: 普通信息
   - `trivial`: 琐碎信息

#### 实现方案

```python
# 使用 LLM 进行分类
async def classify_memory(content: str) -> MemoryClassification:
    prompt = f"""
    Classify the following user memory:
    "{content}"

    Return JSON:
    {{
      "memory_type": "fact|preference|event|opinion|instruction",
      "topics": ["topic1", "topic2"],
      "importance": "critical|important|normal|trivial",
      "entities": [{{name: "...", type: "person|organization|location"}}],
      "concepts": ["concept1", "concept2"]
    }}
    """
    result = await llm_client.complete(prompt)
    return parse_classification(result)
```

### 实体抽取

自动从记忆中提取：
- 人名
- 组织
- 地点
- 时间
- 事件

### API 端点

```http
POST /v1/memories/classify
{
  "memory_id": "mem123"
}

Response:
{
  "memory_type": "event",
  "topics": ["work", "meeting"],
  "importance": "important",
  "entities": [
    {"name": "John Smith", "type": "person"},
    {"name": "ABC Company", "type": "organization"}
  ],
  "concepts": ["project planning", "deadline"]
}
```

## JSONB KV 存储

### 扩展现有 Preference 模型

```python
class KeyValue(Base, TimestampMixin):
    __tablename__ = "key_values"

    id: uuid
    tenant_id: uuid
    namespace: str  # user, system, app
    scope_id: str   # user_id, app_id, etc.
    key: str
    value: jsonb    # 灵活的 JSON 存储
    ttl: datetime   # 可选的过期时间

    __table_args__ = (
        Index('ix_kv_lookup', 'tenant_id', 'namespace', 'scope_id', 'key'),
    )
```

### 使用场景

1. **用户配置** (namespace=user)
2. **应用状态** (namespace=app)
3. **会话数据** (namespace=session, ttl=1h)
4. **缓存** (namespace=cache, ttl=5m)

### API 端点

```http
POST /v1/kv/{namespace}/{scope_id}
{
  "key": "user.settings.theme",
  "value": {"mode": "dark", "accent": "#007bff"},
  "ttl": 3600
}

GET /v1/kv/{namespace}/{scope_id}/{key}
DELETE /v1/kv/{namespace}/{scope_id}/{key}
GET /v1/kv/{namespace}/{scope_id}?prefix=user.settings
```

## 配额管理

### 配额维度

```python
class TenantQuota(Base):
    __tablename__ = "tenant_quotas"

    tenant_id: uuid
    # 存储配额
    max_memories: int = 10000
    max_preferences: int = 1000
    max_graph_nodes: int = 5000
    max_graph_edges: int = 10000
    max_storage_mb: int = 1000

    # API 配额
    requests_per_minute: int = 60
    requests_per_day: int = 10000

    # 当前使用
    current_memories: int = 0
    current_preferences: int = 0
    current_graph_nodes: int = 0
    current_graph_edges: int = 0
    current_storage_mb: float = 0
```

### 配额检查中间件

```python
async def check_quota(tenant_id: uuid, operation: str):
    quota = await get_tenant_quota(tenant_id)
    usage = await get_current_usage(tenant_id)

    if usage.memories >= quota.max_memories:
        raise HTTPException(
            status_code=429,
            detail="Memory quota exceeded"
        )
```

### API 端点

```http
GET /v1/quotas/usage
Response:
{
  "memories": {"used": 523, "limit": 10000, "percentage": 5.23},
  "preferences": {"used": 45, "limit": 1000, "percentage": 4.5},
  "storage_mb": {"used": 12.5, "limit": 1000, "percentage": 1.25}
}
```

## OBS 文档存储

### 文档模型

```python
class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: uuid
    tenant_id: uuid
    user_id: str
    filename: str
    content_type: str
    size_bytes: int
    obs_key: str         # OBS 对象键
    obs_url: str         # 访问 URL
    checksum: str        # MD5 校验
    metadata_: jsonb     # 文档元数据
    embedding_id: uuid   # 关联的向量
```

### OBS 集成

支持多种对象存储：
- 华为云 OBS
- AWS S3
- 阿里云 OSS
- MinIO (本地开发)

### API 端点

```http
POST /v1/documents/upload
Content-Type: multipart/form-data

Response:
{
  "document_id": "doc123",
  "filename": "report.pdf",
  "size_bytes": 1024000,
  "url": "https://obs.example.com/..."
}

GET /v1/documents/{document_id}
GET /v1/documents/{document_id}/download
DELETE /v1/documents/{document_id}
```

---

## 实施顺序

### 阶段 1: 图数据库 (当前)
- [ ] AGE Docker 配置
- [ ] 图服务层
- [ ] 图 API 端点
- [ ] 图查询测试

### 阶段 2: LLM 分类器
- [ ] 分类服务
- [ ] 实体抽取
- [ ] 自动标注
- [ ] 分类 API

### 阶段 3: KV 存储
- [ ] KV 模型
- [ ] KV 服务层
- [ ] KV API
- [ ] TTL 清理

### 阶段 4: 配额管理
- [ ] 配额模型
- [ ] 配额中间件
- [ ] 使用统计
- [ ] 配额 API

### 阶段 5: OBS 文档
- [ ] 文档模型
- [ ] OBS 集成
- [ ] 上传/下载
- [ ] 文档检索
