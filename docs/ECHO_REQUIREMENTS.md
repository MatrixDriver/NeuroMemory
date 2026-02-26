# Echo 项目对 neuromem 的改进需求

> 来源：`/Users/jacky/code/echo/rpiv/requirements/prd-echo-learning-assistant.md` § 15.3

本文档列出了 Echo AI 个人学习助理项目对 neuromem 的功能需求，并制定实施计划。

---

## 需求概览

| 需求 | 优先级 | 状态 | 预估工时 |
|------|--------|------|---------|
| 1. 文件上传支持 | ⭐⭐⭐ 高 | 📋 待实施 | 2-3 周 |
| 2. 时间序列查询 | ⭐⭐⭐ 高 | 📋 待实施 | 1 周 |
| 3. 图数据库能力增强 | ⭐⭐⭐ 高 | 📋 待实施 | 2-3 周 |
| 4. JSON 存储支持 | ⭐⭐ 中 | ✅ 已完成 | - |
| 5. 学习进度追踪 | ⭐⭐ 中 | 📋 待实施 | 1-2 周 |

**总预估工时**：6-9 周

---

## 特性 1: 文件上传支持 ⭐⭐⭐

### 背景

Echo 需要支持用户上传练习作业（代码截图、图片、PDF、Word 文档）进行反馈分析。当前 neuromem 只支持 URL 方式添加文档，不支持直接文件上传。

### 用户故事

**US-Echo-1**：作为 Echo 用户，我想要上传代码截图或作业文件，以便 AI 分析我的错误并给出改进建议。

### 需求详情

**API 设计**：
```python
# SDK 接口
client.files.upload_file(
    user_id="alice",
    file=file_object,           # 文件对象（bytes 或 File-like）
    filename="homework.pdf",    # 文件名
    category="feedback",        # 分类：feedback/learning/reference
    auto_extract=True,          # 是否自动提取文本并生成 embedding
    metadata={"task_id": "task_123"}  # 可选元数据
)

# 返回
{
    "file_id": "uuid",
    "filename": "homework.pdf",
    "file_size": 1024000,
    "file_type": "application/pdf",
    "obs_url": "https://obs.example.com/...",
    "extracted_text": "...",  # 如果 auto_extract=True
    "created_at": "2025-02-10T10:00:00"
}
```

**支持的文件类型**：
- 图片：PNG、JPG、JPEG、GIF、WebP
- 文档：PDF、Word (.docx)、Markdown (.md)、文本 (.txt)
- 代码：Python (.py)、JavaScript (.js)、其他文本格式

**处理流程**：
1. 接收文件上传（multipart/form-data）
2. 验证文件类型和大小（限制：单文件 < 50MB）
3. 上传到 OBS/S3 对象存储
4. 如果 `auto_extract=True`：
   - PDF → 使用 pypdf 提取文本
   - Word → 使用 python-docx 提取
   - 图片 → OCR 提取文字（可选，使用 Tesseract）
5. 生成 embedding 并存储
6. 记录文件元数据到 `documents` 表

**依赖**：
- 对象存储（OBS/S3/MinIO）
- 文本提取库：pypdf、python-docx
- OCR 库（可选）：pytesseract

### 实施计划

