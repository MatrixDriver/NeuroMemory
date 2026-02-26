---
name: session-memory-management
overview: 实现 neuromem Session 记忆管理系统，包括内部自动 Session 管理、双层记忆模型（短期内存 + 长期 Qdrant+Neo4j）、指代消解机制和 Session 整合功能。
todos:
  - id: session-infra
    content: "阶段 1: 创建 Session 基础设施（session_manager.py, config.py 更新, 数据结构定义）"
    status: pending
  - id: coreference
    content: "阶段 2: 实现指代消解模块（coreference.py - 规则匹配 + LLM 消解）"
    status: pending
  - id: consolidator
    content: "阶段 2: 实现 Session 整合器（consolidator.py - 语义分组 + 消解 + 存储）"
    status: pending
  - id: brain-integration
    content: "阶段 3: 集成 Session 到 PrivateBrain（重构 process(), 添加 end_session(), 更新返回格式）"
    status: pending
  - id: http-api
    content: "阶段 4: 更新 HTTP API（添加 /end-session 和 /session-status 端点，更新返回格式）"
    status: pending
  - id: mcp-tools
    content: "阶段 4: 更新 MCP Tools（添加 end_session 和 get_session_status tools）"
    status: pending
  - id: tests
    content: "阶段 5: 编写测试（单元测试、集成测试、端到端测试）"
    status: pending
isProject: false
---

# 功能：Session 记忆管理系统

基于 [docs/SESSION_MEMORY_DESIGN.md](../SESSION_MEMORY_DESIGN.md) 设计文档，实现 neuromem 的 Session 记忆管理功能。

## 功能描述

实现内部自动 Session 管理系统，为 neuromem 提供双层记忆架构：
- **短期记忆**：Session 内的用户输入原始文本，存储在内存中，用于指代消解
- **长期记忆**：跨 Session 的知识，存储在 Qdrant + Neo4j 中，用于语义检索和图谱查询

核心特性：
1. **用户无感知的 Session 管理**：系统内部自动创建、维护和结束 Session
2. **指代消解**：检索时使用规则匹配快速消解，整合时使用 LLM 准确消解
3. **自动整合**：Session 超时或显式结束时，自动将短期记忆整合为长期记忆
4. **隐私过滤**：整合时对每条记忆进行隐私分类，只存储 PRIVATE 数据

## 用户故事

作为 neuromem 的用户
我想要系统自动管理我的对话 Session
以便我无需关心底层细节，只需调用 `process_memory(input, user_id)` 即可

作为调用方应用（如 DIFY）
我想要获取消解后的查询和长期记忆检索结果
以便我能够理解系统如何理解用户意图，并将相关记忆注入到 LLM prompt 中

## 问题陈述

当前架构存在以下问题：
1. 无法处理跨轮次的指代消解（如"这个"、"她"等代词）
2. 每次输入都立即存储，无法利用对话上下文进行语义分组和合并
3. 返回格式不够直观（vector_chunks 暴露实现细节）
4. 缺少 Session 概念，无法区分短期上下文和长期知识

## 解决方案陈述

实现内部自动 Session 管理系统：
- 用户调用 `process_memory()` 时，系统自动获取或创建 Session
- 检索时使用最近 3-5 条短期事件进行规则匹配消解
- Session 超时（默认 30 分钟）或显式调用 `end_session()` 时，触发整合流程
- 整合时使用 LLM 进行语义分组、指代消解和合并
- 整合后的记忆经过隐私过滤，只存储 PRIVATE 数据到长期记忆

## 功能元数据

**功能类型**：新功能（架构升级）
**估计复杂度**：高
**主要受影响的系统**：
- `private_brain.py` - 核心处理逻辑
- `http_server.py` - REST API 端点
- `mcp_server.py` - MCP Tools
- `config.py` - 配置管理
**依赖项**：
- `asyncio` - 异步 Session 管理
- `dataclasses` - 数据结构定义
- `enum` - Session 状态枚举
- `langchain-openai` - LLM 调用（指代消解）
- 现有 `privacy_filter.py` - 隐私分类
- 现有 `mem0` - 长期记忆存储

