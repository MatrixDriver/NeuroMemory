"""Chat Agent with Memory - NeuroMemory 示例

一个带记忆的终端对话 Agent，展示 NeuroMemory 的核心功能：
- 混合记忆架构：向量搜索 + 图实体关系 + KV 偏好
- 对话历史管理
- 可配置的自动记忆提取策略

用法:
    export LLM_API_KEY=your_key
    python example/chat_agent.py

默认使用内置的 HashEmbedding（基于哈希，无需额外依赖，适合功能验证）。
如需真正的语义检索，安装 sentence-transformers 后会自动启用本地模型。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import os
import uuid

from neuromemory import ExtractionStrategy, NeuroMemory, OpenAILLM
from neuromemory.providers.embedding import EmbeddingProvider

USER_ID = "demo-user"
SESSION_ID = str(uuid.uuid4())

# --- Embedding Providers ---


class HashEmbedding(EmbeddingProvider):
    """基于哈希的 embedding provider，无需额外依赖。

    使用 SHA-256 哈希生成确定性向量，不提供真正的语义相似度，
    但可以完整验证 NeuroMemory 的所有功能流程。
    """

    def __init__(self, dims: int = 1024):
        self._dims = dims

    @property
    def dims(self) -> int:
        return self._dims

    async def embed(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        raw = []
        # 用 SHA-256 的 32 字节循环填充到目标维度
        for i in range(self._dims):
            byte_val = digest[i % len(digest)] ^ (i // len(digest) & 0xFF)
            raw.append(byte_val / 255.0 * 2 - 1)
        # L2 归一化
        norm = math.sqrt(sum(x * x for x in raw)) or 1.0
        return [x / norm for x in raw]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(t) for t in texts]


MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


class LocalEmbedding(EmbeddingProvider):
    """使用 sentence-transformers 的本地 embedding provider。

    首次使用时自动下载模型（约 450MB），之后从本地缓存加载。
    模型: paraphrase-multilingual-MiniLM-L12-v2 (384 dims, 支持中英文)
    """

    def __init__(self, model_name: str = MODEL_NAME):
        from sentence_transformers import SentenceTransformer

        print(f"加载 embedding 模型: {model_name}")
        print("（首次运行需要下载，之后从缓存加载）")
        self._model = SentenceTransformer(model_name)
        self._dims = self._model.get_sentence_embedding_dimension()
        print(f"模型加载完成 (dims={self._dims})")

    @property
    def dims(self) -> int:
        return self._dims

    async def embed(self, text: str) -> list[float]:
        result = await self.embed_batch([text])
        return result[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return [e.tolist() for e in embeddings]


def create_embedding_provider() -> EmbeddingProvider:
    """自动选择最佳 embedding provider。

    优先使用 sentence-transformers 本地模型（真正的语义检索），
    如果未安装则回退到 HashEmbedding（功能验证模式）。
    """
    try:
        import sentence_transformers  # noqa: F401
        print("检测到 sentence-transformers，使用本地语义模型")
        return LocalEmbedding()
    except ImportError:
        print("使用内置 HashEmbedding（功能验证模式，无语义相似度）")
        print("提示: pip install sentence-transformers 可启用真正的语义检索\n")
        return HashEmbedding(dims=1024)


# --- Provider 初始化 ---


def create_llm_provider():
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise ValueError("请设置 LLM_API_KEY 环境变量")

    return OpenAILLM(
        api_key=api_key,
        model=os.getenv("LLM_MODEL", "deepseek-chat"),
        base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1"),
    )


# --- LLM 调用 ---


async def generate_reply(llm: OpenAILLM, user_input: str, memories: list[dict], history: list[dict]) -> str:
    """调用 LLM 生成回复，将相关记忆注入 system prompt。"""
    system_parts = ["你是一个友好的 AI 助手，能够记住用户之前告诉你的信息。"]

    if memories:
        lines = []
        for m in memories:
            meta = m.get("metadata") or {}
            emotion_hint = ""
            if "emotion" in meta and meta["emotion"]:
                label = meta["emotion"].get("label", "")
                valence = meta["emotion"].get("valence", 0)
                if label:
                    emotion_hint = f" [用户当时感到{label}]"
                elif valence < -0.3:
                    emotion_hint = " [负面情绪]"
                elif valence > 0.3:
                    emotion_hint = " [正面情绪]"

            if m.get("source") == "graph":
                lines.append(f"- [关系] {m.get('content', '')}")
            elif m.get("memory_type") == "reflection":
                lines.append(f"- [理解] {m['content']}")
            else:
                score = m.get('score', 0)
                lines.append(f"- {m['content']} (得分: {score:.2f}){emotion_hint}")
        memory_text = "\n".join(lines)
        system_parts.append(f"\n你记得关于用户的以下信息：\n{memory_text}")

    system_parts.append("\n请基于你对用户的了解来回答问题。如果用户告诉你新的个人信息，自然地记住它。")

    messages = [{"role": "system", "content": "\n".join(system_parts)}]

    # 添加最近的对话历史（最多 10 轮）
    for msg in history[-20:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    messages.append({"role": "user", "content": user_input})

    return await llm.chat(messages, temperature=0.7, max_tokens=1024)


# --- 命令处理 ---


async def handle_memories_command(nm: NeuroMemory, query: str):
    """搜索记忆（混合检索，三因子评分）。"""
    if not query:
        print("  用法: /memories <搜索词>")
        return
    recall_result = await nm.recall(user_id=USER_ID, query=query, limit=5)
    merged = recall_result["merged"]
    if not merged:
        print("  没有找到相关记忆。")
        return
    print(f"  找到 {len(merged)} 条相关记忆（三因子评分：相关性 × 时效性 × 重要性）：")
    for r in merged:
        source = r.get("source", "?")
        meta = r.get("metadata") or {}
        emotion_str = ""
        if "emotion" in meta and meta["emotion"]:
            label = meta["emotion"].get("label", "")
            if label:
                emotion_str = f" 💭{label}"

        if source == "vector":
            score = r.get("score", 0)
            importance = meta.get("importance", "?")
            print(f"    - [向量/{r.get('memory_type', '?')}] {r['content']} "
                  f"(得分: {score:.2f}, 重要性: {importance}){emotion_str}")
        else:
            print(f"    - [图/{r.get('relation', '?')}] {r.get('subject', '?')} → "
                  f"{r.get('object', '?')}: {r.get('content', '')}")


async def handle_reflect_command(nm: NeuroMemory):
    """触发反思，生成高层次洞察。"""
    print("  正在反思最近的记忆...")
    try:
        result = await nm.reflect(user_id=USER_ID, limit=50)
        count = result.get("insights_generated", 0)
        facts = result.get("facts_added", 0)
        prefs = result.get("preferences_updated", 0)
        print(f"  反思完成：提取 {facts} 条事实，{prefs} 条偏好，生成 {count} 条洞察")
        if count > 0:
            for ins in result.get("insights", []):
                print(f"    - {ins.get('content', '')}")
    except RuntimeError as e:
        print(f"  反思失败: {e}")


async def handle_history_command(nm: NeuroMemory):
    """查看当前会话对话历史。"""
    messages = await nm.conversations.get_session_messages(
        user_id=USER_ID, session_id=SESSION_ID, limit=50,
    )
    if not messages:
        print("  当前会话没有对话历史。")
        return
    print(f"  当前会话共 {len(messages)} 条消息：")
    for msg in messages:
        role = "🧑 用户" if msg.role == "user" else "🤖 助手"
        content = msg.content[:80] + "..." if len(msg.content) > 80 else msg.content
        print(f"    {role}: {content}")


async def handle_prefs_command(nm: NeuroMemory, args: str):
    """查看或设置偏好。"""
    parts = args.strip().split(maxsplit=1)
    if not parts:
        # 列出所有偏好
        prefs = await nm.kv.list("preferences", USER_ID)
        if not prefs:
            print("  没有保存的偏好。")
            return
        print("  用户偏好：")
        for p in prefs:
            print(f"    {p.key} = {p.value}")
        return

    if len(parts) == 1:
        # 查询单个偏好
        val = await nm.kv.get("preferences", USER_ID, parts[0])
        if val is None:
            print(f"  偏好 '{parts[0]}' 未设置。")
        else:
            print(f"  {parts[0]} = {val.value}")
    else:
        # 设置偏好
        await nm.kv.set("preferences", USER_ID, parts[0], parts[1])
        print(f"  已设置: {parts[0]} = {parts[1]}")


# --- 主循环 ---

HELP_TEXT = """
可用命令：
  /memories <query>  - 搜索记忆（三因子评分：相关性 × 时效性 × 重要性）
  /reflect           - 触发反思，从近期记忆生成高层次洞察
  /history           - 查看当前会话对话历史
  /prefs [key] [val] - 查看/设置偏好
  /help              - 显示帮助
  /quit              - 退出
