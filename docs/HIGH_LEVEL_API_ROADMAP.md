# neuromem 高层 API 实施路线图

## 🎯 目标

将 neuromem 从"底层记忆 API"升级为"智能记忆管理平台"，让用户：
- 无需手动提取和分类记忆
- 只需提交对话，系统自动处理
- 获得跨类型的智能检索能力

---

## 📅 分阶段实施计划

### Phase 1: 会话存储 + 基础记忆提取 （4-6 周）✅ **已完成（v0.2.0）**

#### 1.1 会话存储 (1-2 周) ✅

**后端实现：**
- [x] 设计会话数据模型
  - `ConversationMessage` 和 `ConversationSession` 模型
  - 支持 user_id 隔离（无 tenant_id）
  - 索引优化：按 user_id + session_id

- [x] 实现会话 API（Python 框架）
  - `conversations.add_message()` - 添加单条消息
  - `conversations.add_messages_batch()` - 批量添加
  - `conversations.get_session_messages()` - 获取会话历史
  - `conversations.list_sessions()` - 列出所有会话
  - `conversations.close_session()` - 关闭会话

**Python SDK：**
- [x] `conversations.py` 模块（ConversationService）
- [x] ConversationsFacade 集成到 neuromem 主类
- [x] 单元测试（test_conversations.py）

---

#### 1.2 LLM Classifier 集成 (2-3 周) ✅

**核心功能：**
- [x] **MemoryExtractionService** - LLM 记忆提取服务
  - 支持多语言提取（中文/英文，自动检测或 KV 偏好）
  - 提取类型：Facts, Preferences, Episodes, Triples（图关系）
  - 自动标注：重要性评分、情感标注（valence/arousal）
  - 实现：`neuromem/services/memory_extraction.py`

- [x] **自动提取机制（v0.2.0）**
  - `auto_extract=True`（默认）：每次 `add_message()` 自动提取
  - 同步提取，立即可检索
  - 无需手动调用 `extract_memories()`

- [x] 提取策略配置
  - **实时提取**（推荐）：`auto_extract=True`
  - **手动提取**：`auto_extract=False` + 手动 `reflect()`
  - ~~任务队列~~ - v0.2.0 采用同步提取，简化架构

**Python API：**
- [x] `conversations.add_message()` - 自动提取（默认）
- [x] `extract_memories()` - 手动触发（内部使用）
- [x] `reflect()` - 生成洞察 + 更新画像

---

#### 1.3 记忆分类存储 (1 周) ✅

**存储映射：**
- [x] 所有记忆类型统一存储在 `Embedding` 表
  - `memory_type`: fact / preference / episodic / insight / general
  - `metadata`: 包含 importance, emotion, tags 等

**数据模型：**
```python
class Embedding:
    id: UUID
    user_id: str
    content: str
    memory_type: str  # fact/episodic/preference/insight/general
    embedding: Vector  # pgvector
    metadata: dict  # importance, emotion, tags, source_session_id
    created_at: datetime
```

**已实现特性：**
- [x] 情感标注（valence, arousal）
- [x] 重要性评分（1-10）
- [x] 来源追踪（source_session_id）
- [x] 时间索引（created_at）

---

### Phase 2: 文件系统 + URL 管理 （3-4 周）

#### 2.1 对象存储集成 (1-2 周)

**技术选型：**
- 华为云 OBS
- MinIO（开源替代）
- AWS S3 兼容

**实现：**
- [ ] OBS 客户端封装
- [ ] 文件上传/下载 API
- [ ] 文件元数据管理

```python
class OBSService:
    def upload_file(self, file_path: str, user_id: str) -> str:
        """上传文件到 OBS，返回 URL"""
        bucket = f"neuromem-{tenant_id}"
        key = f"{user_id}/{uuid4()}/{filename}"
        # 上传到 OBS
        return obs_url

    def download_url(self, url: str) -> bytes:
        """下载 URL 内容"""
        # 支持 HTTP/HTTPS
        ...
```

**数据模型：**
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    tenant_id UUID,
    user_id VARCHAR,
    filename VARCHAR,
    file_type VARCHAR,  -- pdf/md/txt/html
    file_size BIGINT,
    obs_url TEXT,  -- OBS 存储位置
    original_url TEXT,  -- 如果来自 URL
    category VARCHAR,
    tags TEXT[],
    created_at TIMESTAMP
);

