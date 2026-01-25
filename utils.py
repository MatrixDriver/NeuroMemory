"""
NeuroMemory 工具函数模块
"""
import re


def extract_json_from_response(content: str) -> str:
    """
    从 LLM 响应中提取 JSON 字符串。

    支持两种格式：
    1. Markdown 代码块：```json ... ``` 或 ``` ... ```
    2. 纯 JSON 文本

    Args:
        content: LLM 原始响应内容

    Returns:
        提取出的 JSON 字符串（未解析）
    """
    json_match = re.search(r'```(?:json)?\s*(.*?)\s*```', content, re.DOTALL)
    return json_match.group(1) if json_match else content