---

## 上下文参考

### 相关代码库文件 重要：在实施之前必须阅读这些文件！

- `docs/SESSION_MEMORY_DESIGN.md` (全文) - **必须完整阅读**：详细的设计文档，包含所有数据结构、API 设计和实现细节
- `private_brain.py` (第 199-458 行) - 原因：核心处理逻辑，需要集成 Session 管理
- `privacy_filter.py` (全文) - 原因：隐私分类逻辑，整合时需要调用
- `config.py` (全文) - 原因：配置管理，需要添加 Session 相关配置
- `http_server.py` (第 91-180 行) - 原因：REST API 端点，需要添加新端点
- `mcp_server.py` (第 41-168 行) - 原因：MCP Tools 定义，需要添加新 tools
- `private_brain.py` (第 41-63 行) - 原因：数据结构定义模式（RetrievalResult, DebugInfo）
- `tests/test_cognitive.py` (全文) - 原因：测试模式示例，需要参考编写新测试

### 要创建的新文件

- `session_manager.py` - Session 生命周期管理器
- `coreference.py` - 指代消解模块（规则匹配 + LLM 消解）
- `consolidator.py` - Session 整合器（语义分组 + 消解 + 存储）

### 相关文档 在实施之前应该阅读这些！

- [docs/SESSION_MEMORY_DESIGN.md](../SESSION_MEMORY_DESIGN.md) - **完整文档**
  - 特定部分：第 2-4 章（架构设计、数据结构、生命周期管理）
  - 原因：核心设计文档，包含所有实现细节
- [docs/ARCHITECTURE.md](../ARCHITECTURE.md)
  - 特定部分：2.3.1 隐私过滤器设计
  - 原因：了解隐私过滤的实现方式
