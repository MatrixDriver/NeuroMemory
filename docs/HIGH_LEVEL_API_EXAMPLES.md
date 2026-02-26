# neuromem 高层 API 使用示例

## 对比：底层 vs 高层 API

### 底层 API（现有）
```python
from neuromem import neuromemClient

client = neuromemClient(api_key="nm_xxx")

# 需要用户手动分类和提取
client.add_memory(
    user_id="user1",
    content="我喜欢蓝色",
    memory_type="preference"
)

client.preferences.set(
    user_id="user1",
    key="favorite_color",
    value="蓝色"
)
```

### 高层 API（新增）
```python
from neuromem import neuromemClient

client = neuromemClient(api_key="nm_xxx")

# 直接提交对话，自动处理一切
client.conversations.add_message(
    user_id="user1",
    role="user",
    content="我喜欢蓝色"
)

# 系统自动：
# 1. 存储会话到 KV
# 2. LLM 识别为偏好
# 3. 提取并存入 Preferences
# 4. 生成 embedding 存入向量数据库
```

---

## 完整示例 1: 智能聊天机器人

```python
from neuromem import neuromemClient
from anthropic import Anthropic

class SmartChatbot:
    def __init__(self, nm_api_key: str, claude_api_key: str):
        self.memory = neuromemClient(api_key=nm_api_key)
        self.claude = Anthropic(api_key=claude_api_key)

        # 启用自动记忆提取（每 10 条消息提取一次）
        self.memory.conversations.enable_auto_extract(
            user_id="user1",
            trigger="message_count",
            threshold=10
        )

    def chat(self, user_id: str, message: str) -> str:
        # 1. 检索相关记忆（跨所有类型）
        memories = self.memory.memory.search(
            user_id=user_id,
            query=message,
            memory_types=["preference", "fact", "episodic", "document"],
            limit=5
        )

        # 2. 构建记忆上下文
        context = "用户的相关信息：\n"
        for mem in memories:
            context += f"- [{mem['type']}] {mem['content']} (相关度: {mem['score']:.2f})\n"

        # 3. 调用 Claude
        prompt = f"""{context}

用户问题: {message}

请基于用户的历史信息回答问题。"""

        response = self.claude.messages.create(
            model="claude-sonnet-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024
        )

        answer = response.content[0].text

        # 4. 存储对话（自动触发记忆提取）
        self.memory.conversations.add_messages(
            user_id=user_id,
            messages=[
                {"role": "user", "content": message},
                {"role": "assistant", "content": answer}
            ]
        )

        return answer

# 使用示例
bot = SmartChatbot(
    nm_api_key="nm_xxx",
    claude_api_key="sk-ant-xxx"
)

# 第一轮对话
print(bot.chat("user1", "我在 Google 工作，负责后端开发"))
# => "很高兴认识您！Google 是一家优秀的科技公司..."

# 第二轮对话
print(bot.chat("user1", "我喜欢蓝色和极简风格"))
# => "了解了您的喜好！蓝色代表专业和信任..."

# ... 10 条消息后，系统自动提取记忆

# 第 N 轮对话 - Bot 已经记住所有信息
print(bot.chat("user1", "推荐一个适合我的编辑器主题"))
# => "基于您在 Google 从事后端开发的背景，以及您喜欢蓝色和极简风格，
#     我推荐 Visual Studio Code 的 'One Dark Pro' 主题..."
```

---

## 完整示例 2: 知识库助手

