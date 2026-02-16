# NeuroMemory Evaluation History

本目录记录 NeuroMemory 在各个基准测试上的历史结果，用于追踪性能演进和对比优化效果。

## 目录结构

```
evaluation/history/
├── README.md                       # 本文档
├── index.json                      # 所有测试的索引
├── 2025-02-15_baseline.json        # 基线测试
├── 2025-02-16_perf_opt.json        # 性能优化测试
└── YYYY-MM-DD_<name>.json          # 未来的测试记录
```

## 测试记录格式

每个测试记录文件包含以下信息：

### 基本信息
- `test_id`: 测试唯一标识（日期_名称）
- `test_name`: 测试描述性名称
- `timestamp`: 测试时间戳
- `benchmark`: 基准测试名称（locomo, longmemeval）
- `dataset`: 使用的数据集

### 环境配置
- `neuromemory_commit`: NeuroMemory 代码的 Git commit
- `neuromemory_branch`: Git 分支
- `database`: 数据库配置（类型、版本、隔离方式）
- `embedding`: Embedding 提供商和模型
- `llm`: LLM 提供商和模型
- `judge`: 评测 Judge 模型

### 优化措施
- `optimizations`: 本次测试包含的优化清单

### 性能指标
- `ingest_phase`: Ingest 阶段耗时和速度
- `query_phase`: Query 阶段耗时和速度
- `evaluate_phase`: Evaluate 阶段耗时和速度
- `total_duration`: 总耗时

### 测试结果
- `overall`: 总体指标（F1, BLEU-1, Judge）
- `by_category`: 按问题类别的详细指标
  - Category 1: Multi-hop（多跳推理）
  - Category 2: Temporal（时序记忆）
  - Category 3: Open-domain（开放域）
  - Category 4: Single-hop（单跳）

### 改进对比
- `improvements_vs_baseline`: 相对基线的改进幅度

### 备注
- `key_findings`: 关键发现
- `issues`: 遗留问题
- `notes`: 其他备注

## 如何添加新的测试记录

### 1. 运行测试并收集信息

```bash
# 记录当前 commit
git log -1 --oneline

# 运行测试
python -m evaluation.cli locomo

# 测试完成后查看结果
cat evaluation/results/locomo_results.json
```

### 2. 创建新的测试记录文件

文件命名格式：`YYYY-MM-DD_<short_name>.json`

例如：`2025-02-20_graph_opt.json`

```json
{
  "test_id": "2025-02-20_graph_opt",
  "test_name": "Graph Memory Optimization Test",
  "timestamp": "2025-02-20T10:00:00+08:00",
  "benchmark": "locomo",

  "environment": {
    "neuromemory_commit": "abc1234",
    "neuromemory_branch": "main",
    ...
  },

  "optimizations": [
    "优化措施1",
    "优化措施2"
  ],

  "results": {
    // 从 locomo_results.json 复制
  }
}
```

### 3. 更新索引文件

编辑 `index.json`，添加新记录到 `tests` 数组，并更新 `latest` 和 `best`。

### 4. 使用对比脚本（可选）

```bash
python evaluation/scripts/compare_history.py 2025-02-15_baseline 2025-02-20_graph_opt
```

## 测试结果对比

### 查看所有测试

```bash
cat evaluation/history/index.json | jq '.tests[] | {date, name, judge_score}'
```

### 对比两次测试

```bash
python -c "
import json

with open('evaluation/history/2025-02-15_baseline.json') as f:
    baseline = json.load(f)
with open('evaluation/history/2025-02-16_perf_opt.json') as f:
    current = json.load(f)

print(f'Judge Score: {baseline[\"results\"][\"overall\"][\"judge\"]} -> {current[\"results\"][\"overall\"][\"judge\"]}')
print(f'Improvement: +{(current[\"results\"][\"overall\"][\"judge\"] - baseline[\"results\"][\"overall\"][\"judge\"]) / baseline[\"results\"][\"overall\"][\"judge\"] * 100:.1f}%')
"
```

## 当前测试历史

| 日期 | 测试名称 | Commit | Judge 分数 | 改进 |
|------|---------|--------|-----------|------|
| 2025-02-15 | Baseline | 5c9672d2 | 0.125 | - |
| 2025-02-16 | Perf Opt | e7c0f3d5 | 0.274 | +119% |
| 2025-02-17 | Complete Test | e5066cc5 | 0.431 | +57% |

## 关键里程碑

### 2025-02-15: Baseline
- 首次完整 LoCoMo 评测
- Judge 分数: 0.125
- Ingest 耗时: ~24 小时

### 2025-02-16: Performance Optimization
- 重大性能优化
- Judge 分数: 0.274 (+119%)
- Ingest 耗时: 1 小时 (24倍提升)
- 优化：只对 user 消息提取记忆 + embedding 缓存

### 2025-02-17: Complete Test (历史性突破)
- Judge 分数: 0.431 (+57%)
- 数据完整性保证：所有 Conv 0-9 完整
- Conv 8-9 修复：解决 DeepSeek 402 错误后重新提取
- 详细分析：见 `2025-02-17_complete_test_analysis.md`
- 下一步：时间信息提取 + 混合检索（预期突破 0.55）

## 未来优化方向

基于当前测试结果，以下是值得优化的方向：

1. **Temporal 时序记忆** (当前 0.087)
   - 增强时间信息提取和存储
   - 改进时间推理能力
   - 利用 session timestamp

2. **Multi-hop 推理** (当前 0.305)
   - 优化知识图谱构建
   - 改进多跳推理路径

3. **召回精度**
   - 混合检索策略
   - Metadata 精确过滤

## 注意事项

1. **数据库隔离**: 始终使用独立容器（端口 5433）避免数据丢失
2. **环境一致性**: 保持 embedding 模型、LLM 模型一致以确保可比性
3. **完整记录**: 记录所有优化措施和配置变更
4. **及时更新**: 测试完成后立即创建记录，避免遗忘细节

## 相关文档

- [LoCoMo Benchmark](../datasets/locomo_loader.py)
- [Evaluation Pipeline](../pipelines/locomo.py)
- [配置说明](../.env)
