---
description: "功能实施计划: context-aware-recall-v2"
status: completed
created_at: 2026-03-05T17:15:00
updated_at: 2026-03-05T17:45:00
archived_at: null
related_files:
  - rpiv/requirements/prd-context-aware-recall-v2.md
---

# 功能: Context-Aware Recall V2

以下计划应该是完整的，但在开始实施之前，验证文档和代码库模式以及任务合理性非常重要。

特别注意现有工具、类型和模型的命名。从正确的文件导入等。

## 功能描述

通过两条路径增强 neuromem 的语境感知能力：
1. **参数调优**：用 A/B 实验（MRR 指标）找到 ContextService 的最优参数组合
2. **记忆级 Context 标注**：在 LLM 提取 fact/episodic 时同时输出 context 标签，recall 时对所有记忆类型应用 context boost

## 用户故事

作为 AI agent 开发者，
我希望当用户在工作场景下提问时，recall 优先返回工作相关的记忆，
以便 agent 给出更精准的上下文回复。

## 问题陈述

V1 的 context-aware recall 存在两个核心问题：
1. `MARGIN_THRESHOLD=0.05` 过高，大多数查询被判为 general
2. context boost 仅对 trait 生效（hardcoded `memory_type = 'trait'`），fact/episodic 无法获得 context bonus
3. boost 值硬编码在 `search.py` 中（0.10/0.07），未引用 `ContextService` 的参数常量

## 解决方案陈述

1. 通过 3 组参数 A/B 实验确定最优 `MARGIN_THRESHOLD` 和 `MAX_CONTEXT_BOOST`
2. 修改 extraction prompt 让 LLM 在提取 fact/episodic 时同时输出 `context` 字段
3. 将 context 值写入 `trait_context` 列（已存在，无 DDL 变更）
4. 修改 `search.py` 的 context_bonus_sql，去掉 `memory_type = 'trait'` 限制
5. 提供历史回填脚本

## 功能元数据

**功能类型**：增强
**估计复杂度**：中
**主要受影响的系统**：MemoryExtractionService, SearchService, ContextService
**依赖项**：无新增外部依赖

---

## 上下文参考

### 相关代码库文件（实施前必须阅读）

- `neuromem/services/context.py` (L173-184) - ContextService 参数常量定义
- `neuromem/services/context.py` (L227-263) - `infer_context()` 推断逻辑，使用 MARGIN_THRESHOLD
- `neuromem/services/search.py` (L248-265) - `scored_search()` 方法签名，接收 `query_context` 和 `context_confidence`
- `neuromem/services/search.py` (L348-363) - context_bonus_sql 生成逻辑（当前仅 trait）
- `neuromem/services/search.py` (L430-460) - context_bonus_sql 在最终 score 计算中的位置
- `neuromem/services/memory_extraction.py` (L298-411) - `_build_zh_prompt()` 中文 extraction prompt
- `neuromem/services/memory_extraction.py` (L413-526) - `_build_en_prompt()` 英文 extraction prompt
- `neuromem/services/memory_extraction.py` (L663-801) - `_store_facts()` fact 存储逻辑
- `neuromem/services/memory_extraction.py` (L803-912) - `_store_episodes()` episode 存储逻辑
- `neuromem/models/memory.py` (L70) - `trait_context: Mapped[str | None] = mapped_column(String(20), nullable=True)`
- `neuromem/_core.py` (L627-628) - ContextService 初始化
- `neuromem/_core.py` (L1190-1205) - recall 中调用 infer_context 并传递给 scored_search
- `neuromem/db.py` (L113) - trait_context 列 DDL
- `neuromem/db.py` (L222-223) - trait_context 索引 DDL

### 测试参考文件

- `tests/test_recall_context_match.py` - 现有 context match 集成测试（仅测试 trait，需扩展到 fact/episodic）
- `tests/test_context_inference.py` - ContextService 单元测试
- `tests/conftest.py` - MockEmbeddingProvider, MockLLMProvider, db_session fixture

### 要创建的新文件

- `scripts/eval_context_params.py` - 参数 A/B 评估脚本
- `scripts/backfill_context.py` - 历史 context 回填脚本

### 要修改的现有文件

