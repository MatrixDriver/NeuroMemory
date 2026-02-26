# neuromem 高层 API 设计文档

## 概述

高层 API 让用户无需手动提取记忆，只需提交会话数据，系统自动完成：
1. 会话存储
2. 智能分类提取
3. 多后端存储
4. 统一检索

---

## 1. 会话管理 API

### 1.1 添加对话消息

```python
from neuromem import neuromemClient

client = neuromemClient(api_key="nm_xxx")

# 方式1: 逐条添加消息
client.conversations.ingest(
    user_id="user123",
    session_id="session_001",  # 会话 ID（可选，自动生成）
    role="user",
    content="我最喜欢的颜色是蓝色",
    metadata={"timestamp": "2024-01-15T10:00:00"}
)

client.conversations.ingest(
    user_id="user123",
    session_id="session_001",
    role="assistant",
    content="好的，我记住了您喜欢蓝色！"
)

# 方式2: 批量添加（更高效）
client.conversations.add_messages(
    user_id="user123",
    session_id="session_001",
    messages=[
        {"role": "user", "content": "我在 Google 工作"},
        {"role": "assistant", "content": "很高兴认识您！"},
        {"role": "user", "content": "我负责后端开发"},
        {"role": "assistant", "content": "了解了，您是后端工程师。"}
    ]
)
```

### 1.2 自动触发记忆提取

```python
# 自动模式：每 N 条消息或每 M 分钟自动提取
client.conversations.enable_auto_extract(
    user_id="user123",
    trigger="message_count",  # 或 "time_interval"
    threshold=10,  # 每 10 条消息提取一次
    async_mode=True  # 后台异步执行
)

# 手动触发提取
result = client.conversations.extract_memories(
    user_id="user123",
    session_id="session_001"  # 可选：指定会话
)
# => {
#   "preferences_extracted": 2,
#   "facts_extracted": 5,
#   "documents_extracted": 1,
#   "status": "completed"
# }
```

---

## 2. 智能记忆提取

### 2.1 记忆分类体系

```python
class MemoryType:
    """记忆类型枚举"""
    PREFERENCE = "preference"      # 用户偏好（颜色、习惯、设置）
    FACT = "fact"                   # 事实信息（工作、爱好、技能）
    EPISODIC = "episodic"          # 情景记忆（事件、经历）
    PROCEDURAL = "procedural"      # 程序性记忆（规则、技能）
    DOCUMENT = "document"          # 文档（用户上传/引用的文件）
    URL = "url"                    # URL（自动下载并存储）
    SEMANTIC = "semantic"          # 语义知识（概念、关系）
```

### 2.2 LLM 分类器配置

```python
# 配置提取策略
client.config.set_extraction_strategy(
    llm_provider="claude",  # 或 "openai", "gemini"
    model="claude-sonnet-4",
    prompt_template="custom",  # 或使用默认
    batch_size=50,  # 每批处理的消息数
    confidence_threshold=0.7  # 置信度阈值
)
```

---

## 3. 高级检索 API

### 3.1 按类型检索

```python
# 检索所有偏好
preferences = client.memory.get_preferences(user_id="user123")
# => [
#   {"key": "favorite_color", "value": "蓝色", "extracted_at": "..."},
#   {"key": "work_hours", "value": "9:00-18:00", "extracted_at": "..."}
# ]

# 检索事实
facts = client.memory.get_facts(
    user_id="user123",
    category="work",  # 可选分类
    limit=10
)
# => [
#   {"content": "在 Google 工作", "confidence": 0.95, "source": "conversation"},
#   {"content": "负责后端开发", "confidence": 0.92, "source": "conversation"}
# ]

# 检索情景记忆
episodes = client.memory.get_episodes(
    user_id="user123",
    time_range=("2024-01-01", "2024-01-31"),
    limit=20
)

# 语义检索（跨类型）
results = client.memory.search(
    user_id="user123",
    query="用户的工作相关信息",
    memory_types=[MemoryType.FACT, MemoryType.EPISODIC],
    limit=10
)
```

### 3.2 统一记忆视图

