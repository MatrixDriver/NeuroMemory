"""
隐私过滤器模块 (Privacy Filter)

用于判断用户输入是否为私有数据，决定是否存储到记忆系统。
- PRIVATE: 个人偏好、经历、私有实体关系、个人计划 -> 存储
- PUBLIC: 通用知识、百科事实、公共信息 -> 不存储
"""
import json
import logging
from typing import Literal

from config import create_chat_llm
from utils import extract_json_from_response

logger = logging.getLogger("neuro_memory.privacy_filter")

PrivacyType = Literal["PRIVATE", "PUBLIC"]


class PrivacyFilter:
    """LLM 驱动的隐私分类器"""

    def __init__(self):
        self.llm = create_chat_llm(temperature=0.0)

    def _build_prompt(self, text: str) -> str:
        """构建隐私分类的 prompt"""
        return f"""判断以下用户输入是否为私有数据。

用户输入: "{text}"

分类规则：
- PRIVATE（私有数据，应该存储）:
  * 个人偏好（如"我喜欢吃苹果"）
  * 个人经历（如"我去年去了北京"）
  * 私有实体关系（如"我的女儿叫小红"）
  * 个人计划（如"我明天要开会"）
  * 个人身份信息（如"我叫张三"）

- PUBLIC（公共知识，不应存储）:
  * 通用知识（如"苹果是一种水果"）
  * 百科事实（如"北京是中国的首都"）
  * 公共信息（如"今天是周一"）
  * 问句/查询（如"小朱的儿子叫什么？"）

注意：
- 问句通常是查询，归类为 PUBLIC（不存储查询本身）
- 包含"我"或指向用户的内容通常是 PRIVATE
- 陈述性的个人信息是 PRIVATE

请以 JSON 格式返回：
```json
{{"type": "PRIVATE 或 PUBLIC", "reason": "简短的分类理由"}}
```

只返回 JSON，不要有其他内容。"""

    def _parse_response(self, content: str) -> tuple[PrivacyType, str]:
        """解析 LLM 响应，提取分类结果"""
        json_str = extract_json_from_response(content)
        data = json.loads(json_str)
        privacy_type = data.get("type", "PRIVATE").upper()
        reason = data.get("reason", "无法解析理由")

        # 确保返回值合法
        if privacy_type not in ("PRIVATE", "PUBLIC"):
            privacy_type = "PRIVATE"  # 默认保守策略：存储

        return privacy_type, reason

    def classify(self, text: str) -> tuple[PrivacyType, str]:
        """
        判断文本是否为私有数据

        Args:
            text: 用户输入文本

        Returns:
            tuple: (分类结果, 分类理由)
        """
        try:
            response = self.llm.invoke(self._build_prompt(text))
            return self._parse_response(response.content.strip())
        except Exception as e:
            logger.warning(f"隐私分类失败: {e}，默认按 PRIVATE 处理")
            return "PRIVATE", f"分类失败（{e}），默认存储"
    
    async def classify_async(self, text: str) -> tuple[PrivacyType, str]:
        """
        异步版本的隐私分类

        Args:
            text: 用户输入文本

        Returns:
            tuple: (分类结果, 分类理由)
        """
        try:
            response = await self.llm.ainvoke(self._build_prompt(text))
            return self._parse_response(response.content.strip())
        except Exception as e:
            logger.warning(f"异步隐私分类失败: {e}，默认按 PRIVATE 处理")
            return "PRIVATE", f"分类失败（{e}），默认存储"


# 模块级单例
_filter_instance: PrivacyFilter | None = None


def get_privacy_filter() -> PrivacyFilter:
    """获取隐私过滤器单例"""
    global _filter_instance
    if _filter_instance is None:
        _filter_instance = PrivacyFilter()
    return _filter_instance


def classify_privacy(text: str) -> tuple[PrivacyType, str]:
    """
    便捷函数：判断文本是否为私有数据
    
    Args:
        text: 用户输入文本
        
    Returns:
        tuple: (分类结果 "PRIVATE"/"PUBLIC", 分类理由)
    """
    return get_privacy_filter().classify(text)