- `neuromem/services/memory_extraction.py` - prompt 增加 context 字段 + 存储逻辑
- `neuromem/services/search.py` - context_bonus_sql 扩展到全类型 + 引用参数
- `neuromem/services/context.py` - 更新参数常量（P0 完成后）
- `tests/test_recall_context_match.py` - 扩展测试覆盖 fact/episodic context boost
- `tests/test_memory_extraction.py` - 新增 context 标注测试

### 要遵循的模式

**存储模式** — 参考 `_store_facts()` (L746-797) 中 Memory 构造：
```python
embedding_obj = Memory(
    user_id=user_id,
    content=content,
    embedding=embedding_vector,
    memory_type="fact",
    metadata_=meta,
    extracted_timestamp=resolved_ts,
    valid_from=now,
    content_hash=content_hash,
    valid_at=now,
    # 新增: trait_context=context,
)
```

**context 白名单验证模式** — 参考 `search.py` (L349):
```python
_VALID_CONTEXTS = {"work", "personal", "social", "learning", "general"}
```

**SQL CASE 模式** — 参考 `search.py` (L353-361) 的 context_bonus_sql 生成

**日志模式** — `logger = logging.getLogger(__name__)`，使用 `logger.info()` / `logger.debug()`

**测试模式** — 参考 `test_recall_context_match.py` 的 helper 函数和断言风格

---

## 实施计划

### 阶段 1: Extraction Prompt + 存储（核心改动）

修改 LLM 提取流程，让新 ingest 的 fact/episodic 自动携带 context 标签。

**任务**:
- 修改 extraction prompt（中/英双语）增加 context 字段
- 修改 `_store_facts()` 和 `_store_episodes()` 读取并写入 `trait_context`
- 增加无效值降级逻辑

### 阶段 2: Recall Boost 增强

扩展 context_bonus_sql 到全记忆类型，引用 ContextService 参数。

**任务**:
- 修改 `search.py` 的 context_bonus_sql 生成逻辑
- 将硬编码 boost 值改为引用 ContextService 参数
- 更新 `scored_search()` 以接收 ContextService 参数

### 阶段 3: 回填脚本 + 评估脚本

提供历史数据回填和参数评估工具。

**任务**:
- 创建 `scripts/backfill_context.py`
- 创建 `scripts/eval_context_params.py`

### 阶段 4: 测试

验证所有改动的正确性。

**任务**:
- 扩展现有测试
- 新增 context 标注测试

---

## 逐步任务

重要：按顺序从上到下执行每个任务。每个任务都是原子的且可独立测试。

### Task 1: UPDATE `neuromem/services/memory_extraction.py` — 中文 prompt 增加 context 字段

- **IMPLEMENT**: 在 `_build_zh_prompt()` 方法中，fact 和 episode 的 JSON 格式说明里增加 `context` 字段
- **位置**: fact 格式说明在 L338 左右（`"emotion": ...` 之后），episode 格式说明在 L382 左右
- **插入内容（fact 部分，在 emotion 字段说明之后）**:
```
   - context: 该记忆所属的语境类别（必填）
     * "work": 工作、编程、项目、会议、职业、技术相关
     * "personal": 个人生活、家庭、健康、兴趣爱好、旅行
     * "social": 社交关系、聚会、人际交往、约会
     * "learning": 学习、教育、论文、课程、理论研究
     * "general": 无法明确归类时使用此值
```
- **插入内容（episode 部分，在 entities 字段说明之后）**:
```
   - context: 该事件所属的语境类别（必填），可选值: work / personal / social / learning / general
```
- **同时**在 fact 的 JSON 格式模板中添加 `"context": "分类"` 字段（在 `"emotion"` 之后）
- **同时**在 episode 的 JSON 格式模板中添加 `"context": "分类"` 字段
- **GOTCHA**: 确保 JSON 格式示例中的花括号使用双花括号 `{{` 转义（因为是 f-string）
- **VALIDATE**: `uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('import ok')"`

### Task 2: UPDATE `neuromem/services/memory_extraction.py` — 英文 prompt 增加 context 字段

- **IMPLEMENT**: 在 `_build_en_prompt()` 方法中，对称地增加 context 字段说明
- **位置**: fact 格式说明在 L453 左右，episode 格式说明在 L497 左右
- **插入内容（fact 部分）**:
```
   - context: The context category this memory belongs to (required)
     * "work": programming, projects, meetings, career, technology
     * "personal": daily life, family, health, hobbies, travel
     * "social": social relationships, gatherings, interpersonal interactions, dating
     * "learning": studying, education, papers, courses, theoretical research
     * "general": use when the context cannot be clearly determined
```
- **插入内容（episode 部分）**:
```
   - context: The context category this event belongs to (required), options: work / personal / social / learning / general
```
- **PATTERN**: 与 Task 1 完全对称，遵循 `_build_en_prompt()` 的英文风格
- **VALIDATE**: `uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('import ok')"`

