# 未实现特性与开发顺序建议

> 基于对 `docs/`、`docs/feature-plans/` 及代码库的梳理；文档日期可能与实现有滞后，以代码为准。

---

## 一、已实现（文档可能仍标「规划」）

| 特性 | 文档位置 | 实现位置 |
|------|----------|----------|
| REST API | API.md 已标 ✅ | http_server.py: REST API 端点 |
| Session 记忆管理 v3 | SESSION_MEMORY_DESIGN 标「待实现」 | session_manager, consolidator, coreference；private_brain、/end-session、/session-status |
| 性能优化-异步整合 | PERFORMANCE_OPTIMIZATION 标已完成 | v3 整合在 Session 结束路径；PERFORMANCE 中的「cognitive_process」已由 process/consolidation 替代 |

---

## 二、未实现特性清单

### 2.1 接入层（API / SDK / CLI）

| 特性 | 文档 | 说明 |
|------|------|------|
| **Python SDK（NeuroMemory 类）** | API.md `[🚧 开发中]`，COMPONENTS、ARCHITECTURE、GETTING_STARTED | 目标：`from neuromemory import NeuroMemory`；`add/search/ask/get_graph`，支持 `metadata`、`config`。底层 PrivateBrain 已有对应能力，主要是封装 + 包结构。 |
| **CLI 工具** | API.md `[📋 规划]`，ARCHITECTURE | 目标：`neuromemory add/search/ask/graph export/graph visualize/status`。需在 pyproject 增加 CLI 入口（如 Click/Typer）。 |

### 2.2 可观测性（OBSERVABILITY.md `[📋 规划]`）

| 子项 | 说明 |
|------|------|
| **Metrics (Prometheus)** | 业务：memory_add_total、search_duration_seconds、reasoning_duration_seconds；系统：neo4j_nodes_total、qdrant_vectors_total、llm_tokens_total。 |
| **Tracing (Jaeger)** | cognitive_process / process、hybrid_retrieval、llm_reasoning、memory_consolidation 等 Span。 |
| **结构化日志 (trace_id/span_id)** | 当前为普通 logging；需统一格式、trace_id/span_id 注入。 |

### 2.3 部署与生产（DEPLOYMENT.md）

| 子项 | 说明 |
|------|------|
| **生产部署架构** | Load Balancer、API Server 多副本、Neo4j Primary、Qdrant Cluster、Redis、可观测性平台。偏运维/编排，与代码迭代可分开。 |

### 2.4 知识增强（FUTURE_ENHANCEMENTS.md）

| 子项 | 说明 |
|------|------|
| **混合方案 C - 阶段 1：存储时轻量增强** | 在写入前用规则引擎 `extract_implicit_attributes()` 抽隐含属性（如从「弟弟」推「男性」），与主内容一起写入。需接在 consolidator 或 `brain.add` 的调用链。前提：性能优化完成（已满足）；`brain.add` 后台耗时 <5s 为可选目标。 |

### 2.5 架构远期扩展（ARCHITECTURE 5. 未来扩展）

| 特性 | 优先级 | 说明 |
|------|--------|------|
| **情景流 (Episodic)** | P2 | LLM 长窗口作工作记忆，与 Graph/Vector 三层检索。 |
| **LangGraph 复杂编排** | P2 | 多轮检索、并行推理、条件分支、自检循环。 |
| **图谱可视化** | P2 | Web UI 展示知识图谱（如 `neuromemory graph visualize --open-browser`）。 |
| **批量导入** | P2 | 文档批量解析与导入。 |
| **记忆遗忘机制** | P3 | 按访问频率/时间衰减或淘汰。 |
| **多模态记忆** | P3 | 图/音等。 |
| **分布式部署** | P3 | Neo4j 集群、Qdrant 分片。 |

### 2.6 性能（PERFORMANCE_OPTIMIZATION「未来可选」）

| 子项 | 说明 |
|------|------|
| 为 GraphStore 配置更快 LLM | 后台 28s→约 15s，待评估。 |
| mem0 `infer=False` 等 | 降低 LLM 调用，需评估精度。 |
| 批量整合 | 多条一起写入以减 LLM 次数，实现复杂。 |

---

## 三、开发顺序建议

按**依赖关系、价值、实现成本**排序，便于迭代。

### 第一批：接入层补齐（提升易用与调试）