CREATE INDEX idx_documents_user ON documents(tenant_id, user_id);
```

**预计工时：** 1-2 周

---

#### 2.2 文本提取 + Embedding (1 周)

**文本提取：**
- [ ] PDF → pypdf2 / pdfplumber
- [ ] Word → python-docx
- [ ] HTML → BeautifulSoup / Readability

**Embedding 生成：**
- [ ] 分块策略（Chunk）
  - 固定长度（512 token）
  - 滑动窗口（overlap 50 token）
  - 语义分块（按段落）

- [ ] 批量生成 embedding
  ```python
  def process_document(doc_id: str):
      content = extract_text(doc_id)
      chunks = split_into_chunks(content, size=512)

      for chunk in chunks:
          embedding = generate_embedding(chunk)
          save_to_db(
              content=chunk,
              embedding=embedding,
              document_id=doc_id,
              memory_type="document"
          )
  ```

**API 端点：**
- [ ] `POST /v1/files/documents` - 上传文档
- [ ] `POST /v1/files/text` - 从文本创建
- [ ] `POST /v1/files/urls` - 添加 URL（自动下载）
- [ ] `GET /v1/files` - 列出文件
- [ ] `GET /v1/files/{file_id}/content` - 获取内容
- [ ] `POST /v1/files/search` - 搜索文件
- [ ] `DELETE /v1/files/{file_id}` - 删除文件

**预计工时：** 1 周

---

#### 2.3 URL 自动下载 (1 周)

**网页抓取：**
- [ ] 使用 Playwright / Selenium 渲染动态页面
- [ ] 提取正文（Readability.js）
- [ ] 转换为 Markdown

```python
class URLProcessor:
    def process_url(self, url: str, user_id: str, format: str = "markdown"):
        """处理 URL：下载、提取、存储"""
        # 1. 下载页面
        html = download_page(url)

        # 2. 提取正文
        article = extract_article(html)

        # 3. 转换格式
        if format == "markdown":
            content = html_to_markdown(article.html)
        elif format == "pdf":
            content = html_to_pdf(article.html)

        # 4. 上传到 OBS
        obs_url = upload_to_obs(content, user_id)

        # 5. 生成 embedding
        process_document(doc_id)

        return {
            "file_id": doc_id,
            "title": article.title,
            "url": obs_url
        }
```

**预计工时：** 1 周

---

### Phase 3: 基准测试 + 高级检索 + 记忆画像 （3-5 周）

#### 3.0 基准测试（LoCoMo + LongMemEval）(1-2 周)

使用学术界标准基准测试评估 neuromem 的记忆召回质量，与 mem0、Zep 等框架横向对比。

**LoCoMo**（ACL 2024，Long Conversation Memory）：
- 论文：[arXiv:2402.17753](https://arxiv.org/abs/2402.17753)
- 数据集：10 组多轮多 session 对话（400-680 轮/组），1986 个 QA 对
- 5 类问题：多跳推理(282)、时间推理(321)、开放域(96)、单跳(841)、对抗性(446)
- 评测流程：
  1. **记忆注入**：按 session 逐轮喂入对话，调用 `add_message()` + `extract_memories()`
  2. **问答检索**：对每个 QA，调用 `recall()` 召回相关记忆，LLM 生成回答
  3. **评分**：Token F1 + BLEU-1 + LLM Judge（GPT-4o 二元判定）
- 参考实现：[mem0/evaluation](https://github.com/mem0ai/mem0/tree/main/evaluation)

**LongMemEval**（ICLR 2025，超长记忆评测）：
- 论文：[arXiv:2410.10813](https://arxiv.org/abs/2410.10813)
- 数据集：500 个问题，对话长度 115k~1.5M tokens
- 5 类能力：信息提取、多 session 推理、时间推理、知识更新、拒答
- 比 LoCoMo 更长更难（商业系统准确率仅 30-70%）
- 参考实现：[xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval)

**实现计划：**
```
evaluation/
  dataset/
    locomo10.json            # LoCoMo 数据集
    longmemeval/             # LongMemEval 数据集
  src/
    neuromem_add.py       # 记忆注入：对话 → add_message → extract_memories
    neuromem_search.py    # 问答检索：recall → LLM 生成回答
  metrics/
    f1.py                    # Token F1
    bleu.py                  # BLEU-1
    llm_judge.py             # GPT-4o 二元判定
  run_eval.py                # 主评测脚本
  generate_scores.py         # 按类别汇总分数