### Task 3: UPDATE `neuromem/services/memory_extraction.py` — `_store_facts()` 写入 trait_context

- **IMPLEMENT**: 在 `_store_facts()` (L746 左右的 Memory 构造) 中：
  1. 在 Memory 构造之前，解析 context 值：
     ```python
     context = fact.get("context", "general")
     if context not in {"work", "personal", "social", "learning", "general"}:
         context = "general"
     ```
  2. 在 Memory 构造函数中添加 `trait_context=context`
- **位置**: 在 `embedding_obj = Memory(...)` 构造语句中，在 `valid_at=now,` 之后添加 `trait_context=context,`
- **PATTERN**: 参考 `neuromem/services/trait_engine.py:116` 的 `trait_context=context` 写法
- **GOTCHA**: context 验证必须在 Memory 构造之前完成，确保无效值降级为 "general"
- **VALIDATE**: `uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('ok')"`

### Task 4: UPDATE `neuromem/services/memory_extraction.py` — `_store_episodes()` 写入 trait_context

- **IMPLEMENT**: 在 `_store_episodes()` (L895 左右的 Memory 构造) 中：
  1. 在 Memory 构造之前，解析 context 值（同 Task 3 的验证逻辑）
  2. 在 Memory 构造函数中添加 `trait_context=context`
- **位置**: 在 `embedding_obj = Memory(...)` 构造语句中，在 `valid_at=now,` 之后添加 `trait_context=context,`
- **PATTERN**: 与 Task 3 完全相同的验证和写入模式
- **VALIDATE**: `uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('ok')"`

### Task 5: UPDATE `neuromem/services/search.py` — context_bonus_sql 扩展到全类型

- **IMPLEMENT**: 修改 `scored_search()` (L348-363) 的 context_bonus_sql 生成逻辑
- **当前代码** (L353-361):
  ```python
  context_bonus_sql = (
      f"CASE"
      f"  WHEN memory_type = 'trait' AND trait_context = '{query_context}'"
      f"  THEN {0.10 * context_confidence:.4f}"
      f"  WHEN memory_type = 'trait' AND trait_context = 'general'"
      f"  THEN {0.07 * context_confidence:.4f}"
      f"  ELSE 0"
      f" END"
  )
  ```
- **目标代码**:
  ```python
  context_bonus_sql = (
      f"CASE"
      f"  WHEN trait_context = '{query_context}'"
      f"  THEN {max_context_boost * context_confidence:.4f}"
      f"  WHEN trait_context = 'general'"
      f"  THEN {general_context_boost * context_confidence:.4f}"
      f"  ELSE 0"
      f" END"
  )
  ```
- **变更要点**:
  1. 去掉 `memory_type = 'trait' AND` 条件
  2. 将硬编码 `0.10` 替换为变量 `max_context_boost`
  3. 将硬编码 `0.07` 替换为变量 `general_context_boost`
- **参数传递**: `scored_search()` 需要获取 ContextService 的参数。有两种方案：
  - **方案 A（推荐）**: 直接在 `scored_search()` 开头从参数中读取，或使用默认值：
    ```python
    from neuromem.services.context import ContextService
    max_context_boost = ContextService.MAX_CONTEXT_BOOST
    general_context_boost = ContextService.GENERAL_CONTEXT_BOOST
    ```
  - 方案 B: 通过 `scored_search()` 的新参数传入（不推荐，改动面大）
- **GOTCHA**: `query_context` 来自用户输入路径（`_core.py` 传入），需确保 SQL 注入安全。当前代码用 `_VALID_CONTEXTS` 白名单验证，确保此检查保留。
- **VALIDATE**: `uv run python -c "from neuromem.services.search import SearchService; print('ok')"`

### Task 6: CREATE `scripts/backfill_context.py` — 历史 context 回填脚本

