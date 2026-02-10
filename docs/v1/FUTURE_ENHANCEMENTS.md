# 未来增强计划

> 创建日期：2026-01-21

## 方案 C：混合知识增强方案

### 背景

当前系统使用"方案 B - 推理时深度语义分析"来处理隐含知识推理。该方案通过改进 LLM prompt 引导深度推理，但存在以下局限：

1. 每次查询都需要 LLM 进行深度推理，增加延迟
2. 推理质量依赖 LLM 能力，可能不稳定
3. 隐含知识没有被显式存储，无法被向量检索直接命中

### 方案概述

**混合方案**结合两个阶段的优化：

1. **存储时轻量级增强**：提取高置信度的核心属性
2. **推理时深度分析**：处理复杂的多跳推理

### 实施前提

- [ ] 性能优化任务完成（参见 [PERFORMANCE_OPTIMIZATION.md](./PERFORMANCE_OPTIMIZATION.md)）
- [ ] `brain.add()` 耗时降低到可接受范围（< 5 秒）

---

## 详细设计

### 阶段 1：存储时轻量级增强

在 `brain.add()` 之前，快速提取高置信度的核心属性。

#### 实现方式 A：规则引擎（推荐，快速）

```python
# main.py 新增函数

# 性别指示词映射
GENDER_INDICATORS = {
    # 关系词 → (性别, 实体位置)
    # 位置: 0 = 主语, 1 = 宾语
    "弟弟": ("男", 1),
    "哥哥": ("男", 1),
    "妹妹": ("女", 1),
    "姐姐": ("女", 1),
    "儿子": ("男", 0),
    "女儿": ("女", 0),
    "父亲": ("男", 0),
    "母亲": ("女", 0),
    "爸爸": ("男", 0),
    "妈妈": ("女", 0),
    "丈夫": ("男", 0),
    "妻子": ("女", 0),
    "外公": ("男", 0),
    "外婆": ("女", 0),
    "爷爷": ("男", 0),
    "奶奶": ("女", 0),
}


def extract_implicit_attributes(text: str) -> list[str]:
    """
    快速提取文本中的隐含属性（基于规则）
    
    Args:
        text: 输入文本
        
    Returns:
        隐含属性列表
        
    Example:
        输入: "灿灿有一个弟弟叫帅帅"
        输出: ["帅帅是男性"]
    """
    import re
    
    attributes = []
    
    for keyword, (gender, position) in GENDER_INDICATORS.items():
        if keyword in text:
            # 尝试提取实体名
            if position == 1:  # 宾语位置
                # 模式: "X的弟弟叫Y" 或 "X有一个弟弟叫Y"
                pattern = rf"(?:的|有(?:一个)?){keyword}(?:叫|是|名叫)?(\S+)"
            else:  # 主语位置
                # 模式: "X是Y的儿子"
                pattern = rf"(\S+)是\S+的{keyword}"
            
            match = re.search(pattern, text)
            if match:
                entity = match.group(1)
                # 清理实体名（移除标点等）
                entity = re.sub(r'[，。！？、]', '', entity)
                if entity:
                    attributes.append(f"{entity}是{gender}性")
    
    return attributes
```

#### 修改 cognitive_process

```python
# Step 3: 记忆整合 - 增强版
step_start = time.perf_counter()
try:
    # 提取隐含属性
    implicit_attrs = extract_implicit_attributes(resolved_input)
    
    # 存储原始输入
    brain.add(resolved_input, user_id=user_id)
    
    # 存储隐含属性
    for attr in implicit_attrs:
        brain.add(attr, user_id=user_id)
        print(f"[知识增强] 提取隐含属性: {attr}")
    
    # 存储回答
    brain.add(f"针对'{resolved_input}'的回答是: {answer}", user_id=user_id)
    print("[后台] 知识图谱已更新。")
except Exception as e:
    print(f"[警告] 记忆保存时出错: {e}")
```

#### 实现方式 B：LLM 提取（精准但慢）

```python
def extract_implicit_attributes_llm(text: str) -> list[str]:
    """
    通过 LLM 提取隐含属性（更精准但更慢）
    """
    prompt = f"""分析以下文本，提取其中隐含的属性信息。

文本: "{text}"

只提取高置信度的隐含属性，例如：
- 从"弟弟"推断男性
- 从"女演员"推断女性
- 从"医生爸爸"推断职业和性别

返回 JSON 数组，每个元素是一条属性陈述。
只返回确定性极高的推导，不要过度推测。
如果没有可提取的隐含属性，返回空数组 []。
"""
    # 调用 LLM...
```

### 阶段 2：推理时深度分析

保持当前方案 B 的 prompt 策略，处理复杂的多跳推理。

---

## 预期效果

| 场景 | 当前方案 B | 混合方案 C |
|------|-----------|-----------|
| "帅帅是男性吗？" | 需要 LLM 推理 | 直接检索命中 |
| "小朱的儿子是谁？" | 需要多跳推理 | 检索"帅帅是男性" + 简单推理 |
| 存储耗时 | 基准 | 增加 ~10%（规则方式） |

## 风险与缓解

1. **存储冗余**：隐含属性可能与显式信息重复
   - 缓解：去重检查

2. **错误推导**：规则可能在特殊语境下失效
   - 缓解：只提取高置信度属性，保守策略

3. **性能影响**：额外的存储操作
   - 缓解：先解决性能问题，再实施此方案

---

## 实施计划

1. 完成性能优化（PERFORMANCE_OPTIMIZATION.md）
2. 实现 `extract_implicit_attributes()` 规则引擎
3. 修改 `cognitive_process()` 集成知识增强
4. 测试验证效果
5. 可选：实现 LLM 提取版本作为备选
