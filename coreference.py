"""
指代消解模块

提供两种消解方式：
1. 检索时消解（规则匹配，快速）
2. 整合时消解（LLM，准确）

LLM 按 config.LLM_PROVIDER 选择，支持 deepseek 与 gemini，与 privacy_filter 等模块一致。
"""
import json
import re
import logging
from typing import Optional

from config import COREFERENCE_CONTEXT_SIZE, LLM_PROVIDER, create_chat_llm
from session_manager import Event
from utils import extract_json_from_response

logger = logging.getLogger("neuro_memory.coreference")


class CoreferenceResolver:
    """指代消解器"""
    
    def __init__(self):
        """初始化指代消解器（按 LLM_PROVIDER 选择 DeepSeek 或 Gemini）"""
        self.llm = create_chat_llm(temperature=0.0)
        logger.info("CoreferenceResolver 初始化完成 (LLM_PROVIDER=%s)", LLM_PROVIDER)
    
    def resolve_query(self, query: str, context_events: list[Event]) -> str:
        """
        检索时消解（规则匹配，快速）
        
        检测查询中的代词，从最近事件中提取名词/人名进行替换。
        
        Args:
            query: 当前用户查询
            context_events: 最近的短期事件（用于提取上下文）
            
        Returns:
            消解后的查询
        """
        if not context_events:
            return query
        
        # 提取最近事件中的名词和人名
        context_texts = [event.content for event in context_events[-COREFERENCE_CONTEXT_SIZE:]]
        context_text = " ".join(context_texts)
        
        # 规则匹配：检测常见代词
        resolved = query
        
        # 1. "这个" / "那个" → 查找最近事件中的名词
        if "这个" in resolved or "那个" in resolved:
            # 提取名词（简单规则：中文名词通常是2-4个字）
            nouns = self._extract_nouns(context_text)
            if nouns:
                # 使用最近出现的名词
                resolved = resolved.replace("这个", nouns[-1])
                resolved = resolved.replace("那个", nouns[-1])
                logger.debug(f"消解 '这个/那个' → '{nouns[-1]}'")
        
        # 2. "她" / "他" → 查找最近事件中的人名
        if "她" in resolved or "他" in resolved:
            names = self._extract_names(context_text)
            if names:
                # 使用最近出现的人名
                name = names[-1]
                resolved = resolved.replace("她", name)
                resolved = resolved.replace("他", name)
                logger.debug(f"消解 '她/他' → '{name}'")
        
        # 3. "它" → 查找最近事件中的事物名词
        if "它" in resolved:
            nouns = self._extract_nouns(context_text)
            if nouns:
                resolved = resolved.replace("它", nouns[-1])
                logger.debug(f"消解 '它' → '{nouns[-1]}'")
        
        return resolved if resolved != query else query
    
    def _extract_nouns(self, text: str) -> list[str]:
        """
        从文本中提取名词（简单规则）
        
        规则：
        - 2-4 个中文字符
        - 不包含常见动词/形容词
        """
        # 简单规则：提取2-4个连续的中文字符
        pattern = r'[\u4e00-\u9fa5]{2,4}'
        matches = re.findall(pattern, text)
        
        # 过滤常见动词和形容词
        stop_words = {"喜欢", "想要", "需要", "可以", "应该", "能够", "开始", "结束"}
        nouns = [m for m in matches if m not in stop_words]
        # 有序去重，保留首次出现顺序，以便 nouns[-1] 表示最近出现的名词
        return list(dict.fromkeys(nouns))
    
    def _extract_names(self, text: str) -> list[str]:
        """
        从文本中提取人名（简单规则）
        
        规则：
        - 常见人名模式："XXX叫YYY"、"XXX是YYY"、"我的XXX叫YYY"
        """
        names = []
        
        # 模式1: "XXX叫YYY"
        pattern1 = r'([\u4e00-\u9fa5]{2,4})叫([\u4e00-\u9fa5]{2,4})'
        for match in re.finditer(pattern1, text):
            names.append(match.group(2))
        
        # 模式2: "XXX是YYY"
        pattern2 = r'([\u4e00-\u9fa5]{2,4})是([\u4e00-\u9fa5]{2,4})'
        for match in re.finditer(pattern2, text):
            names.append(match.group(2))
        
        # 模式3: "我的XXX叫YYY"
        pattern3 = r'我的[\u4e00-\u9fa5]{1,3}叫([\u4e00-\u9fa5]{2,4})'
        for match in re.finditer(pattern3, text):
            names.append(match.group(1))
        # 有序去重，保留首次出现顺序，以便 names[-1] 表示最近出现的人名
        return list(dict.fromkeys(names))
    
    def resolve_events(self, events: list[Event]) -> list[str]:
        """
        整合时消解（LLM，准确）
        
        使用 LLM 进行语义分组、指代消解和合并。
        
        Args:
            events: Session 中的所有事件
            
        Returns:
            消解后的记忆列表（已分组合并）
        """
        if not events:
            return []
        
        # 构建事件文本列表
        event_texts = [event.content for event in events]
        
        prompt = f"""以下是用户的一段对话历史，请帮我整合为可独立理解的记忆。

对话历史：
{json.dumps(event_texts, ensure_ascii=False, indent=2)}

要求：
1. 将相关内容分组（例如：关于同一个人的信息放一组）
2. 消解代词（如"她"→"灿灿"，"这个"→"桔子"）
3. 每组合并为一句完整的陈述
4. 确保每条记忆可以脱离上下文独立理解
5. 如果某条内容无法消解代词，则跳过该条
6. 问句通常不需要存储，可以跳过

返回 JSON 数组格式：
```json
["记忆1", "记忆2", ...]
```

只返回 JSON 数组，不要有其他内容。"""

        try:
            response = self.llm.invoke(prompt)
            content = response.content.strip()
            
            # 提取并解析 JSON
            json_str = extract_json_from_response(content)
            memories = json.loads(json_str)
            
            # 确保返回列表
            if isinstance(memories, list):
                # 过滤空字符串
                memories = [m.strip() for m in memories if m.strip()]
                logger.info(f"LLM 消解完成: {len(events)} 条事件 → {len(memories)} 条记忆")
                return memories
            else:
                logger.warning(f"LLM 返回格式错误，期望列表但得到: {type(memories)}")
                return []
                
        except json.JSONDecodeError as e:
            logger.error(f"LLM 返回的 JSON 解析失败: {e}")
            logger.debug("原始内容: %s...", (json_str[:200] if json_str else "(empty)"))
            return []
        except Exception as e:
            logger.error(f"LLM 消解失败: {e}")
            return []


# =============================================================================
# 模块级单例
# =============================================================================

_resolver_instance: Optional[CoreferenceResolver] = None


def get_coreference_resolver() -> CoreferenceResolver:
    """获取 CoreferenceResolver 单例"""
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = CoreferenceResolver()
    return _resolver_instance
