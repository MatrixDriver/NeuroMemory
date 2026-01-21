# 性能优化任务

> 状态：**已完成**  
> 优先级：高  
> 创建日期：2026-01-21  
> 完成日期：2026-01-21

## 问题描述

记忆整合（Memory Consolidation）性能严重不足，每次 `brain.add()` 操作需要 **48-66 秒**，占总处理时间的 **77-85%**。

### 优化前性能统计

```
[性能统计] 总耗时: 62.02s
  - 预处理(身份+消解): 0.00s (0.0%)
  - 意图判断(LLM): 3.77s (6.1%)
  - 混合检索(Vector+Graph): 5.63s (9.1%)
  - 深度推理(LLM): 4.62s (7.5%)
  - 记忆整合(Vector+Graph): 48.00s (77.4%)  ← 性能瓶颈
```

---

## 诊断结论

### 根本原因

通过阅读 mem0 源码和添加细粒度性能监控，确定瓶颈是 **mem0 内部多次 LLM 调用**：

| 调用点 | 源码位置 | 功能 | 平均耗时 |
|--------|----------|------|----------|
| ① | `mem0/memory/main.py:434` | 事实提取 (fact extraction) | ~2s |
| ② | `mem0/memory/main.py:502` | 记忆更新决策 (ADD/UPDATE/DELETE) | ~2s |
| ③ | `mem0/memory/graph_memory.py:201` | 实体提取 (extract entities) | ~4s |
| ④ | `mem0/memory/graph_memory.py:258` | 关系建立 (establish relations) | ~4s |

**每次 `brain.add()` 至少 4-5 次 LLM 调用！**

### 诊断数据

| 指标 | 启用 graph_store | 禁用 graph_store |
|------|-----------------|-----------------|
| 单次 add() | 13.90s | 5.39s |
| LLM 调用次数 | 5 次 | 2 次 |
| LLM 总耗时 | 16s (86%) | 4.5s (84%) |
| Embedding 调用 | 5 次, 2.18s | 1 次, 0.76s |
| Neo4j 操作 | 5 次, 0.37s | - |
| Qdrant 操作 | 0.05s | 0.06s |

**结论**：LLM 调用是主要瓶颈，数据库操作很快。

---

## 已实施优化方案

### 方案 A：异步记忆整合 ✅

将记忆整合改为后台异步任务，用户无需等待：

```python
# main.py 新增模块

from concurrent.futures import ThreadPoolExecutor

# 后台整合线程池
_consolidation_executor = ThreadPoolExecutor(max_workers=2)

def _background_consolidate(brain, texts, user_id):
    """后台执行记忆整合"""
    for text in texts:
        try:
            brain.add(text, user_id=user_id)
        except Exception as e:
            _consolidation_logger.warning(f"记忆保存失败: {e}")

# 在 cognitive_process 中
_consolidation_executor.submit(_background_consolidate, brain, texts, user_id)
return answer  # 立即返回，无需等待
```

### 优化效果

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 用户感知等待时间 | ~38s | **~10s** |
| 后台整合时间 | - | ~28s（不影响用户） |
| 图谱功能 | 完整 | **完整保留** |

### 优化后性能统计

```
[性能统计] 用户感知耗时: 10.24s
  - 预处理(身份+消解): 0.00s (0.0%)
  - 意图判断(LLM): 3.77s (36.8%)
  - 混合检索(Vector+Graph): 1.85s (18.1%)
  - 深度推理(LLM): 4.62s (45.1%)
  - 记忆整合: 异步执行中（约 28s，不阻塞用户）
```

---

## 注意事项

1. **整合延迟生效**：刚存储的记忆需要等后台整合完成才能被检索到（约 20-30 秒）
2. **程序退出**：如果程序在整合完成前退出，未完成的整合任务会丢失
3. **日志查看**：后台整合结果会输出到控制台，格式为 `[时间] INFO - 记忆整合完成: X/Y 条成功, 耗时 Xs`

---

## 未来可选优化

如需进一步降低后台整合时间，可考虑：

| 方案 | 效果 | 状态 |
|------|------|------|
| 为 GraphStore 配置更快的 LLM (gpt-4o-mini/Groq) | 后台耗时 28s -> 15s | 待评估 |
| 使用 `infer=False` 跳过 LLM 事实提取 | 后台耗时进一步降低 | 需评估精度影响 |
| 批量整合（累积多条后一次性写入） | 减少 LLM 调用次数 | 复杂度较高 |