1. **Python SDK（NeuroMemory 类）**  
   - **原因**：ARCHITECTURE 标 P0/「优先实现」；PrivateBrain、REST API 已具备能力，SDK 主要为薄封装 + `neuromemory` 包与 `NeuroMemory` 类。  
   - **产出**：`neuromemory` 包、`NeuroMemory(config).add/search/ask/get_graph`，`metadata` 透传或扩展；可被 CLI 或应用直接复用。

2. **CLI 工具**  
   - **原因**：API.md 已给出命令形态；可用 SDK 或直接调 `get_brain()`/HTTP。若先做 SDK，CLI 可直接基于 SDK，减少重复。  
   - **产出**：`neuromemory add/search/ask/graph export/graph visualize/status`，pyproject 的 `[project.scripts]` 或 `console_scripts`。

### 第二批：可观测性与生产就绪

3. **可观测性 - Metrics 先行**  
   - **原因**：OBSERVABILITY 设计完整；Metrics 对生产排障、容量规划最直接，且不依赖 Tracing。  
   - **产出**：Prometheus 指标（如 `neuromemory_memory_add_total`、`neuromemory_search_duration_seconds` 等），在 `http_server`、`private_brain` 关键路径打点。

4. **可观测性 - Tracing + 结构化日志**  
   - **原因**：与 Metrics 一起构成「观测三支柱」，便于排查延迟与跨组件调用。  
   - **产出**：OpenTelemetry 或 Jaeger 的 Span（process、retrieval、llm、consolidation）；日志带 `trace_id`/`span_id` 等。

5. **生产部署与可观测性落地**  
   - **原因**：DEPLOYMENT 的生产架构依赖 LB、多副本、Redis、可观测性栈。  
   - **产出**：docker-compose/k8s 示例、Prometheus/Grafana/Jaeger 等配置；可与 Metrics/Tracing 同步推进。

### 第三批：知识增强与体验

6. **混合知识增强 - 阶段 1（规则引擎）**  
   - **原因**：FUTURE_ENHANCEMENTS 方案 C 阶段 1 设计细致；性能前提已满足；可先上规则版，再考虑 LLM 版。  
   - **产出**：`extract_implicit_attributes()`，并接入 consolidator 或 `brain.add` 的写入路径；测试「帅帅是男性吗」等检索效果。

### 第四批：架构扩展（按需）

7. **图谱可视化**  
   - 实现 `graph visualize`，或独立 Web 页，读取 `get_user_graph`/`/graph/{user_id}` 展示 nodes/edges。

8. **批量导入**  
   - 文档解析（PDF/TXT 等）→ 分片 → 调用 `add` 或批量接口。

9. **情景流、LangGraph、遗忘、多模态、分布式**  
   - 按 ARCHITECTURE 的 P2/P3 和产品需求排期；依赖与复杂度较高，适合单独规划。

### 说明

- **cognitive_process / format_results / create_brain**：在 COMPONENTS、HOW_IT_WORKS、GETTING_STARTED 中出现，但 `main.py` 为 v2 演示与 `PrivateBrain.process`。`create_chat_llm` 已在 `config`，`cognitive_process` 的职责已由 `process` + 调用方 LLM 承担，不单独列为待实现。
- **SESSION_MEMORY_DESIGN「待实现」**：与现有 session_manager、consolidator、coreference 实现不一致，属文档滞后。
- **feature-plans/session-memory-management 的 todos**：计划中仍为 pending，实现已完成，可更新计划状态。

---

## 四、顺序小结（一图）

```
1. Python SDK (NeuroMemory)     ──┐
2. CLI 工具                      ──┼─ 接入层，可并行或 SDK→CLI
3. Metrics (Prometheus)         ──┐
4. Tracing + 结构化日志         ──┼─ 可观测性，Metrics 可先
5. 生产部署与可观测性落地       ──┘
6. 混合知识增强 - 规则引擎      ─── 知识增强
7. 图谱可视化 / 批量导入 / ...  ─── 按需、P2/P3
```

---

## 五、相关文档

- [API 接口设计](API.md)  
- [可观测性设计](OBSERVABILITY.md)  
- [未来增强（方案 C）](FUTURE_ENHANCEMENTS.md)  
- [部署架构](DEPLOYMENT.md)  
- [主架构与未来扩展](ARCHITECTURE.md#5-未来扩展-todo)  
- [特性开发目录与规范](feature-plans/README.md)