```

- [ ] 搭建评测框架（数据加载、结果保存、指标计算）
- [ ] 实现 LoCoMo 评测（记忆注入 + 问答 + 评分）
- [ ] 实现 LongMemEval 评测
- [ ] 与 mem0、Zep 结果横向对比

**预计工时：** 1-2 周

---

#### 3.1 跨类型统一检索 (1 周)

**实现：**
```python
class UnifiedSearch:
    def search(
        self,
        user_id: str,
        query: str,
        memory_types: List[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """跨类型检索"""
        results = []

        # 1. 偏好匹配（关键词）
        if not memory_types or "preference" in memory_types:
            prefs = search_preferences(user_id, query)
            results.extend(format_results(prefs, type="preference"))

        # 2. 向量检索（事实、情景、文档）
        if not memory_types or any(t in memory_types for t in ["fact", "episodic", "document"]):
            embedding = generate_embedding(query)
            vectors = vector_search(user_id, embedding, memory_types)
            results.extend(format_results(vectors, type="semantic"))

        # 3. 图查询（关系、规则）
        if not memory_types or "graph" in memory_types:
            graph_results = graph_search(user_id, query)
            results.extend(format_results(graph_results, type="graph"))

        # 4. 合并和排序
        return merge_and_rank(results, limit)
```

**API 端点：**
- [ ] `POST /v1/memory/search` - 统一检索
- [ ] `GET /v1/memory/preferences` - 获取所有偏好
- [ ] `GET /v1/memory/facts` - 获取事实
- [ ] `GET /v1/memory/episodes` - 获取情景记忆

**预计工时：** 1 周

---

#### 3.2 用户记忆画像 (1-2 周)

**画像生成：**
```python
class UserProfile:
    def generate_profile(self, user_id: str) -> Dict:
        """生成用户完整画像"""
        return {
            "basic_info": {
                "preferences_count": count_preferences(user_id),
                "facts_count": count_facts(user_id),
                "documents_count": count_documents(user_id),
            },
            "preferences": get_all_preferences(user_id),
            "top_facts": get_top_facts(user_id, limit=10),
            "recent_episodes": get_recent_episodes(user_id, days=7),
            "knowledge_graph": generate_knowledge_graph(user_id),
            "timeline": generate_timeline(user_id),
        }
```

**可视化：**
- [ ] 记忆时间轴
- [ ] 知识图谱可视化
- [ ] 偏好雷达图

**API 端点：**
- [ ] `GET /v1/memory/users/{user_id}/profile` - 用户画像
- [ ] `GET /v1/memory/timeline` - 记忆时间轴

**预计工时：** 1-2 周

---

### Phase 4: 优化和扩展 （2-3 周）

#### 4.1 性能优化

- [ ] 缓存层（Redis）
  - 缓存高频查询结果
  - 缓存 embedding 向量

- [ ] 批量操作优化
  - 批量生成 embedding
  - 批量插入数据库

- [ ] 异步任务优化
  - 优先级队列
  - 任务重试机制

**预计工时：** 1 周

---

#### 4.2 高级特性

- [ ] 记忆遗忘策略
  - 按时间衰减
  - 按访问频率
  - 手动归档

- [ ] 记忆冲突检测
  - 检测矛盾信息
  - 提示用户确认

- [ ] 多模态支持
  - 图片记忆（OCR + 图像 embedding）
  - 音频记忆（语音转文本）

**预计工时：** 1-2 周

---

## 🔧 技术栈

### 后端
- **Web 框架**: FastAPI (Python) 或 Spring Boot (Java)
- **任务队列**: Celery + Redis
- **对象存储**: 华为云 OBS / MinIO
- **LLM**: Claude API / OpenAI API
- **文本提取**: pypdf2, python-docx, BeautifulSoup
- **网页渲染**: Playwright

### 数据库
- **会话存储**: PostgreSQL (JSONB)
- **向量检索**: pgvector
- **文档元数据**: PostgreSQL
- **缓存**: Redis

---

## 📊 预估工时和人力

| 阶段 | 工作内容 | 预估工时 | 人力需求 |
|------|---------|---------|---------|
| Phase 1 | 会话存储 + 记忆提取 | 4-6 周 | 2 后端 + 1 LLM |
| Phase 2 | 文件系统 + URL | 3-4 周 | 2 后端 |
| Phase 3 | 基准测试 + 高级检索 + 画像 | 3-5 周 | 2 后端 |
| Phase 4 | 优化和扩展 | 2-3 周 | 2 后端 + 1 前端 |
| **总计** | | **12-18 周** | **2-3 人** |

---

## 🎯 里程碑

### M1: MVP（6 周）✅ **已完成（v0.2.0）**
- ✅ 会话存储
- ✅ 自动记忆提取（auto_extract）
- ✅ 统一检索 API（recall + search）
- ✅ Python 框架（非 SDK，直接嵌入）
- ✅ 多语言支持（中文/英文）

### M2: 文件系统（9 周）
- ✅ 文档上传和管理
- ✅ URL 自动下载
- ✅ 全文检索

### M3: 完整版（12 周）
- ✅ 用户画像
- ✅ 记忆时间轴
- ✅ 性能优化

### M4: 高级特性（16 周）
- ✅ 多模态支持
- ✅ 记忆管理策略
- ✅ 可视化界面

---

## 🚀 快速启动（最小可行方案）

如果要快速验证，可以先实现核心功能：

**Week 1-2:**
- [ ] 会话存储（简化版，单表）
- [ ] 手动调用 LLM 提取（无队列）
- [ ] 存入 preferences 和 embeddings

**Week 3-4:**
- [ ] 统一检索 API
- [ ] Python SDK 集成
- [ ] 基础测试

这样 4 周就能出 Demo，验证产品方向！

---

## 📝 后续规划

### 企业级功能
- 记忆权限管理
- 多租户资源隔离
- 记忆审计日志
- 合规和隐私控制

### 开发者工具
- 记忆调试工具
- 性能分析仪表板
- 记忆质量评分

### 生态建设
- LangChain 插件
- AutoGPT 集成
- Semantic Kernel 适配器

---

**让我们开始构建下一代智能记忆管理平台！** 🚀