```python
from neuromem import neuromemClient

class KnowledgeAssistant:
    def __init__(self, api_key: str):
        self.memory = neuromemClient(api_key=api_key)

    def add_document(self, user_id: str, file_path: str, category: str = "knowledge"):
        """添加文档到知识库"""
        doc = self.memory.files.add_document(
            user_id=user_id,
            file_path=file_path,
            category=category,
            auto_extract=True  # 自动提取并生成 embedding
        )
        print(f"文档已添加: {doc['filename']}")
        print(f"生成了 {doc.get('embedding_count', 0)} 个 embedding")
        return doc

    def add_webpage(self, user_id: str, url: str):
        """添加网页到知识库（自动下载）"""
        doc = self.memory.files.add_url(
            user_id=user_id,
            url=url,
            category="web_article",
            auto_extract=True,
            format="markdown"  # 保存为 markdown
        )
        print(f"网页已下载: {doc['title']}")
        print(f"提取了 {doc.get('extracted_facts', 0)} 个事实")
        return doc

    def ask(self, user_id: str, question: str) -> str:
        """基于知识库回答问题"""
        # 跨文档和记忆搜索
        results = self.memory.memory.search(
            user_id=user_id,
            query=question,
            memory_types=["document", "fact", "semantic"],
            limit=10
        )

        if not results:
            return "抱歉，我在知识库中没有找到相关信息。"

        # 构建 RAG 上下文
        context = "相关知识：\n\n"
        for i, result in enumerate(results, 1):
            context += f"{i}. {result['content']}\n"
            if 'source' in result:
                context += f"   来源: {result['source']}\n"
            context += "\n"

        # 调用 LLM（这里简化为返回引用）
        answer = f"基于以下知识回答您的问题：\n\n{context}"
        return answer

    def list_knowledge(self, user_id: str):
        """列出所有知识源"""
        files = self.memory.files.list(user_id=user_id)
        print(f"\n知识库文件列表（共 {len(files)} 个）：")
        for file in files:
            print(f"- {file['filename']} ({file['category']}) - {file['size']} bytes")

# 使用示例
assistant = KnowledgeAssistant(api_key="nm_xxx")

# 添加文档
assistant.add_document("user1", "/path/to/python_tutorial.pdf", "programming")
assistant.add_document("user1", "/path/to/django_guide.pdf", "programming")

# 添加网页
assistant.add_webpage("user1", "https://docs.python.org/3/tutorial/errors.html")
assistant.add_webpage("user1", "https://realpython.com/python-exceptions/")

# 查看知识库
assistant.list_knowledge("user1")

# 提问
answer = assistant.ask("user1", "Python 如何处理异常？")
print(answer)
```

---

## 完整示例 3: 个人助理 Agent

```python
from neuromem import neuromemClient
from datetime import datetime

class PersonalAssistant:
    def __init__(self, user_id: str, api_key: str):
        self.user_id = user_id
        self.memory = neuromemClient(api_key=api_key)

    def morning_routine(self):
        """早晨例行：回顾昨天的记忆"""
        # 获取昨天的情景记忆
        yesterday = datetime.now().date() - timedelta(days=1)
        episodes = self.memory.memory.get_episodes(
            user_id=self.user_id,
            time_range=(str(yesterday), str(yesterday))
        )

        print(f"📅 {yesterday} 您做了这些事：")
        for ep in episodes:
            print(f"- {ep['content']}")

        # 获取今天的偏好（提醒事项）
        prefs = self.memory.memory.get_preferences(
            user_id=self.user_id,
            keys=["wake_time", "morning_routine"]
        )
        for pref in prefs:
            print(f"⏰ {pref['key']}: {pref['value']}")

    def process_conversation(self, message: str) -> str:
        """处理用户输入"""
        # 存储对话
        self.memory.conversations.add_message(
            user_id=self.user_id,
            role="user",
            content=message
        )

        # 检索相关信息
        context = self.memory.memory.search(
            user_id=self.user_id,
            query=message,
            limit=3
        )

        # 生成回复（简化版）
        if "我的" in message or "我在" in message:
            # 学习新信息
            return "好的，我已经记住了！"
        else:
            # 回忆信息
            if context:
                return f"根据我的记忆：{context[0]['content']}"
            else:
                return "我还没有相关的记忆。"

    def evening_summary(self):
        """晚上总结"""
        # 手动触发记忆提取
        result = self.memory.conversations.extract_memories(
            user_id=self.user_id
        )

        print("\n🌙 今日记忆总结：")
        print(f"- 提取了 {result['preferences_extracted']} 个偏好")
        print(f"- 提取了 {result['facts_extracted']} 个事实")
        print(f"- 提取了 {result.get('episodes_extracted', 0)} 个情景")

    def get_profile(self):
        """查看完整画像"""
        profile = self.memory.memory.get_user_profile(
            user_id=self.user_id
        )

        print("\n👤 用户画像：")
        print(f"\n偏好：")
        for key, value in profile.get('preferences', {}).items():
            print(f"  {key}: {value}")

        print(f"\n事实摘要：")
        for category, facts in profile.get('facts_summary', {}).items():
            print(f"  {category}: {len(facts)} 条")

        print(f"\n文档: {profile.get('documents_count', 0)} 个")

# 使用示例
assistant = PersonalAssistant(user_id="user1", api_key="nm_xxx")

# 早晨
assistant.morning_routine()

# 白天的对话
assistant.process_conversation("我今天参加了团队会议")
assistant.process_conversation("讨论了 Q2 的 OKR 目标")
assistant.process_conversation("晚上和朋友去看了电影《沙丘2》")

# 晚上
assistant.evening_summary()
assistant.get_profile()
```

---

## 完整示例 4: Multi-Agent 协作系统