```python
# 获取用户的完整记忆画像
profile = client.memory.get_user_profile(user_id="user123")
# => {
#   "preferences": {...},
#   "facts": {...},
#   "recent_episodes": [...],
#   "documents_count": 15,
#   "knowledge_graph": {...}
# }
```

---

## 4. 文件系统 API

### 4.1 添加文档

```python
# 上传文件
doc = client.files.add_document(
    user_id="user123",
    file_path="/path/to/resume.pdf",
    category="personal",
    tags=["resume", "career"],
    auto_extract=True  # 自动提取文本并生成 embedding
)
# => {
#   "file_id": "doc_abc123",
#   "filename": "resume.pdf",
#   "size": 1024000,
#   "url": "https://obs.../abc123.pdf",
#   "embedding_id": "emb_xyz789"
# }

# 从文本创建文档
doc = client.files.add_text(
    user_id="user123",
    title="Meeting Notes",
    content="今天讨论了 Q2 OKR...",
    category="work"
)
```

### 4.2 添加 URL（自动下载）

```python
# 添加网页（自动下载并存储）
doc = client.files.add_url(
    user_id="user123",
    url="https://example.com/article",
    category="reading",
    auto_extract=True,  # 提取正文
    format="markdown"   # 保存格式：markdown/pdf/html
)
# => {
#   "file_id": "url_def456",
#   "original_url": "https://example.com/article",
#   "title": "Article Title",
#   "stored_path": "https://obs.../def456.md",
#   "extracted_facts": 5
# }
```

### 4.3 文件检索和管理

```python
# 列出所有文件
files = client.files.list(
    user_id="user123",
    category="work",  # 可选过滤
    tags=["resume"],
    limit=50
)

# 获取文件内容
content = client.files.get_content(
    user_id="user123",
    file_id="doc_abc123"
)

# 搜索文件内容
results = client.files.search(
    user_id="user123",
    query="后端开发经验",
    file_types=["pdf", "md"]
)

# 删除文件
client.files.delete(user_id="user123", file_id="doc_abc123")
```

---

## 5. 后台任务管理

### 5.1 任务状态查询

```python
# 查询提取任务状态
status = client.tasks.get_status(task_id="task_123")
# => {
#   "task_id": "task_123",
#   "type": "memory_extraction",
#   "status": "processing",  # pending/processing/completed/failed
#   "progress": 0.65,
#   "estimated_time": 120  # 秒
# }

# 查询用户的所有任务
tasks = client.tasks.list(user_id="user123", status="processing")
```

### 5.2 任务配置

```python
# 配置任务调度策略
client.config.set_task_policy(
    user_id="user123",
    extraction_frequency="realtime",  # realtime/hourly/daily
    batch_size=100,
    priority="high"
)
```

---

## 6. 完整使用示例

### 6.1 场景：聊天机器人自动记忆

```python
from neuromem import neuromemClient

class SmartChatbot:
    def __init__(self, api_key: str):
        self.memory = neuromemClient(api_key=api_key)

    def chat(self, user_id: str, message: str, session_id: str = None) -> str:
        # 1. 检索相关记忆（跨类型智能检索）
        context = self.memory.memory.search(
            user_id=user_id,
            query=message,
            memory_types=["preference", "fact", "episodic"],
            limit=5
        )

        # 2. 调用 LLM 生成回复（带上记忆上下文）
        response = call_llm(message, context)

        # 3. 存储会话（自动触发记忆提取）
        self.memory.conversations.add_messages(
            user_id=user_id,
            session_id=session_id,
            messages=[
                {"role": "user", "content": message},
                {"role": "assistant", "content": response}
            ]
        )

        return response

# 使用
bot = SmartChatbot(api_key="nm_xxx")

# 第一次对话
bot.chat("user1", "我喜欢蓝色")
# 系统自动提取并存储偏好：favorite_color = 蓝色

# 第二次对话
bot.chat("user1", "推荐一个主题色")
# 系统自动检索到偏好，LLM 可以回答："根据您喜欢蓝色，推荐..."
```