- **IMPLEMENT**: 创建独立的一次性回填脚本
- **核心逻辑**:
  ```python
  """Backfill trait_context for existing fact/episodic memories.

  Usage:
      uv run python scripts/backfill_context.py --database-url DATABASE_URL --embedding-api-key API_KEY [--force]
  """
  import argparse
  import asyncio
  import logging
  from neuromem.services.context import ContextService, cosine_similarity

  async def main():
      # 1. 解析参数
      # 2. 连接数据库
      # 3. 初始化 EmbeddingProvider + ContextService
      # 4. await ctx_service.ensure_prototypes()
      # 5. 批量查询 memories (WHERE memory_type IN ('fact', 'episodic') AND (trait_context IS NULL OR :force))
      # 6. 对每条记忆: 与 4 个 prototype 计算余弦相似度 -> 取 best -> margin >= THRESHOLD ? best : "general"
      # 7. 批量 UPDATE (每 100 条一批)
      # 8. 输出统计
  ```
- **关键细节**:
  - embedding 向量从数据库 `SELECT id, embedding FROM memories` 读取，**不需要**调用 embedding API
  - prototype 向量从 `ctx_service._prototypes` 获取（需要一次 `embed_batch(120)` 调用初始化）
  - 余弦相似度使用 `context.py` 中已有的 `cosine_similarity()` 函数
  - 使用 `ContextService.MARGIN_THRESHOLD` 作为阈值
  - `--force` 参数：覆盖已标注的记忆（默认只处理 `trait_context IS NULL`）
  - 分批处理：每 100 条 fetch + 每 100 条 UPDATE commit
  - 使用 `SiliconFlowEmbedding` 作为默认 embedding provider（需要 API key）
- **PATTERN**: 参考 `scripts/run_migration.py` 的命令行参数和数据库连接模式
- **IMPORTS**: `argparse, asyncio, logging, sqlalchemy (create_async_engine, text), neuromem.services.context, neuromem.providers.embedding`
- **GOTCHA**: embedding 列在 PostgreSQL 中是 pgvector 类型，SELECT 出来是字符串格式 `[0.1,0.2,...]`，需要解析为 `list[float]`
- **VALIDATE**: `uv run python scripts/backfill_context.py --help`

### Task 7: CREATE `scripts/eval_context_params.py` — 参数 A/B 评估脚本

- **IMPLEMENT**: 创建评估脚本，对比 3 组参数的 MRR
- **核心逻辑**:
  ```python
  """Evaluate context parameter combinations using MRR metric.

  Usage:
      uv run python scripts/eval_context_params.py --database-url DATABASE_URL --user-id USER_ID --dataset DATASET_JSON
  """
  # 1. 加载评估数据集 JSON:
  #    [{"query": "...", "expected_top3": ["memory_id_1", "memory_id_2", "memory_id_3"]}, ...]
  # 2. 对每组参数 (baseline/medium/aggressive):
  #    a. 临时修改 ContextService 类属性
  #    b. 对每个查询执行 nm.recall()
  #    c. 计算 MRR@3 和 MRR@5
  # 3. 输出对比表
  ```
- **参数组定义**:
  ```python
  PARAM_SETS = {
      "baseline":   {"MARGIN_THRESHOLD": 0.05, "MAX_CONTEXT_BOOST": 0.10, "GENERAL_CONTEXT_BOOST": 0.07},
      "medium":     {"MARGIN_THRESHOLD": 0.03, "MAX_CONTEXT_BOOST": 0.15, "GENERAL_CONTEXT_BOOST": 0.10},
      "aggressive": {"MARGIN_THRESHOLD": 0.02, "MAX_CONTEXT_BOOST": 0.20, "GENERAL_CONTEXT_BOOST": 0.14},
  }
  ```
- **MRR 计算**:
  ```python
  def mrr_at_k(results: list[str], expected: list[str], k: int) -> float:
      for i, rid in enumerate(results[:k]):
          if rid in expected:
              return 1.0 / (i + 1)
      return 0.0
  ```
- **PATTERN**: 参考 `scripts/reextract_eval.py` 的评估脚本模式
- **VALIDATE**: `uv run python scripts/eval_context_params.py --help`

### Task 8: UPDATE `neuromem/services/context.py` — 更新参数常量（根据 P0 结果）

- **IMPLEMENT**: 根据 Task 7 评估脚本的运行结果，更新 ContextService 的参数常量
- **位置**: L180-183
- **当前值**:
  ```python
  MARGIN_THRESHOLD = 0.05
  MAX_CONTEXT_BOOST = 0.10
  GENERAL_CONTEXT_BOOST = 0.07
  ```