详见 **[特性 1 实施计划](#特性-1-实施计划)**

---

## 特性 2: 时间序列查询 ⭐⭐⭐

### 背景

Echo 需要查询用户最近的学习活动、错误记录、学习历程，以便进行进度追踪和复习提醒。当前 neuromem 不支持按时间范围过滤记忆。

### 用户故事

**US-Echo-2**：作为 Echo，我想要查询用户最近 7 天的学习活动，以便生成学习进度报告和复习提醒。

### 需求详情

**API 设计**：
```python
# 查询时间范围内的情景记忆
client.memory.get_episodes(
    user_id="alice",
    start_time="2025-01-01T00:00:00",  # 开始时间（ISO 8601）
    end_time="2025-01-07T23:59:59",    # 结束时间
    limit=100
)

# 查询最近 N 天的记忆
client.memory.get_recent_memories(
    user_id="alice",
    days=7,  # 最近 7 天
    memory_types=["episodic", "fact"],
    limit=50
)

# 查询学习历程时间线
client.memory.get_timeline(
    user_id="alice",
    start_date="2025-01-01",
    end_date="2025-01-31",
    group_by="day"  # day | week | month
)
```

**数据模型增强**：
- `embeddings` 表已有 `created_at` 字段（timestamp with time zone）
- 添加索引优化时间范围查询

**返回格式**：
```json
{
    "user_id": "alice",
    "time_range": {
        "start": "2025-01-01T00:00:00Z",
        "end": "2025-01-07T23:59:59Z"
    },
    "total": 25,
    "episodes": [
        {
            "id": "uuid",
            "content": "完成了线性回归练习",
            "created_at": "2025-01-05T14:30:00Z",
            "metadata": {"task_id": "task_123"}
        },
        ...
    ]
}
```

### 实施计划

详见 **[特性 2 实施计划](#特性-2-实施计划)**

---

## 特性 3: 图数据库能力增强 ⭐⭐⭐

### 背景

Echo 需要构建和查询知识图谱（学习路径、概念依赖、技能树），当前 neuromem 已集成 Apache AGE，但缺少高层 API 支持。

### 用户故事

**US-Echo-3**：作为 Echo，我想要查询学习路径的依赖关系（阶段 A 依赖阶段 B），以便为用户生成正确的学习顺序。

### 需求详情

**API 设计**：
```python
# 创建节点
client.graph.create_node(
    user_id="alice",
    node_type="Stage",
    node_id="stage_1",
    properties={
        "name": "AI 基础概念",
        "duration": "2 周",
        "level": "beginner"
    }
)

# 创建边（关系）
client.graph.create_edge(
    user_id="alice",
    source_type="Stage",
    source_id="stage_1",
    edge_type="PREREQUISITE",
    target_type="Stage",
    target_id="stage_2"
)

# 查询邻居节点
client.graph.get_neighbors(
    user_id="alice",
    node_type="Stage",
    node_id="stage_2",
    edge_type="PREREQUISITE",
    direction="incoming"  # incoming | outgoing | both
)

# Cypher 查询（高级）
client.graph.query(
    user_id="alice",
    cypher="""
        MATCH (a:Stage)-[:DEPENDS_ON]->(b:Stage)
        WHERE a.user_id = $user_id
        RETURN a.name, b.name
    """,
    params={"user_id": "alice"}
)
```

**支持的图操作**：
- 节点 CRUD（创建、读取、更新、删除）
- 边 CRUD
- 邻居查询（1-hop、N-hop）
- 路径查询（最短路径、所有路径）
- Cypher 原生查询

**典型应用场景**：
1. **学习路径依赖**：
   ```
   (阶段1) -[PREREQUISITE]-> (阶段2) -[PREREQUISITE]-> (阶段3)
   ```
2. **概念关系**：
   ```
   (损失函数) -[PART_OF]-> (机器学习)
   (MSE) -[IS_A]-> (损失函数)
   ```
3. **技能树**：
   ```
   (Python基础) -[ENABLES]-> (AI编程) -[ENABLES]-> (深度学习)
   ```

### 实施计划

详见 **[特性 3 实施计划](#特性-3-实施计划)**

---

## 特性 4: JSON 存储支持 ⭐⭐

### 背景

Echo 需要存储复杂的结构化数据（学习路径、错误记录），需要 PostgreSQL 的 JSONB 支持。

### 状态

✅ **已完成** - PostgreSQL 已启用 JSONB 支持

**现有能力**：
- `embeddings.metadata_` 字段使用 JSONB 类型
- `preferences.metadata_` 字段使用 JSONB 类型
- `conversations.metadata_` 字段使用 JSONB 类型

**使用示例**：
```python
# 存储复杂的学习路径
client.add_memory(
    user_id="alice",
    content="学习路径：AI 编程",
    memory_type="plan",
    metadata={
        "path_id": "uuid",
        "stages": [
            {"stage_id": "s1", "name": "AI 基础", "duration": "2周"},
            {"stage_id": "s2", "name": "机器学习", "duration": "3周"}
        ],
        "total_duration": "5周"
    }
)
```

**无需额外开发**。

---

## 特性 5: 学习进度追踪 ⭐⭐

### 背景

Echo 需要记录和查询用户的学习进度（技能、阶段、任务完成状态），当前 neuromem 没有专门的进度追踪 API。

### 用户故事

**US-Echo-5**：作为 Echo，我想要记录用户完成了某个学习阶段，以便计算学习进度和识别薄弱环节。

### 需求详情

**API 设计**：
```python
# 更新学习进度
client.progress.update(
    user_id="alice",
    skill_id="ai_programming",
    stage_id="stage_2",
    status="completed",  # pending | in_progress | completed | skipped
    metadata={
        "completed_tasks": 8,
        "total_tasks": 10,
        "quality_score": 85
    }
)

# 查询学习进度
progress = client.progress.get(
    user_id="alice",
    skill_id="ai_programming"
)
# 返回
{
    "skill_id": "ai_programming",
    "stages": [
        {
            "stage_id": "stage_1",
            "status": "completed",
            "completed_at": "2025-01-15T10:00:00Z"
        },
        {
            "stage_id": "stage_2",
            "status": "in_progress",
            "progress": 80
        }
    ],
    "overall_progress": 45
}

# 列出所有技能进度
all_progress = client.progress.list(user_id="alice")
```

**数据模型**：
```sql
CREATE TABLE learning_progress (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    user_id VARCHAR NOT NULL,
    skill_id VARCHAR NOT NULL,
    stage_id VARCHAR NOT NULL,
    status VARCHAR NOT NULL,  -- pending | in_progress | completed | skipped
    metadata JSONB,
    completed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(tenant_id, user_id, skill_id, stage_id)
);

CREATE INDEX idx_progress_user_skill
ON learning_progress(tenant_id, user_id, skill_id);
```

### 实施计划

详见 **[特性 5 实施计划](#特性-5-实施计划)**

---

## 实施优先级排序

根据 Echo 的开发阶段和依赖关系，建议按以下顺序实施：

### 第一批（Echo 阶段 1-2 需要）
1. **特性 2: 时间序列查询** （1 周）
   - Echo 阶段 2 需要查询学习历史
   - 相对独立，易于实现

2. **特性 5: 学习进度追踪** （1-2 周）
   - Echo 阶段 2 核心功能
   - 依赖少，可快速实现

### 第二批（Echo 阶段 3 需要）
3. **特性 1: 文件上传支持** （2-3 周）
   - Echo 阶段 2-3 需要
   - 需要 OBS 配置，工作量较大

### 第三批（Echo 未来版本）
4. **特性 3: 图数据库能力增强** （2-3 周）
   - Echo 知识图谱可视化需要
   - 可暂时用 JSON 存储替代

---

## 特性 1 实施计划

### Phase 1: OBS 集成 (1 周)

**任务**：
- [ ] 选择对象存储方案（MinIO 本地 / 华为云 OBS / AWS S3）
- [ ] 配置 OBS 客户端
- [ ] 实现文件上传服务（OBSService）
- [ ] 实现文件下载和预签名 URL

**交付物**：
- `server/app/services/obs.py`
- 配置项：`OBS_ENDPOINT`, `OBS_ACCESS_KEY`, `OBS_SECRET_KEY`, `OBS_BUCKET`

### Phase 2: 文件上传 API (1 周)

**任务**：
- [ ] 设计 `documents` 表结构
- [ ] 实现文件上传端点 `POST /v1/files/upload`
- [ ] 文件类型验证和大小限制
- [ ] 文本提取（PDF、Word）
- [ ] 生成 embedding

**交付物**：
- `server/app/models/document.py`
- `server/app/api/v1/files.py`
- `server/app/services/file_processor.py`

### Phase 3: SDK 集成 (3-5 天)

**任务**：
- [ ] 更新 FilesClient.upload_file()
- [ ] 添加文件列表、删除 API
- [ ] 编写测试

**交付物**：
- `sdk/neuromem/files.py` (更新)
- `tests/v2/test_files.py`

---

## 特性 2 实施计划

### Phase 1: 时间查询 API (3-5 天)

**任务**：
- [ ] 添加时间过滤到现有查询
- [ ] 实现 `GET /v1/memory/episodes?start_time=&end_time=`
- [ ] 实现 `GET /v1/memory/timeline`
- [ ] 添加数据库索引优化

**交付物**：
- `server/app/api/v1/memory.py`
- 数据库迁移（索引）

### Phase 2: SDK 集成 (2 天)

**任务**：
- [ ] 更新 MemoryClient 添加时间查询方法
- [ ] 编写测试

**交付物**：
- `sdk/neuromem/memory.py` (更新)
- `tests/v2/test_memory_time.py`

---

## 特性 3 实施计划

### Phase 1: 图 API 设计 (1 周)

**任务**：
- [ ] 设计图 API 接口
- [ ] 实现节点 CRUD
- [ ] 实现边 CRUD
- [ ] 邻居查询

**交付物**：
- `server/app/api/v1/graph.py` (扩展)
- `server/app/services/graph.py`

### Phase 2: Cypher 查询支持 (1 周)

**任务**：
- [ ] 实现 Cypher 查询端点
- [ ] 查询结果格式化
- [ ] 安全性验证（防注入）

### Phase 3: SDK 和测试 (3-5 天)

**任务**：
- [ ] 完善 GraphClient
- [ ] 编写测试
- [ ] 文档和示例

**交付物**：
- `sdk/neuromem/graph.py` (完善)
- `tests/v2/test_graph.py`

---

## 特性 5 实施计划

### Phase 1: 数据模型 (2-3 天)

**任务**：
- [ ] 创建 `learning_progress` 表
- [ ] 实现 ProgressService

**交付物**：
- `server/app/models/progress.py`
- `server/app/services/progress.py`

### Phase 2: API 实现 (2-3 天)

**任务**：
- [ ] 实现进度更新 API
- [ ] 实现进度查询 API
- [ ] 聚合计算（总进度）

**交付物**：
- `server/app/api/v1/progress.py`

### Phase 3: SDK 和测试 (2 天)

**任务**：
- [ ] 实现 ProgressClient
- [ ] 编写测试

**交付物**：
- `sdk/neuromem/progress.py`
- `tests/v2/test_progress.py`

---

## 总结

本文档列出了 Echo 项目对 neuromem 的 5 个改进需求，并制定了详细的实施计划。

**建议实施顺序**：
1. ✅ 特性 4 (已完成)
2. 特性 2: 时间序列查询 (1 周)
3. 特性 5: 学习进度追踪 (1-2 周)
4. 特性 1: 文件上传支持 (2-3 周)
5. 特性 3: 图数据库能力增强 (2-3 周)

**总预估工时**：6-9 周

这些特性的实现将使 neuromem 从单纯的记忆存储系统升级为支持复杂应用场景的完整平台。
