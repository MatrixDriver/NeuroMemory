# LoCoMo 评测改进计划

## 当前基线

- **Overall LLM Judge: 12.5%** (mem0: 66.9%, Zep: 75.1%, Memobase: 75.8%)
- 60.8% 的回答是 "I don't know"
- 配置: all-MiniLM-L6-v2 (384d) + DeepSeek-chat + DeepSeek Judge

## 改进项（按影响排序）

### P0: 回答 prompt 对齐 mem0（影响最大，难度低）

**问题**: 当前 prompt 明确说 "say I don't know"，导致 60.8% 拒答。mem0 的 prompt 不包含任何 "I don't know" 指令。

**mem0 使用的 prompt**:
```
You are an intelligent memory assistant tasked with retrieving accurate information from conversation memories.

# INSTRUCTIONS:
1. Carefully analyze all provided memories from both speakers
2. Pay special attention to the timestamps to determine the answer
3. If the question asks about a specific event or fact, look for direct evidence in the memories
4. If the memories contain contradictory information, prioritize the most recent memory
5. If there is a question about time references (like "last year", "two months ago", etc.),
   calculate the actual date based on the memory timestamp.
6. Always convert relative time references to specific dates, months, or years.
7. Focus only on the content of the memories from both speakers.
8. The answer should be less than 5-6 words.
```

**LoCoMo 原始论文的 prompt**:
```
Based on the above context, write an answer in the form of a short phrase for the following question.
Answer with exact words from the context whenever possible.
```

**行动**: 替换为 mem0 的 prompt（公平对比）或 LoCoMo 原始 prompt。

### P1: recall 同时返回原始对话片段（影响大，难度中）

**问题**: 当前只搜索 LLM 提取的摘要事实，信息严重有损。日期、列表、具体细节在提取时丢失。

**mem0 做法**: 同时检索原始对话片段 + 提取的记忆，合并后送给 LLM。

**行动**: 在 recall() 中增加 conversation embedding 搜索，与 memory embedding 结果合并。

### P2: 提取 prompt 改为英文/多语言自适应（影响中，难度低）

**问题**: `memory_extraction.py` 的提取 prompt 全是中文，处理英文对话时部分结果变成中文，embedding 匹配质量下降。有 14 条回答直接是中文。

**行动**: 提供英文版提取 prompt，根据输入语言自动选择。或评测时用英文 prompt override。

### P3: 换用更强的 embedding 模型（影响中，难度低）

**问题**: all-MiniLM-L6-v2 (384 dims) vs mem0 的 text-embedding-3-small (1536 dims)，语义匹配差距大。

**行动**: 支持 OpenAI embedding，评测时用 text-embedding-3-small 做公平对比。

### P4: 评测时关闭或调大 recency 衰减（影响中，难度低）

**问题**: scored_search 默认 30 天衰减，LoCoMo 对话跨数月，旧记忆即使正确也被惩罚。

**行动**: 评测时设 decay_rate=365 或更大，或提供纯 relevance 搜索模式。

### P5: 合并记忆时加 speaker 标注（影响小，难度低）

**问题**: 两个 speaker 的记忆合并为扁平列表，LLM 无法区分谁说的。

**mem0 做法**: prompt 中分开展示两个 speaker 的记忆:
```
Memories for user {speaker_1_user_id}:
{speaker_1_memories}

Memories for user {speaker_2_user_id}:
{speaker_2_memories}
```

**行动**: 在 locomo.py query 阶段分开展示两个 speaker 的记忆。

### P6: LLM Judge prompt 校准（影响小，难度低）

**问题**: 需确认我们的 judge prompt 与 mem0 一致。mem0 的 judge 被描述为 "generous with grading"。

**行动**: 对比 judge prompt，确保评分标准一致。

## 公平对比配置（目标）

| 组件 | NeuroMemory | mem0 |
|------|------------|------|
| Embedding | text-embedding-3-small | text-embedding-3-small |
| LLM | gpt-4o-mini | gpt-4o-mini |
| Judge | gpt-4o-mini | gpt-4o-mini |
| Answer Prompt | mem0 prompt | mem0 prompt |
| 检索量 | 10 memories | 10 memories |

## 实施优先级

1. **快速见效** (预计 12.5% → 30-40%): P0 + P2 + P4 + P5
2. **中期提升** (预计 → 50-60%): P1 + P3
3. **精细调优** (预计 → 65%+): P6 + recall 策略优化