### 6.2 场景：知识库助手

```python
class KnowledgeAssistant:
    def __init__(self, api_key: str):
        self.memory = neuromemClient(api_key=api_key)

    def add_knowledge_source(self, user_id: str, url: str):
        """添加知识来源（自动下载、提取、存储）"""
        doc = self.memory.files.add_url(
            user_id=user_id,
            url=url,
            category="knowledge",
            auto_extract=True
        )
        return doc["file_id"]

    def ask(self, user_id: str, question: str) -> str:
        """基于知识库回答问题"""
        # 检索相关文档和事实
        results = self.memory.memory.search(
            user_id=user_id,
            query=question,
            memory_types=["document", "fact", "semantic"],
            limit=10
        )

        # 使用 LLM 基于检索结果回答
        answer = call_llm_with_rag(question, results)
        return answer

# 使用
assistant = KnowledgeAssistant(api_key="nm_xxx")

# 添加知识源
assistant.add_knowledge_source("user1", "https://docs.python.org/3/tutorial/")

# 提问
answer = assistant.ask("user1", "Python 如何处理异常？")
# 系统自动从已下载的文档中检索相关内容并回答
```

---

## 7. 存储后端映射

| 记忆类型 | 存储后端 | 检索方式 |
|---------|---------|---------|
| **会话消息** | KV (JSONB) | 按 session_id 查询 |
| **偏好** | Preferences 表 | Key-Value 查询 |
| **事实/情景** | Vector (pgvector) | 语义相似度 |
| **文档/URL** | OBS + Vector | 全文检索 + 语义 |
| **规则/技能** | Graph DB (AGE) | 图查询 |
| **知识图谱** | Graph DB (AGE) | Cypher 查询 |

---

## 8. API 分层对比

### 底层 API（当前）
```python
# 需要用户手动提取和分类
client.add_memory(user_id="u1", content="我喜欢蓝色")
client.preferences.set(user_id="u1", key="color", value="蓝色")
```

### 高层 API（新增）
```python
# 自动处理
client.conversations.ingest(
    user_id="u1",
    role="user",
    content="我喜欢蓝色"
)
# 系统自动：
# 1. 存储会话到 KV
# 2. LLM 识别为偏好
# 3. 提取并存入 Preferences 表
```

---

## 9. 实施路线图

### Phase 1: 会话存储 + 基础提取
- ✅ KV 存储会话
- ✅ 基础 LLM Classifier
- ✅ 偏好和事实提取

### Phase 2: 文件系统
- ⏳ 文档上传 (OBS)
- ⏳ URL 自动下载
- ⏳ 文本提取和 embedding

### Phase 3: 高级分类
- ⏳ 情景记忆时间轴
- ⏳ 程序性记忆 (Graph)
- ⏳ 知识图谱构建

### Phase 4: 智能检索
- ⏳ 跨类型联合检索
- ⏳ 用户画像生成
- ⏳ 记忆可视化

---

## 10. 配置和控制

```python
# 全局配置
client.config.set(
    # 提取策略
    extraction_strategy="aggressive",  # conservative/balanced/aggressive

    # LLM 配置
    llm_provider="claude",
    llm_model="claude-sonnet-4",

    # 触发策略
    auto_extract=True,
    extract_trigger="message_count",
    extract_threshold=10,

    # 存储策略
    enable_compression=True,
    retention_days=365,

    # 隐私控制
    anonymize_pii=False,
    enable_encryption=True
)

# 用户级别控制
client.users.set_preferences(
    user_id="user123",
    auto_extract=False,  # 禁用自动提取
    manual_review=True   # 需要人工审核
)
```

---

## 总结

高层 API 的核心价值：
1. **零配置记忆管理** - 用户只需提交会话
2. **智能自动分类** - LLM 自动识别记忆类型
3. **多后端透明** - 自动选择最优存储
4. **统一检索接口** - 一个 API 查询所有类型
5. **文件系统支持** - URL/文档自动下载和索引

让 AI Agent 开发者专注于业务逻辑，记忆管理交给 neuromem！
