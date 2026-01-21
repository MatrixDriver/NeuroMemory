"""
NeuroMemory 主程序
神经符号混合记忆系统 - 核心认知流程实现
"""
# 预加载 openai 模块，避免并发导入死锁
import openai.resources.embeddings  # noqa: F401

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from pydantic import BaseModel
from mem0 import Memory

from config import (
    MEM0_CONFIG,
    LLM_PROVIDER,
    EMBEDDING_PROVIDER,
    DEEPSEEK_API_KEY,
    DEEPSEEK_CONFIG,
    get_chat_config,
)


# =============================================================================
# 异步记忆整合模块
# =============================================================================

# 配置后台整合日志记录器
_consolidation_logger = logging.getLogger("neuro_memory.consolidation")
_consolidation_logger.setLevel(logging.INFO)
if not _consolidation_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s"))
    _consolidation_logger.addHandler(_handler)

# 后台整合线程池（max_workers=2 确保不会积压太多任务）
_consolidation_executor = ThreadPoolExecutor(
    max_workers=2,
    thread_name_prefix="mem_consolidate"
)


def _background_consolidate(brain: Memory, texts: list[str], user_id: str) -> None:
    """
    后台执行记忆整合（异步，不阻塞主流程）
    
    Args:
        brain: Memory 实例
        texts: 需要存储的文本列表
        user_id: 用户标识
    """
    import time
    start = time.perf_counter()
    success_count = 0
    
    for text in texts:
        try:
            brain.add(text, user_id=user_id)
            success_count += 1
        except Exception as e:
            _consolidation_logger.warning(f"记忆保存失败: {e}")
    
    elapsed = time.perf_counter() - start
    _consolidation_logger.info(
        f"记忆整合完成: {success_count}/{len(texts)} 条成功, 耗时 {elapsed:.2f}s"
    )


# =============================================================================
# 代词消解模块 (Coreference Resolution)
# =============================================================================

import re

# 用户身份上下文（可扩展为持久化存储）
USER_IDENTITY_CACHE: dict[str, dict] = {}


