"""
NeuroMemory 主程序
神经符号混合记忆系统 - 核心认知流程实现
"""
from mem0 import Memory

from config import (
    MEM0_CONFIG,
    LLM_PROVIDER,
    EMBEDDING_PROVIDER,
    get_chat_config,
)


def create_chat_llm():
    """根据配置创建对话 LLM 实例"""
    chat_config = get_chat_config()

    if chat_config["provider"] == "gemini":
        from langchain_google_genai import ChatGoogleGenerativeAI
        return ChatGoogleGenerativeAI(
            model=chat_config["model"],
            temperature=chat_config["temperature"],
        )
    elif chat_config["provider"] == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(
            model=chat_config["model"],
            temperature=chat_config["temperature"],
            base_url=chat_config["base_url"],
        )
    else:
        raise ValueError(f"未知的 LLM 提供商: {chat_config['provider']}")


def create_brain() -> Memory:
    """初始化混合记忆系统"""
    return Memory.from_config(MEM0_CONFIG)


def cognitive_process(
    brain: Memory,
    user_input: str,
    user_id: str = "default_user",
) -> str:
    """
    核心认知流程

    Args:
        brain: Memory 实例
        user_input: 用户输入
        user_id: 用户标识

    Returns:
        AI 生成的回答
    """
    print(f"\n[输入] {user_input}")

    # Step 1: 混合检索 (Hybrid Retrieval)
    search_results = brain.search(user_input, user_id=user_id)

    knowledge_context = ""
    if search_results:
        print("[海马体] 激活记忆:")
        for res in search_results:
            # 兼容不同的返回格式
            if isinstance(res, dict):
                memory_text = res.get("memory", str(res))
                source_type = res.get("type", "vector")
            else:
                memory_text = str(res)
                source_type = "vector"
            print(f"  - [{source_type}] {memory_text}")
            knowledge_context += f"- {memory_text}\n"

    # Step 2: 深度推理 (System 2 Thinking)
    llm = create_chat_llm()

    system_prompt = f"""你是一个拥有"图谱思维"的超级智能。

[已提取的知识网络]
{knowledge_context if knowledge_context else "(暂无相关记忆)"}

[指令]
请基于上述知识网络回答用户问题。
如果知识中包含实体关系（如 A 导致 B，或 A 属于 B），请明确指出这种逻辑链条。
"""

    response = llm.invoke([("system", system_prompt), ("user", user_input)])
    answer = response.content

    print(f"[前额叶] 生成回答:\n{answer}")

    # Step 3: 记忆整合 (Consolidation)
    brain.add(user_input, user_id=user_id)
    brain.add(f"针对'{user_input}'的回答是: {answer}", user_id=user_id)
    print("[后台] 知识图谱已更新。")

    return answer


def demo_multi_hop_reasoning():
    """演示多跳推理能力"""
    print("=" * 50)
    print("NeuroMemory 多跳推理演示")
    print(f"当前配置: LLM={LLM_PROVIDER}, Embedding={EMBEDDING_PROVIDER}")
    print("=" * 50)

    brain = create_brain()
    user_id = "demo_user"

    # 注入碎片化信息
    print("\n--- 正在构建初始记忆 ---")
    cognitive_process(brain, "DeepMind 是 Google 的子公司。", user_id)
    cognitive_process(brain, "Demis Hassabis 是 DeepMind 的 CEO。", user_id)
    cognitive_process(brain, "Gemini 是 DeepMind 团队研发的。", user_id)

    print("\n" + "=" * 50)

    # 测试多跳推理
    print("\n--- 测试推理能力 ---")
    cognitive_process(brain, "Demis Hassabis 和 Gemini 模型有什么关系？", user_id)


if __name__ == "__main__":
    demo_multi_hop_reasoning()