- [Python asyncio 文档](https://docs.python.org/3/library/asyncio.html)
  - 特定部分：Task 和 Lock 的使用
  - 原因：Session 管理器需要异步操作和并发控制

### 要遵循的模式

**命名约定**：
- 类名使用 PascalCase：`SessionManager`, `CoreferenceResolver`
- 函数名使用 snake_case：`get_or_create_session`, `resolve_query`
- 常量使用 UPPER_SNAKE_CASE：`SESSION_TIMEOUT_SECONDS`
- 私有方法使用单下划线前缀：`_check_timeouts`, `_consolidate_session`

**错误处理**：
- 采用静默降级策略，不抛出异常影响主流程
- 使用 logger 记录错误：`logger.error(f"错误信息: {e}")`
- 参考：`private_brain.py` 第 387-389 行

**日志记录模式**：
- 使用模块级 logger：`logger = logging.getLogger("neuro_memory.session")`
- 关键操作记录 INFO：`logger.info("Session 创建成功")`
- 错误记录 ERROR：`logger.error("Session 整合失败")`
- 参考：`private_brain.py` 第 20-21 行

**数据结构模式**：
- 使用 `@dataclass` 定义数据结构
- 使用 `field(default_factory=list)` 处理可变默认值
- 提供 `to_dict()` 方法用于 JSON 序列化
- 参考：`private_brain.py` 第 41-62 行

**单例模式**：
- 使用模块级变量存储实例：`_instance: ClassType | None = None`
- 提供 `get_instance()` 函数获取单例
- 参考：`privacy_filter.py` 第 112-121 行

**异步处理模式**：
- 使用 `ThreadPoolExecutor` 处理同步阻塞操作（如 LLM 调用）
- 使用 `asyncio.Lock()` 保护共享资源
- 参考：`private_brain.py` 第 211-214 行

---

## 实施计划

### 阶段 1：Session 基础设施

**目标**：实现 Session 生命周期管理，不破坏现有功能

**任务**：
1. 创建 `session_manager.py` - Session 管理器
2. 更新 `config.py` - 添加 Session 相关配置
3. 创建基础数据结构（Event, Session, SessionStatus）

### 阶段 2：指代消解与整合

**目标**：实现指代消解和 Session 整合逻辑

**任务**：
1. 创建 `coreference.py` - 指代消解模块
2. 创建 `consolidator.py` - Session 整合器
3. 编写单元测试验证消解规则

### 阶段 3：核心集成

**目标**：将 Session 和消解集成到 PrivateBrain

**任务**：
1. 重构 `private_brain.py` 的 `process()` 方法
2. 添加 `end_session()` 方法
3. 更新返回格式

### 阶段 4：API 更新

**目标**：暴露新接口给调用方

**任务**：
1. 更新 `http_server.py` - 添加新端点和更新返回格式
2. 更新 `mcp_server.py` - 添加新 tools

### 阶段 5：测试和文档

**目标**：确保功能正确性和可维护性

**任务**：
1. 编写单元测试和集成测试
2. 更新相关文档

---

## 逐步任务

### CREATE session_manager.py

- **IMPLEMENT**：创建 SessionManager 类，实现以下方法：
  - `__init__()`: 初始化内部字典 `_sessions: dict[str, Session]` 和 `asyncio.Lock()`
  - `get_or_create_session(user_id: str) -> Session`: 获取或创建用户 Session
  - `add_event(user_id: str, event: Event) -> None`: 向 Session 添加事件
  - `get_session_events(user_id: str, limit: int) -> list[Event]`: 获取最近事件
  - `end_session(user_id: str) -> SessionSummary`: 结束 Session（异步触发整合）
  - `_check_timeouts() -> None`: 定期检查超时 Session（后台任务）
  - `_consolidate_session(session: Session) -> None`: 整合 Session 到长期记忆
- **PATTERN**：参考 `private_brain.py` 第 199-215 行的类结构
- **IMPORTS**：`asyncio`, `datetime`, `logging`, `dataclasses`, `enum`
- **GOTCHA**：
  - 使用 `asyncio.Lock()` 保护 `_sessions` 字典的并发访问
  - Session 超时检查需要在后台任务中运行，使用 `asyncio.create_task()`
  - 空 Session（无事件）超时时直接清理，跳过整合
- **VALIDATE**：`python -c "from session_manager import SessionManager; print('OK')"`

### CREATE coreference.py

- **IMPLEMENT**：创建 CoreferenceResolver 类：
  - `resolve_query(query: str, context_events: list[Event]) -> str`: 检索时消解（规则匹配）
    - 检测代词："这个"、"她"、"他"、"它"
    - 从最近事件中提取名词/人名进行替换
    - 如果无法消解，返回原始查询
  - `resolve_events(events: list[Event]) -> list[str]`: 整合时消解（LLM）
    - 使用 LLM 进行语义分组
    - 消解每组中的代词
    - 合并为完整陈述
    - 返回整合后的记忆列表
- **PATTERN**：参考 `privacy_filter.py` 第 22-96 行的 LLM 调用模式
- **IMPORTS**：`langchain_openai.ChatOpenAI`, `json`, `re`, `logging`
- **GOTCHA**：
  - 规则匹配要处理中文标点符号
  - LLM prompt 要明确要求 JSON 格式返回
  - 消解失败时返回空列表或跳过该条记忆
- **VALIDATE**：`python -c "from coreference import CoreferenceResolver; r = CoreferenceResolver(); print(r.resolve_query('这个', []))"`

### CREATE consolidator.py

- **IMPLEMENT**：创建 SessionConsolidator 类：
  - `__init__()`: 接收 CoreferenceResolver, PrivacyFilter, Memory 实例
  - `consolidate(session: Session) -> ConsolidationResult`: 整合 Session
    - 跳过空 Session
    - 调用 `coreference.resolve_events()` 进行消解
    - 对每条整合后的记忆进行隐私过滤
    - 只存储 PRIVATE 数据到长期记忆（使用 `memory.add()`）
    - 返回整合统计
- **PATTERN**：参考 `private_brain.py` 第 424-443 行的后台整合逻辑
- **IMPORTS**：`logging`, `dataclasses`
- **GOTCHA**：
  - 整合是异步操作，不阻塞 Session 结束
  - 使用 ThreadPoolExecutor 执行同步的 LLM 调用
- **VALIDATE**：`python -c "from consolidator import SessionConsolidator; print('OK')"`

### UPDATE config.py

- **IMPLEMENT**：在文件末尾添加 Session 管理配置：
  ```python
  # Session 管理配置
  SESSION_TIMEOUT_SECONDS = int(os.getenv("SESSION_TIMEOUT", 30 * 60))
  SESSION_MAX_DURATION_SECONDS = int(os.getenv("SESSION_MAX_DURATION", 24 * 60 * 60))
  SESSION_MAX_EVENTS = int(os.getenv("SESSION_MAX_EVENTS", 100))
  SESSION_CHECK_INTERVAL_SECONDS = 60
  COREFERENCE_CONTEXT_SIZE = int(os.getenv("COREFERENCE_CONTEXT_SIZE", 5))
  ```
- **PATTERN**：参考 `config.py` 第 192-196 行的配置格式
- **IMPORTS**：无需新增（已有 `os`）
- **GOTCHA**：确保环境变量转换为整数
- **VALIDATE**：`python -c "from config import SESSION_TIMEOUT_SECONDS; print(SESSION_TIMEOUT_SECONDS)"`

### UPDATE private_brain.py

- **IMPLEMENT**：
  1. 在 `__init__()` 中初始化 SessionManager 和 CoreferenceResolver
  2. 重构 `process()` 方法：
     - 获取或创建 Session
     - 获取最近事件进行指代消解
     - 使用消解后的查询检索长期记忆
     - 创建 Event 并添加到 Session
     - 返回格式（memories/relations/resolved_query）
  3. 添加 `end_session(user_id: str) -> dict` 方法
  4. 更新 `_retrieve()` 返回格式
- **PATTERN**：参考 `private_brain.py` 第 217-240 行的 process 方法
- **IMPORTS**：`session_manager`, `coreference`, `datetime`, `uuid`
- **GOTCHA**：
  - Session 管理是同步的，但整合是异步的
  - 返回格式要兼容 v2（向后兼容）或直接升级到 v3
  - 短期记忆不返回给调用方
- **VALIDATE**：`python -c "from private_brain import PrivateBrain; b = PrivateBrain(); print(b.process('测试', 'user_001'))"`

### UPDATE http_server.py

- **IMPLEMENT**：
  1. 添加 `POST /end-session` 端点
  2. 添加 `GET /session-status/{user_id}` 端点
  3. 更新 `POST /process` 返回格式为 v3
- **PATTERN**：参考 `http_server.py` 第 91-121 行的端点定义
- **IMPORTS**：无需新增
- **GOTCHA**：
  - 新端点需要添加请求/响应模型（Pydantic）
  - 返回格式要保持向后兼容或明确版本
- **VALIDATE**：启动服务器后测试端点：`curl http://localhost:8765/health`

### UPDATE mcp_server.py

- **IMPLEMENT**：
  1. 在 `list_tools()` 中添加 `end_session` 和 `get_session_status` tools
  2. 在 `call_tool()` 中处理新 tools 的调用
- **PATTERN**：参考 `mcp_server.py` 第 41-114 行的 tool 定义
- **IMPORTS**：无需新增
- **GOTCHA**：Tool 的 inputSchema 要与实际参数匹配
- **VALIDATE**：`python -c "from mcp_server import server; print('OK')"`

### CREATE tests/test_session.py

- **IMPLEMENT**：创建 Session 管理相关测试：
  - `TestSessionManager`: Session 生命周期测试
  - `TestCoreferenceResolver`: 指代消解测试（规则 + LLM）
  - `TestSessionConsolidator`: Session 整合测试
  - `TestSessionIntegration`: 端到端集成测试
- **PATTERN**：参考 `tests/test_cognitive.py` 的测试结构
- **IMPORTS**：`pytest`, `time`
- **GOTCHA**：
  - LLM 相关测试使用 `@pytest.mark.slow` 标记
  - 使用 `unique_user_id` fixture 避免测试间数据污染
- **VALIDATE**：`pytest tests/test_session.py -v`

---

## 测试策略

### 单元测试

**SessionManager 测试**：
- Session 创建和获取
- 事件添加和检索
- Session 超时检查
- 空 Session 处理

**CoreferenceResolver 测试**：
- 规则匹配消解（"这个"、"她"等）
- LLM 消解（需要 @pytest.mark.slow）
- 消解失败处理

**SessionConsolidator 测试**：
- 空 Session 跳过
- 整合流程（需要 @pytest.mark.slow）
- 隐私过滤集成

### 集成测试

**端到端流程测试**：
- 多轮对话的指代消解
- Session 超时自动整合
- 显式结束 Session
- 跨 Session 查询

### 边缘情况

- 空 Session 超时
- 最大事件数限制
- 最大时长限制
- 并发访问 Session
- LLM 调用失败
- 整合失败处理

---

## 验证命令

### 级别 1：语法和样式

```bash
# Python 语法检查
python -m py_compile session_manager.py coreference.py consolidator.py

# 导入检查
python -c "from session_manager import SessionManager; from coreference import CoreferenceResolver; from consolidator import SessionConsolidator; print('Imports OK')"
```

### 级别 2：单元测试

```bash
# 运行 Session 相关测试（跳过慢速测试）
pytest tests/test_session.py -m "not slow" -v

# 运行所有 Session 测试（包含 LLM 调用）
pytest tests/test_session.py -v -s
```

### 级别 3：集成测试

```bash
# 运行端到端测试
pytest tests/test_session.py::TestSessionIntegration -v -s

# 运行所有测试（确保无回归）
pytest tests/ -v
```

### 级别 4：手动验证

```bash
# 启动 HTTP 服务器
uvicorn http_server:app --host 0.0.0.0 --port 8765 --reload

# 测试 process_memory（新终端）
curl -X POST http://localhost:8765/process \
  -H "Content-Type: application/json" \
  -d '{"input": "我叫小朱", "user_id": "test_user"}'

# 测试 end_session
curl -X POST http://localhost:8765/end-session \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user"}'

# 测试 session-status
curl http://localhost:8765/session-status/test_user
```

### 级别 5：MCP 服务器验证（可选）

```bash
# 测试 MCP Server（需要配置 Cursor/Claude Desktop）
python mcp_server.py
```

---

## 验收标准

- [ ] SessionManager 正确创建、管理和结束 Session
- [ ] 指代消解在检索时正确工作（规则匹配）
- [ ] 指代消解在整合时正确工作（LLM）
- [ ] Session 超时自动触发整合
- [ ] 显式 `end_session()` 正确触发整合
- [ ] 整合后的记忆正确存储到长期记忆
- [ ] 隐私过滤在整合时正确工作
- [ ] `process_memory()` 返回格式（memories/relations/resolved_query）
- [ ] HTTP API 新端点正常工作
- [ ] MCP Tools 新 tools 正常工作
- [ ] 所有单元测试通过
- [ ] 所有集成测试通过
- [ ] 无代码检查错误
- [ ] 现有功能无回归

---

## 完成检查清单

- [ ] 所有任务按顺序完成
- [ ] 每个任务验证立即通过
- [ ] 所有验证命令成功执行
- [ ] 完整测试套件通过（单元 + 集成）
- [ ] 无代码检查或类型检查错误
- [ ] 手动测试确认功能有效
- [ ] 所有验收标准均满足
- [ ] 代码已审查质量和可维护性

---

## 备注

**设计决策**：
1. Session 管理采用同步接口，但整合是异步的（使用 ThreadPoolExecutor）
2. 短期记忆存储在内存中，重启后丢失（符合设计文档）
3. 返回格式直接升级到 v3，不保持向后兼容（简化实现）
4. 指代消解失败时，检索使用原始查询，整合跳过该条记忆

**性能考虑**：
- Session 超时检查每分钟运行一次，避免频繁检查
- 整合操作在后台线程池执行，不阻塞用户请求
- LLM 调用使用现有的同步接口，后续可优化为异步

**后续优化**：
- 短期存储可升级为 Redis（生产环境）
- 指代消解规则可扩展（时间词、地点词等）
- 可添加摘要策略（Session 结束时生成对话摘要）