def extract_user_identity(user_input: str, user_id: str) -> str | None:
    """
    从输入中提取用户身份信息
    
    Args:
        user_input: 用户输入
        user_id: 用户标识
        
    Returns:
        提取到的用户名，如果没有则返回 None
    """
    # 匹配 "我的名字叫XXX"、"我叫XXX"、"我是XXX" 等模式
    patterns = [
        r"我的名字叫(\S+)",
        r"我叫(\S+)",
        r"我是(\S+)",
        r"我的名字是(\S+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, user_input)
        if match:
            name = match.group(1)
            USER_IDENTITY_CACHE[user_id] = {"name": name}
            print(f"[身份提取] 识别到用户名: {name}")
            return name
    return None


def resolve_pronouns(user_input: str, user_id: str) -> str:
    """
    将代词"我"替换为用户名（如果已知）
    
    Args:
        user_input: 用户输入
        user_id: 用户标识
        
    Returns:
        代词消解后的输入
    """
    identity = USER_IDENTITY_CACHE.get(user_id, {})
    user_name = identity.get("name")
    
    if not user_name:
        return user_input
    
    # 排除身份声明语句（不应消解）
    # 如 "我的名字叫小朱" 不应变成 "小朱的名字叫小朱"
    identity_patterns = [
        r"我的名字叫",
        r"我叫",
        r"我是",
        r"我的名字是",
    ]
    for pattern in identity_patterns:
        if re.search(pattern, user_input):
            return user_input  # 身份声明语句，不消解
    
    # 替换"我的"为"用户名的"，"我"为"用户名"
    # 注意：先替换"我的"再替换"我"，避免"我的"变成"用户名的"后又被替换
    resolved = user_input.replace("我的", f"{user_name}的")
    resolved = resolved.replace("我", user_name)
    return resolved


# =============================================================================
# 图谱关系处理模块
# =============================================================================

# 关系类型映射（英文 → 中文）
RELATION_NORMALIZE_MAP = {
    "daughter": "女儿",
    "son": "儿子",
    "has": "有",
    "has_name": "名字",
    "has_daughter": "有女儿",
    "has_son": "有儿子",
    "brother": "弟弟",
    "sister": "姐妹",
    "father": "父亲",
    "mother": "母亲",
    "parent": "父母",
    "child": "孩子",
    "name": "名字",
    "states_that": "陈述",
    "responds_to_query_about": "回应查询",
}


def normalize_relation_type(rel_type: str) -> str:
    """
    归一化关系类型（英文 → 中文）
    
    Args:
        rel_type: 原始关系类型
        
    Returns:
        归一化后的关系类型
    """
    return RELATION_NORMALIZE_MAP.get(rel_type.lower(), rel_type)


def dedupe_relations(relations: list) -> list:
    """
    对图谱关系进行去重
    
    Args:
        relations: 原始关系列表
        
    Returns:
        去重后的关系列表
    """
    seen = set()
    deduped = []
    for rel in relations:
        # 生成唯一键
        if isinstance(rel, dict):
            source = rel.get("source", "?")
            relationship = rel.get("relationship", "?")
            target = rel.get("target", "?")
            
            # 处理嵌套字典格式
            if isinstance(source, dict):
                source = source.get("name", source.get("id", "?"))
            if isinstance(relationship, dict):
                relationship = relationship.get("type", relationship.get("name", "?"))
            if isinstance(target, dict):
                target = target.get("name", target.get("id", "?"))
            
            # 归一化关系类型
            relationship = normalize_relation_type(str(relationship))
            
            key = f"{source}|{relationship}|{target}"
        else:
            key = str(rel)
        
        if key not in seen:
            seen.add(key)
            deduped.append(rel)
    return deduped


# =============================================================================
# 意图判断模块
# =============================================================================

class IntentResult(BaseModel):
    """意图判断结果"""
    intent: Literal["personal", "factual", "general"]
    reasoning: str
    needs_external_search: bool


def classify_intent(user_input: str) -> IntentResult:
    """
    通过 DeepSeek LLM 判断用户输入的意图类型
    
    意图类型:
    - personal: 个人信息/记忆查询（如家庭关系、个人偏好等）
    - factual: 需要外部事实知识的查询（如历史事件、科学知识等）
    - general: 通用对话/闲聊
    
    Returns:
        IntentResult: 包含意图类型、推理过程和是否需要外部搜索的结构化结果
    """
    import json
    import re
    from langchain_openai import ChatOpenAI
    
    llm = ChatOpenAI(
        model="deepseek-chat",
        temperature=0.0,
        base_url=DEEPSEEK_CONFIG["base_url"],
        api_key=DEEPSEEK_API_KEY,
    )
    
    prompt = f"""分析以下用户输入，判断其意图类型。

用户输入: "{user_input}"

意图类型说明:
1. personal - 涉及个人信息、记忆、关系的查询
   - 例如: "我的名字叫什么"、"小朱的儿子是谁"、"我喜欢什么颜色"
   - 这类查询应该从本地记忆中检索，不需要外部搜索

2. factual - 需要外部事实知识的查询
   - 例如: "谁发明了电灯"、"Python的最新版本是什么"、"今天天气如何"
   - 这类查询可能需要外部搜索或最新信息

3. general - 通用对话或闲聊
   - 例如: "你好"、"谢谢"、"帮我写一首诗"
   - 不需要特定知识检索

请以 JSON 格式返回结果，格式如下：
```json
{{
  "intent": "personal/factual/general 三选一",
  "reasoning": "你的推理过程",
  "needs_external_search": true/false
}}
```

只返回 JSON，不要有其他内容。"""

    response = llm.invoke(prompt)
    content = response.content.strip()
    
    # 提取 JSON（处理可能的 markdown 代码块包装）
    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = content
    
    try:
        data = json.loads(json_str)
        return IntentResult(
            intent=data.get("intent", "general"),
            reasoning=data.get("reasoning", "无法解析推理过程"),
            needs_external_search=data.get("needs_external_search", False),
        )
    except json.JSONDecodeError as e:
        print(f"[警告] 意图解析失败: {e}")
        print(f"[警告] 原始响应: {content}")
        # 返回默认值
        return IntentResult(
            intent="general",
            reasoning="解析失败，使用默认值",
            needs_external_search=False,
        )


# =============================================================================
# LLM 工厂
# =============================================================================


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
    import time
    
    # 性能统计
    timings: dict[str, float] = {}
    total_start = time.perf_counter()
    
    print(f"\n[输入] {user_input}")

    # Step 0.5: 提取用户身份（如果有）
    step_start = time.perf_counter()
    extract_user_identity(user_input, user_id)
    
    # Step 0.6: 代词消解（用于存储和检索）
    resolved_input = resolve_pronouns(user_input, user_id)
    if resolved_input != user_input:
        print(f"[代词消解] {user_input} -> {resolved_input}")
    timings["预处理(身份+消解)"] = time.perf_counter() - step_start

    # Step 0: 意图判断 (Intent Classification)
    step_start = time.perf_counter()
    intent_result = classify_intent(resolved_input)
    timings["意图判断(LLM)"] = time.perf_counter() - step_start
    print(f"[意图分析] 类型: {intent_result.intent}")
    print(f"[意图分析] 推理: {intent_result.reasoning}")
    print(f"[意图分析] 需要外部搜索: {intent_result.needs_external_search}")

    # Step 1: 混合检索 (Hybrid Retrieval) - 使用消解后的输入
    step_start = time.perf_counter()
    search_results = brain.search(resolved_input, user_id=user_id)
    timings["混合检索(Vector+Graph)"] = time.perf_counter() - step_start

    # 调试: 打印原始返回结构
    print(f"[调试] search_results 类型: {type(search_results).__name__}")
    if isinstance(search_results, dict):
        print(f"[调试] search_results keys: {list(search_results.keys())}")

    knowledge_context = ""
    vector_memories = []
    graph_relations = []

    # 处理返回格式：graph_store 启用时返回字典，否则返回列表
    if isinstance(search_results, dict):
        vector_memories = search_results.get("results", [])
        graph_relations = search_results.get("relations", [])
    elif isinstance(search_results, list):
        vector_memories = search_results

    # 处理向量记忆
    if vector_memories:
        print("[海马体] 激活记忆:")
        for mem in vector_memories:
            if isinstance(mem, dict):
                memory_text = mem.get("memory", str(mem))
                score = mem.get("score", "N/A")
            else:
                memory_text = str(mem)
                score = "N/A"
            print(f"  - [vector] {memory_text} (score: {score})")
            knowledge_context += f"- {memory_text}\n"
    else:
        print("[海马体] 暂无相关向量记忆")

    # 处理图谱关系（先去重）
    if graph_relations:
        graph_relations = dedupe_relations(graph_relations)
        print("[图谱] 关联关系:")
        for rel in graph_relations:
            # 兼容不同的关系数据结构
            if isinstance(rel, dict):
                source = rel.get("source", "?")
                relationship = rel.get("relationship", "?")
                target = rel.get("target", "?")
                
                # 兼容字符串和字典两种格式
                if isinstance(source, dict):
                    source_name = source.get("name", source.get("id", "?"))
                else:
                    source_name = str(source)
                
                if isinstance(relationship, dict):
                    rel_type = relationship.get("type", relationship.get("name", "?"))
                else:
                    rel_type = str(relationship)
                
                # 归一化关系类型（英文 → 中文）
                rel_type = normalize_relation_type(rel_type)
                
                if isinstance(target, dict):
                    target_name = target.get("name", target.get("id", "?"))
                else:
                    target_name = str(target)
                
                relation_str = f"{source_name} --[{rel_type}]--> {target_name}"
            else:
                relation_str = str(rel)
            
            print(f"  - [graph] {relation_str}")
            knowledge_context += f"- 关系: {relation_str}\n"

    # Step 2: 深度推理 (System 2 Thinking)
    step_start = time.perf_counter()
    llm = create_chat_llm()

    # 构建用户身份上下文
    identity = USER_IDENTITY_CACHE.get(user_id, {})
    current_user_name = identity.get("name")
    identity_context = ""
    if current_user_name:
        identity_context = f"""[用户身份]
当前用户的名字是: {current_user_name}
重要：在知识网络中，"我" 等同于 "{current_user_name}"

"""

    system_prompt = f"""你是一个拥有"图谱思维"的超级智能，擅长从碎片化信息中进行深度语义推理。

{identity_context}[已提取的知识网络]
{knowledge_context if knowledge_context else "(暂无相关记忆)"}

[推理指导]
在回答问题时，请进行多层语义分析：

1. **词汇语义分析**：注意词汇的隐含语义
   - 许多词汇自带属性信息（如"弟弟"暗示男性，"女儿"暗示女性，"外婆"暗示女性且是母亲的母亲）
   - 先识别这些隐含属性，再进行推理
   - 职业、称谓、关系词都可能包含隐含信息

2. **关系传递推理**：
   - 识别具有传递性的关系
   - 例如：A 是 B 的兄弟姐妹 + B 是 C 的孩子 → A 也是 C 的孩子
   - 例如：A 是 B 的弟弟 → A 是男性 → 如果 A 是 C 的孩子 → A 是 C 的儿子

3. **推理步骤显式化**：
   - 先列出所有相关事实
   - 逐步推导，展示完整的推理链条
   - 从隐含属性得出具体结论

[指令]
1. 严格基于知识网络，不编造信息
2. 知识中的"我"指用户"{current_user_name if current_user_name else "用户"}"
3. 遇到问题时，先分析相关实体的隐含属性，再进行多跳推理
4. 展示推理链条，让结论有据可循
5. 如果确实无法确定，说明缺少哪些关键信息
"""

    response = llm.invoke([("system", system_prompt), ("user", user_input)])
    answer = response.content
    timings["深度推理(LLM)"] = time.perf_counter() - step_start

    print(f"[前额叶] 生成回答:\n{answer}")

    # Step 3: 记忆整合 (Consolidation) - 异步执行，不阻塞主流程
    texts_to_consolidate = [
        resolved_input,
        f"针对'{resolved_input}'的回答是: {answer}"
    ]
    _consolidation_executor.submit(
        _background_consolidate,
        brain,
        texts_to_consolidate,
        user_id
    )
    print("[后台] 记忆整合已提交（异步执行中）...")

    # 打印性能统计（用户感知耗时，不包含记忆整合）
    total_time = time.perf_counter() - total_start
    print(f"\n[性能统计] 用户感知耗时: {total_time:.2f}s")
    for step_name, step_time in timings.items():
        percentage = (step_time / total_time) * 100
        print(f"  - {step_name}: {step_time:.2f}s ({percentage:.1f}%)")
    print(f"  - 记忆整合: 异步执行中（约 28s，不阻塞用户）")

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
    # cognitive_process(brain, "DeepMind 是 Google 的子公司。", user_id)
    # cognitive_process(brain, "Demis Hassabis 是 DeepMind 的 CEO。", user_id)
    # cognitive_process(brain, "Gemini 是 DeepMind 团队研发的。", user_id)

    cognitive_process(brain, "我的名字叫小朱", user_id)
    cognitive_process(brain, "小朱有两个孩子", user_id)
    cognitive_process(brain, "灿灿是小朱的女儿", user_id)
    cognitive_process(brain, "灿灿还有一个弟弟，叫帅帅", user_id)


    print("\n" + "=" * 50)

    # 测试多跳推理
    print("\n--- 测试推理能力 ---")
    cognitive_process(brain, "小朱的儿子叫什么名字？", user_id)


if __name__ == "__main__":
    demo_multi_hop_reasoning()