- **预期更新**（以 medium 组为例，实际根据 MRR 结果决定）:
  ```python
  MARGIN_THRESHOLD = 0.03
  MAX_CONTEXT_BOOST = 0.15
  GENERAL_CONTEXT_BOOST = 0.10
  ```
- **GOTCHA**: 如果三组 MRR 无显著差异，保留当前值并在注释中记录结论
- **VALIDATE**: `uv run python -c "from neuromem.services.context import ContextService; print(f'MARGIN={ContextService.MARGIN_THRESHOLD}, BOOST={ContextService.MAX_CONTEXT_BOOST}')"`

### Task 9: UPDATE `tests/test_recall_context_match.py` — 扩展测试覆盖 fact/episodic

- **IMPLEMENT**: 修改现有测试以验证 fact/episodic 也能获得 context boost
- **具体变更**:
  1. 修改 `_insert_fact()` helper，增加 `trait_context` 参数：
     ```python
     async def _insert_fact(
         db_session, mock_embedding, *,
         user_id="ctx_user", content=None, trait_context=None,
     ) -> str:
         # ...创建 Memory 后...
         if trait_context:
             await db_session.execute(
                 text("UPDATE memories SET trait_context = :ctx WHERE id = :mid"),
                 {"ctx": trait_context, "mid": str(record.id)},
             )
             await db_session.commit()
         return str(record.id)
     ```
  2. 新增 `_insert_episode()` helper（类似 `_insert_fact`，memory_type="episodic"）
  3. 修改 `test_fact_no_context_boost` (CM-4) → 改为 `test_fact_with_context_gets_boost`：
     - 插入两个 fact，一个 trait_context="work"，一个 trait_context="personal"
     - 使用 `query_context="work", context_confidence=0.8` 查询
     - 断言 work fact 的 score > personal fact 的 score
  4. 新增 `test_episode_with_context_gets_boost`：类似上面，但用 episodic
  5. 新增 `test_null_context_no_penalty`：
     - 插入一个 trait_context=NULL 的 fact
     - 验证 context_match=0（不惩罚）
- **PATTERN**: 遵循现有 helper 函数 + pytest.mark.asyncio 的风格
- **VALIDATE**: `cd D:/CODE/NeuroMem && uv run pytest tests/test_recall_context_match.py -v`

### Task 10: UPDATE `tests/test_memory_extraction.py` — 新增 context 标注测试

- **IMPLEMENT**: 在现有 memory_extraction 测试文件中新增 context 相关测试
- **先读取** `tests/test_memory_extraction.py` 了解现有结构
- **新增测试用例**:
  1. `test_extraction_prompt_contains_context_field`:
     - 构造 MemoryExtractionService 实例
     - 调用 `_build_zh_prompt()` 和 `_build_en_prompt()`
     - 断言输出包含 "context" 字段说明
  2. `test_store_fact_writes_trait_context`:
     - Mock LLM 返回包含 `"context": "work"` 的 fact
     - 调用 `_store_facts()`
     - 验证 Memory 对象的 `trait_context == "work"`
  3. `test_store_fact_invalid_context_fallback`:
     - Mock LLM 返回 `"context": "invalid_value"` 的 fact
     - 调用 `_store_facts()`
     - 验证 Memory 对象的 `trait_context == "general"`
  4. `test_store_fact_missing_context_fallback`:
     - Mock LLM 返回不含 `context` 字段的 fact
     - 调用 `_store_facts()`
     - 验证 Memory 对象的 `trait_context == "general"`
- **PATTERN**: 参考 `tests/test_memory_extraction.py` 现有测试的 fixture 和 mock 用法
- **VALIDATE**: `cd D:/CODE/NeuroMem && uv run pytest tests/test_memory_extraction.py -v -k context`

---

## 测试策略

### 单元测试

1. **Prompt 内容测试**: 验证 `_build_zh_prompt()` 和 `_build_en_prompt()` 输出包含 context 字段说明
2. **Context 验证逻辑测试**: 验证无效/缺失 context 降级为 "general"
3. **ContextService 参数引用测试**: 验证 `search.py` 使用 ContextService 的参数而非硬编码

### 集成测试