"""


async def main():
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://neuromemory:neuromemory@localhost:5432/neuromemory",
    )

    # 使用默认提取策略：每 10 条消息 + 10 分钟空闲 + session 关闭 + 程序退出
    strategy = ExtractionStrategy()

    embedding = create_embedding_provider()
    llm = create_llm_provider()

    # 开启 extraction 日志，便于观察自动提取过程
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("neuromemory").setLevel(logging.INFO)

    async with NeuroMemory(
        database_url=database_url,
        embedding=embedding,
        llm=llm,
        extraction=strategy,
        graph_enabled=True,
    ) as nm:
        print("=" * 50)
        print("  NeuroMemory Chat Agent")
        print(f"  会话 ID: {SESSION_ID[:8]}...")
        print("  输入 /help 查看可用命令")
        print("=" * 50)

        history: list[dict] = []

        while True:
            try:
                user_input = input("\n你: ").strip()
            except (EOFError, KeyboardInterrupt):
                user_input = "/quit"

            if not user_input:
                continue

            # 处理命令
            if user_input.startswith("/"):
                cmd, _, args = user_input[1:].partition(" ")
                cmd = cmd.lower()

                if cmd == "quit" or cmd == "exit":
                    # 关闭 session，触发记忆提取
                    await nm.conversations.close_session(USER_ID, SESSION_ID)
                    print("\n再见！")
                    break
                elif cmd == "memories":
                    await handle_memories_command(nm, args.strip())
                elif cmd == "reflect":
                    await handle_reflect_command(nm)
                elif cmd == "history":
                    await handle_history_command(nm)
                elif cmd == "prefs":
                    await handle_prefs_command(nm, args)
                elif cmd == "help":
                    print(HELP_TEXT)
                else:
                    print(f"  未知命令: /{cmd}，输入 /help 查看帮助。")
                continue

            # 1. 混合检索相关记忆
            recall_result = await nm.recall(user_id=USER_ID, query=user_input, limit=3)
            memories = recall_result["merged"]

            # 2. 调用 LLM 生成回复
            reply = await generate_reply(llm, user_input, memories, history)

            # 3. 保存对话消息（框架自动按策略触发记忆提取）
            await nm.conversations.add_message(
                user_id=USER_ID, role="user", content=user_input, session_id=SESSION_ID,
            )
            await nm.conversations.add_message(
                user_id=USER_ID, role="assistant", content=reply, session_id=SESSION_ID,
            )

            # 4. 将用户消息存为记忆（便于后续语义搜索）
            await nm.add_memory(user_id=USER_ID, content=user_input)

            # 5. 更新本地历史
            history.append({"role": "user", "content": user_input})
            history.append({"role": "assistant", "content": reply})

            # 6. 打印回复
            if memories:
                print(f"  (召回 {len(memories)} 条相关记忆)")
            print(f"\n助手: {reply}")


if __name__ == "__main__":
    asyncio.run(main())
