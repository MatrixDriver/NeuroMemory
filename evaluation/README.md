# neuromem 基准测试

使用 [LoCoMo](https://arxiv.org/abs/2402.09302) (ACL 2024) 和 [LongMemEval](https://arxiv.org/abs/2407.15168) (ICLR 2025) 对 neuromem 的记忆召回能力进行评测。

## 快速开始

### 1. 准备数据

```bash
# LoCoMo - 将 locomo10.json 放入 data/ 目录
cp /path/to/locomo10.json evaluation/data/

# LongMemEval - 从 HuggingFace 下载
# https://huggingface.co/datasets/...
cp /path/to/longmemeval_s_cleaned.json evaluation/data/
```

### 2. 环境变量

```bash
# 数据库
export DATABASE_URL=postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem

# Embedding (SiliconFlow 或 OpenAI)
export EMBEDDING_PROVIDER=siliconflow   # 或 openai
export EMBEDDING_API_KEY=your_key

# LLM - 记忆提取 + 回答生成 (DeepSeek/OpenAI)
export LLM_API_KEY=your_key
export LLM_MODEL=deepseek-chat
export LLM_BASE_URL=https://api.deepseek.com/v1

# LLM Judge (GPT-4o-mini)
export JUDGE_API_KEY=your_openai_key
export JUDGE_MODEL=gpt-4o-mini
```

### 3. 安装评测依赖

```bash
uv pip install -e ".[eval]"
```

### 4. 运行评测

```bash
# 完整运行
make -C evaluation locomo
make -C evaluation longmemeval

# 分阶段运行
python -m evaluation.cli locomo --phase ingest     # 注入记忆
python -m evaluation.cli locomo --phase query      # 问答检索
python -m evaluation.cli locomo --phase evaluate   # 计算指标
```

## 评测流程

### LoCoMo (10 组对话, ~1540 个 QA)

| 阶段 | 说明 |
|------|------|
| **ingest** | 注入 10 组多轮对话，每组 2 个 user_id (speaker_a, speaker_b)。LLM 提取记忆。 |
| **query** | 对每个 QA，从两个 speaker 的记忆中 `recall()`，合并后 LLM 生成回答。 |
| **evaluate** | 计算 Token F1、BLEU-1、LLM Judge (GPT-4o-mini 二元判定)，按 category 汇总。 |

Category:
1. Multi-hop (多跳推理)
2. Temporal (时间相关)
3. Open-domain (开放域)
4. Single-hop (单跳事实)
5. Adversarial (跳过)

### LongMemEval (500 个问题, 115k~1.5M tokens)

| 阶段 | 说明 |
|------|------|
| **ingest** | 每个问题独立 user_id，注入 haystack sessions，LLM 提取记忆。 |
| **query** | `recall()` 检索 + LLM 生成回答，记录召回 session 来源。 |
| **evaluate** | Token F1、BLEU-1、LLM Judge + Recall@10，按 question_type 汇总。 |

## 指标

| 指标 | 说明 |
|------|------|
| **Token F1** | lowercase + 去标点 + set 交集 → precision/recall/F1 |
| **BLEU-1** | unigram precision × brevity penalty |
| **LLM Judge** | GPT-4o-mini 二元判定 (CORRECT/WRONG) |
| **Recall@10** | (仅 LongMemEval) 答案 session 在 top-10 召回中的比例 |

## 断点续跑

所有管线支持 checkpoint，中断后重新运行会自动跳过已完成的项目：
- `results/locomo_query_checkpoint.json`
- `results/longmemeval_ingest_checkpoint.json`
- `results/longmemeval_query_checkpoint.json`

## 输出示例

```
LoCoMo Evaluation Results
=======================================================
Category             Count       F1   BLEU-1    Judge
-------------------------------------------------------
1 (multi-hop)          282    0.XXX    0.XXX    0.XXX
2 (temporal)           321    0.XXX    0.XXX    0.XXX
3 (open-dom)            96    0.XXX    0.XXX    0.XXX
4 (single-hop)         841    0.XXX    0.XXX    0.XXX
-------------------------------------------------------
Overall               1540    0.XXX    0.XXX    0.XXX
```

## 配置项

| 环境变量 | 默认值 | 说明 |
|---------|--------|------|
| `EMBEDDING_PROVIDER` | `siliconflow` | `siliconflow` 或 `openai` |
| `EMBEDDING_MODEL` | (provider default) | 模型名称 |
| `LLM_MODEL` | `deepseek-chat` | 记忆提取 + 回答生成 |
| `JUDGE_MODEL` | `gpt-4o-mini` | LLM Judge |
| `GRAPH_ENABLED` | `0` | 是否启用图记忆 (`1` 启用) |
| `RESULTS_DIR` | `evaluation/results` | 结果输出目录 |