1. **Context Boost 全类型测试**: fact/episodic/trait 都能获得 context bonus
2. **NULL context 不惩罚测试**: trait_context IS NULL 的记忆 context_match=0
3. **排序效果测试**: 同 vector_score 的记忆，context 匹配的排在前面

### 边缘情况

1. LLM 返回 context 为空字符串 → 降级为 "general"
2. LLM 返回 context 大小写不一致（如 "Work"）→ 需决定是否做 `.lower()` 转换
3. query_context="general" 时不应用 context bonus（已有逻辑处理）
4. context_confidence=0 时不应用 context bonus（已有逻辑处理）

---

## 验证命令

### 级别 1: 语法检查

```bash
cd D:/CODE/NeuroMem
uv run python -c "from neuromem.services.memory_extraction import MemoryExtractionService; print('ok')"
uv run python -c "from neuromem.services.search import SearchService; print('ok')"
uv run python -c "from neuromem.services.context import ContextService; print('ok')"
```

### 级别 2: 单元测试

```bash
cd D:/CODE/NeuroMem
uv run pytest tests/test_context_inference.py -v
uv run pytest tests/test_memory_extraction.py -v -k context
```

### 级别 3: 集成测试

```bash
cd D:/CODE/NeuroMem
uv run pytest tests/test_recall_context_match.py -v
uv run pytest tests/test_recall_context_e2e.py -v
```

### 级别 4: 全量回归

```bash
cd D:/CODE/NeuroMem
uv run pytest tests/ -v --timeout=120
```

### 级别 5: 脚本验证

```bash
cd D:/CODE/NeuroMem
uv run python scripts/backfill_context.py --help
uv run python scripts/eval_context_params.py --help
```

---

## 验收标准

- [ ] `_build_zh_prompt()` 和 `_build_en_prompt()` 包含 context 字段说明
- [ ] `_store_facts()` 和 `_store_episodes()` 将 context 写入 `trait_context` 列
- [ ] 无效/缺失 context 降级为 "general"
- [ ] `search.py` 的 context_bonus_sql 对所有 memory_type 生效（不仅限 trait）
- [ ] `search.py` 的 boost 值引用 ContextService 参数，不硬编码
- [ ] 回填脚本可正确运行并更新历史记忆的 trait_context
- [ ] 评估脚本可计算 MRR 并输出对比表
- [ ] 所有现有测试通过，无回归
- [ ] 新增 context 相关测试覆盖正向/降级/边缘情况
- [ ] NULL trait_context 的记忆不受惩罚（context_match=0）

---

## 完成检查清单

- [ ] Task 1-2: Extraction prompt 增加 context 字段（中/英双语）
- [ ] Task 3-4: `_store_facts()` 和 `_store_episodes()` 写入 trait_context
- [ ] Task 5: context_bonus_sql 扩展到全类型 + 引用参数
- [ ] Task 6: 回填脚本创建并可运行
- [ ] Task 7: 评估脚本创建并可运行
- [ ] Task 8: 参数常量更新（根据评估结果）
- [ ] Task 9-10: 测试扩展和新增
- [ ] 全量测试通过

---

## 备注

### 设计决策

1. **复用 `trait_context` 列而非新增列**: 虽然列名含 `trait_` 前缀可能有语义混淆，但该列已有索引且无 DDL 变更需求，是最低成本方案。在 Memory model 注释中说明即可。

2. **ContextService 参数通过类属性引用**: `search.py` 直接 `from neuromem.services.context import ContextService` 然后读取 `ContextService.MAX_CONTEXT_BOOST`，避免修改 `scored_search()` 的签名。

3. **context 标注在 prompt 中标记为"必填"**: 这比标为"可选"能得到更高的标注覆盖率。LLM 偶尔仍会遗漏，代码层的 `fact.get("context", "general")` 提供降级保障。

4. **评估脚本与回填脚本分离**: 评估脚本在现有数据上运行（不修改数据），回填脚本修改数据。两者用途不同，不应合并。

5. **context 标签值使用小写**: 与 ContextService 中 prototype 的 key 保持一致（`"work"` 而非 `"Work"`）。prompt 中明确使用小写值。

### 风险提醒

- `query_context` 拼入 SQL 的安全性：依赖 `_VALID_CONTEXTS` 白名单验证（L349-351），**不可删除此检查**
- 评估脚本需要真实数据库访问，不适合在 CI 中运行
- 回填脚本的 prototype 初始化需要一次 embedding API 调用（120 句），确保 API key 可用