```python
from neuromem import neuromemClient

class AgentTeam:
    def __init__(self, api_key: str):
        self.memory = neuromemClient(api_key=api_key)
        self.agents = {}

    def add_agent(self, agent_id: str, role: str, capabilities: list):
        """添加 Agent"""
        self.agents[agent_id] = {
            "role": role,
            "capabilities": capabilities,
            "user_id": f"agent_{agent_id}"  # 每个 agent 独立的记忆空间
        }

        # 存储 agent 的元信息
        self.memory.preferences.set(
            user_id=f"agent_{agent_id}",
            key="role",
            value=role
        )
        for cap in capabilities:
            self.memory.add_memory(
                user_id=f"agent_{agent_id}",
                content=f"我能够: {cap}",
                memory_type="capability"
            )

    def share_knowledge(self, from_agent: str, to_agent: str, knowledge: str):
        """Agent 之间共享知识"""
        # 存到发送方
        self.memory.conversations.add_message(
            user_id=f"agent_{from_agent}",
            role="system",
            content=f"[分享给 {to_agent}] {knowledge}"
        )

        # 存到接收方
        self.memory.add_memory(
            user_id=f"agent_{to_agent}",
            content=f"[来自 {from_agent}] {knowledge}",
            memory_type="shared_knowledge"
        )

    def query_team(self, query: str) -> dict:
        """查询整个团队的知识"""
        results = {}
        for agent_id, info in self.agents.items():
            user_id = info["user_id"]
            memories = self.memory.search(
                user_id=user_id,
                query=query,
                limit=3
            )
            results[agent_id] = {
                "role": info["role"],
                "relevant_knowledge": memories
            }
        return results

# 使用示例
team = AgentTeam(api_key="nm_xxx")

# 创建专业 Agents
team.add_agent(
    "researcher",
    role="研究员",
    capabilities=["搜索论文", "总结文献", "分析数据"]
)

team.add_agent(
    "coder",
    role="程序员",
    capabilities=["编写代码", "调试程序", "代码审查"]
)

team.add_agent(
    "writer",
    role="作家",
    capabilities=["撰写文档", "润色文字", "创作故事"]
)

# 研究员发现了新知识
team.share_knowledge(
    from_agent="researcher",
    to_agent="coder",
    knowledge="最新的论文显示 Transformer 架构可以用于代码生成"
)

# 查询整个团队
results = team.query_team("代码生成相关的知识")
for agent_id, info in results.items():
    print(f"\n{agent_id} ({info['role']}):")
    for mem in info['relevant_knowledge']:
        print(f"  - {mem['content']}")
```

---

## 完整示例 5: 文档问答系统

```python
from neuromem import neuromemClient

class DocQA:
    def __init__(self, api_key: str):
        self.memory = neuromemClient(api_key=api_key)

    def ingest_folder(self, user_id: str, folder_path: str):
        """批量导入文件夹中的文档"""
        import os
        from pathlib import Path

        docs_added = 0
        for file_path in Path(folder_path).rglob("*"):
            if file_path.is_file() and file_path.suffix in [".pdf", ".txt", ".md"]:
                try:
                    doc = self.memory.files.add_document(
                        user_id=user_id,
                        file_path=str(file_path),
                        category="knowledge_base",
                        auto_extract=True
                    )
                    docs_added += 1
                    print(f"✓ {file_path.name}")
                except Exception as e:
                    print(f"✗ {file_path.name}: {e}")

        print(f"\n导入完成：{docs_added} 个文档")

    def ask(self, user_id: str, question: str, context_length: int = 5):
        """提问并获得基于文档的答案"""
        # 检索相关文档片段
        results = self.memory.files.search(
            user_id=user_id,
            query=question,
            limit=context_length
        )

        if not results:
            return "没有找到相关文档。"

        # 构建答案（这里简化，实际应调用 LLM）
        answer = f"基于文档的回答：\n\n"
        for i, result in enumerate(results, 1):
            answer += f"{i}. 来自 {result['filename']}:\n"
            answer += f"   {result['matches'][0]}\n\n"

        return answer

# 使用
qa = DocQA(api_key="nm_xxx")

# 导入文档
qa.ingest_folder("user1", "/path/to/docs")

# 提问
answer = qa.ask("user1", "什么是向量数据库？")
print(answer)
```

---

## 总结

高层 API 的核心优势：

1. **极简使用** - 3 行代码即可拥有记忆能力
2. **自动分类** - 无需手动区分记忆类型
3. **智能提取** - LLM 自动从对话中提取关键信息
4. **统一检索** - 一个接口搜索所有类型的记忆
5. **文件管理** - 自动下载、提取、索引文档和 URL

让 AI Agent 开发变得更简单！🚀
