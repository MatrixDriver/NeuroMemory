# neuromem 示例：带记忆的对话 Agent

一个终端交互式聊天机器人，展示 neuromem 框架的核心能力。

## 功能

- **记忆存储与语义搜索**：用户说的重要信息自动存为记忆，后续提问时通过向量搜索召回相关记忆
- **对话历史管理**：通过 `nm.conversations` 存储完整对话
- **KV 偏好存储**：存取用户偏好设置
- **记忆提取**：对话结束时用 LLM 自动从对话中提取结构化记忆（偏好、事实、情景）

## 前置条件

```bash
# 启动 PostgreSQL
docker compose -f docker-compose.yml up -d db

# 安装 neuromem
pip install -e ".[dev]"
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DATABASE_URL` | PostgreSQL 连接地址 | `postgresql+asyncpg://neuromem:neuromem@localhost:5432/neuromem` |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | **必填** |
| `LLM_MODEL` | LLM 模型名 | `deepseek-chat` (DeepSeek V3.2) |
| `LLM_BASE_URL` | LLM API 地址 | `https://api.deepseek.com/v1` |

### Embedding

默认使用内置的 **HashEmbedding**（基于哈希，无需额外依赖），可以完整验证所有功能流程。

如需真正的语义检索能力，安装 `sentence-transformers` 后会自动切换到本地模型：

```bash
pip install sentence-transformers
# 模型: paraphrase-multilingual-MiniLM-L12-v2 (384 dims, 支持中英文)
# 首次运行自动下载（约 450MB）
```

> 注意：sentence-transformers 依赖 PyTorch，需要 Python ≤ 3.12 或 ARM64 架构。

## 运行

```bash
# 使用 DeepSeek V3.2（默认）
export DEEPSEEK_API_KEY=your_deepseek_key
python example/chat_agent.py

# 使用 OpenAI（通过环境变量覆盖）
export DEEPSEEK_API_KEY=your_openai_key
export LLM_BASE_URL=https://api.openai.com/v1
export LLM_MODEL=gpt-4o-mini
python example/chat_agent.py
```

## 交互命令

| 命令 | 说明 |
|------|------|
| `/memories <query>` | 搜索记忆（三因子评分：相关性 × 时效性 × 重要性） |
| `/digest` | 触发反思，从近期记忆生成高层次洞察 |
| `/history` | 查看当前会话对话历史 |
| `/prefs [key] [value]` | 查看/设置偏好 |
| `/help` | 显示帮助 |
| `/quit` | 退出（自动触发记忆提取） |

## 示例对话

```
你: 我叫小明，在北京的一家 AI 创业公司工作
助手: 你好小明！在 AI 创业公司工作一定很有趣...

你: 我喜欢用 Python 写代码
  (召回 1 条相关记忆)
助手: Python 确实是 AI 领域最流行的语言...

你: 你还记得我在哪里工作吗？
  (召回 2 条相关记忆)
助手: 当然记得！你在北京的一家 AI 创业公司工作。

/memories 工作
  找到 2 条相关记忆：
    - [general] 我叫小明，在北京的一家 AI 创业公司工作 (相关度: 0.95)
    - [general] 我喜欢用 Python 写代码 (相关度: 0.42)

/quit
正在从对话中提取记忆...
记忆提取完成：
  偏好: 1 条
  事实: 2 条
  情景: 0 条
  处理消息: 6 条
```
