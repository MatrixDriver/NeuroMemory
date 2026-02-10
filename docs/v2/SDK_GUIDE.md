# NeuroMemory Python SDK 使用指南

> **版本**: v2.0
> **Python 版本**: 3.10+
> **最后更新**: 2026-02-10

---

## 目录

1. [安装](#1-安装)
2. [快速开始](#2-快速开始)
3. [客户端初始化](#3-客户端初始化)
4. [偏好管理](#4-偏好管理)
5. [记忆管理](#5-记忆管理)
6. [语义检索](#6-语义检索)
7. [时间查询](#7-时间查询)
8. [错误处理](#8-错误处理)
9. [高级用法](#9-高级用法)

---

## 1. 安装

### 1.1 从 PyPI 安装（推荐）

```bash
pip install neuromemory-client
```

### 1.2 从源码安装

```bash
# 克隆仓库
git clone https://github.com/your-repo/NeuroMemory.git
cd NeuroMemory

# 安装 SDK（开发模式）
pip install -e sdk/
```

### 1.3 依赖项

SDK 依赖以下库：
- `httpx >= 0.25.0` - HTTP 客户端
- `pydantic >= 2.0.0` - 数据验证

---

## 2. 快速开始

### 2.1 获取 API Key

首先需要注册租户并获取 API Key：

```python
import httpx

response = httpx.post(
    "http://localhost:8765/v1/tenants/register",
    json={
        "name": "MyCompany",
        "email": "admin@example.com"
    }
)
data = response.json()
api_key = data["api_key"]  # 保存此 Key
print(f"Your API Key: {api_key}")
```

### 2.2 基础示例

```python
from neuromemory_client import NeuroMemoryClient

# 初始化客户端
client = NeuroMemoryClient(
    api_key="nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="http://localhost:8765"
)

# 设置用户偏好
client.preferences.set(
    user_id="alice",
    key="language",
    value="zh-CN"
)

# 添加记忆
client.add_memory(
    user_id="alice",
    content="I work at ABC Company as a software engineer",
    memory_type="fact"
)

# 语义检索
results = client.search(
    user_id="alice",
    query="Where does Alice work?",
    limit=5
)

print(results)
```

---

## 3. 客户端初始化

### 3.1 基础初始化

```python
from neuromemory_client import NeuroMemoryClient

client = NeuroMemoryClient(
    api_key="nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    base_url="http://localhost:8765",  # API 地址
    timeout=30.0  # 请求超时时间（秒）
)
```

### 3.2 参数说明

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| api_key | str | 是 | - | API 密钥（nm_ 开头） |
| base_url | str | 否 | http://localhost:8765 | API 基础地址 |
| timeout | float | 否 | 30.0 | 请求超时时间（秒） |

### 3.3 上下文管理器

推荐使用 `with` 语句自动关闭连接：

```python
with NeuroMemoryClient(api_key="nm_xxx") as client:
    client.preferences.set(user_id="alice", key="lang", value="en")
    # 离开 with 块时自动调用 client.close()
```

手动管理连接：

```python
client = NeuroMemoryClient(api_key="nm_xxx")
try:
    # 使用客户端
    pass
finally:
    client.close()  # 关闭 HTTP 连接
```

---

## 4. 偏好管理

偏好用于存储用户的配置和设置（如语言、主题、通知偏好等）。

### 4.1 设置偏好

```python
# 字符串值
client.preferences.set(
    user_id="alice",
    key="language",
    value="zh-CN"
)

# 数字值
client.preferences.set(
    user_id="alice",
    key="notification_interval",
    value=3600
)

# 对象值（会转换为 JSON）
client.preferences.set(
    user_id="alice",
    key="theme",
    value={
        "mode": "dark",
        "primary_color": "#007bff",
        "font_size": 14
    }
)
```

### 4.2 获取偏好

```python
# 获取单个偏好
pref = client.preferences.get(user_id="alice", key="language")
print(pref["value"])  # "zh-CN"

# 列出所有偏好
all_prefs = client.preferences.list(user_id="alice")
for pref in all_prefs:
    print(f"{pref['key']}: {pref['value']}")
```

### 4.3 删除偏好

```python
client.preferences.delete(user_id="alice", key="language")
```

### 4.4 偏好响应格式

```python
{
    "id": "uuid",
    "user_id": "alice",
    "key": "language",
    "value": "zh-CN",
    "created_at": "2026-02-10T08:00:00Z",
    "updated_at": "2026-02-10T08:00:00Z"
}
```

---

## 5. 记忆管理

### 5.1 添加记忆

```python
# 基础用法
memory = client.add_memory(
    user_id="alice",
    content="I work at ABC Company as a software engineer"
)

# 带记忆类型
memory = client.add_memory(
    user_id="alice",
    content="My favorite color is blue",
    memory_type="preference"
)

# 带元数据
memory = client.add_memory(
    user_id="alice",
    content="Attended team meeting on 2026-02-10",
    memory_type="episodic",
    metadata={
        "source": "calendar",
        "event_type": "meeting",
        "participants": ["bob", "charlie"]
    }
)
```

### 5.2 记忆类型建议

| 类型 | 说明 | 示例 |
|------|------|------|
| `fact` | 事实性知识 | "Python 是一种编程语言" |
| `episodic` | 事件记录 | "昨天参加了项目会议" |
| `preference` | 用户偏好 | "我喜欢喝咖啡" |
| `general` | 通用记忆（默认） | 其他类型的记忆 |

### 5.3 记忆响应格式

```python
{
    "id": "uuid",
    "user_id": "alice",
    "content": "...",
    "memory_type": "fact",
    "metadata": {...},
    "created_at": "2026-02-10T08:00:00Z"
}
```

---

## 6. 语义检索

### 6.1 基础检索

```python
# 简单查询
results = client.search(
    user_id="alice",
    query="Where does Alice work?"
)

for result in results:
    print(f"[{result['similarity']:.2f}] {result['content']}")
```

### 6.2 限制结果数量

```python
results = client.search(
    user_id="alice",
    query="work",
    limit=3  # 最多返回 3 条结果
)
```

### 6.3 按类型过滤

```python
results = client.search(
    user_id="alice",
    query="preferences",
    memory_type="preference"  # 只搜索偏好类型
)
```

### 6.4 时间范围过滤

```python
from datetime import datetime, timezone

results = client.search(
    user_id="alice",
    query="meetings",
    created_after=datetime(2026, 1, 1, tzinfo=timezone.utc),
    created_before=datetime(2026, 2, 1, tzinfo=timezone.utc)
)
```

### 6.5 完整示例

```python
from datetime import datetime, timezone

results = client.search(
    user_id="alice",
    query="project discussions",
    limit=10,
    memory_type="episodic",
    created_after=datetime(2026, 1, 1, tzinfo=timezone.utc)
)

print(f"Found {len(results)} results:\n")
for i, result in enumerate(results, 1):
    print(f"{i}. [{result['similarity']:.3f}] {result['content']}")
    print(f"   Created: {result['created_at']}\n")
```

### 6.6 检索响应格式

```python
[
    {
        "id": "uuid",
        "user_id": "alice",
        "content": "I work at ABC Company",
        "memory_type": "fact",
        "metadata": {...},
        "created_at": "2026-02-10T08:00:00Z",
        "similarity": 0.89  # 相似度分数 (0-1)
    }
]
```

---

## 7. 时间查询

### 7.1 时间范围查询

查询指定时间区间内的所有记忆：

```python
from datetime import datetime, timezone

result = client.memory.get_by_time_range(
    user_id="alice",
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 1, 31, 23, 59, 59, tzinfo=timezone.utc),
    memory_type="fact",
    limit=50,
    offset=0
)

print(f"Total: {result['total']} memories")
print(f"Showing: {len(result['memories'])} memories")

for memory in result['memories']:
    print(f"- {memory['content']}")
```

### 7.2 最近记忆查询

便捷方法，查询最近 N 天的记忆：

```python
# 最近 7 天的记忆
memories = client.get_recent_memories(
    user_id="alice",
    days=7,
    limit=50
)

# 最近 30 天的特定类型记忆
memories = client.get_recent_memories(
    user_id="alice",
    days=30,
    memory_types=["fact", "episodic"],
    limit=100
)
```

或使用 MemoryClient：

```python
memories = client.memory.get_recent(
    user_id="alice",
    days=7,
    memory_types=["fact"],
    limit=50
)
```

### 7.3 时间线聚合

按日/周/月统计记忆数量：

```python
from datetime import date

# 按日统计
timeline = client.get_memory_timeline(
    user_id="alice",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
    granularity="day"
)

print(f"Total memories: {timeline['total_memories']}")
for stat in timeline['data']:
    print(f"{stat['date']}: {stat['count']} memories")
    print(f"  Types: {stat['memory_types']}")
```

或使用 MemoryClient：

```python
timeline = client.memory.get_timeline(
    user_id="alice",
    start_date=date(2026, 1, 1),
    end_date=date(2026, 1, 31),
    granularity="week"  # day, week, month
)
```

---

## 8. 错误处理

### 8.1 HTTP 错误

SDK 使用 `httpx` 库，错误通过异常抛出：

```python
import httpx

try:
    result = client.search(
        user_id="alice",
        query="test"
    )
except httpx.HTTPStatusError as e:
    print(f"HTTP Error: {e.response.status_code}")
    print(f"Detail: {e.response.json()['detail']}")
except httpx.RequestError as e:
    print(f"Request Error: {e}")
```

### 8.2 常见错误处理

```python
from datetime import datetime, timezone
import httpx

try:
    # 可能抛出异常的操作
    result = client.memory.get_by_time_range(
        user_id="alice",
        start_time=datetime(2026, 2, 1, tzinfo=timezone.utc),
        end_time=datetime(2026, 1, 1, tzinfo=timezone.utc)  # 错误：结束时间早于开始时间
    )
except httpx.HTTPStatusError as e:
    if e.response.status_code == 400:
        print("Invalid parameters:", e.response.json()["detail"])
    elif e.response.status_code == 401:
        print("Authentication failed. Check your API key.")
    elif e.response.status_code == 404:
        print("Resource not found.")
    elif e.response.status_code == 500:
        print("Server error. Please try again later.")
    else:
        print(f"Unexpected error: {e}")
except httpx.RequestError as e:
    print(f"Connection error: {e}")
```

### 8.3 重试机制

实现简单的重试逻辑：

```python
import time
import httpx

def search_with_retry(client, user_id, query, max_retries=3):
    for attempt in range(max_retries):
        try:
            return client.search(user_id=user_id, query=query)
        except httpx.HTTPStatusError as e:
            if e.response.status_code >= 500 and attempt < max_retries - 1:
                print(f"Retry {attempt + 1}/{max_retries} after server error...")
                time.sleep(2 ** attempt)  # 指数退避
            else:
                raise
        except httpx.RequestError as e:
            if attempt < max_retries - 1:
                print(f"Retry {attempt + 1}/{max_retries} after connection error...")
                time.sleep(2 ** attempt)
            else:
                raise
```

---

## 9. 高级用法

### 9.1 批量添加记忆

```python
memories = [
    {"content": "Python is a programming language", "memory_type": "fact"},
    {"content": "Java is also a programming language", "memory_type": "fact"},
    {"content": "I prefer Python over Java", "memory_type": "preference"},
]

for mem in memories:
    client.add_memory(
        user_id="alice",
        content=mem["content"],
        memory_type=mem["memory_type"]
    )
    print(f"Added: {mem['content']}")
```

### 9.2 分页查询

```python
def get_all_memories_in_range(client, user_id, start_time, end_time):
    """分页获取时间范围内的所有记忆"""
    all_memories = []
    offset = 0
    limit = 100

    while True:
        result = client.memory.get_by_time_range(
            user_id=user_id,
            start_time=start_time,
            end_time=end_time,
            limit=limit,
            offset=offset
        )

        all_memories.extend(result['memories'])

        if len(result['memories']) < limit:
            break  # 没有更多数据

        offset += limit

    return all_memories

# 使用
from datetime import datetime, timezone

all_memories = get_all_memories_in_range(
    client,
    user_id="alice",
    start_time=datetime(2026, 1, 1, tzinfo=timezone.utc),
    end_time=datetime(2026, 12, 31, tzinfo=timezone.utc)
)
print(f"Total: {len(all_memories)} memories")
```

### 9.3 自定义 HTTP 客户端

如果需要更多控制（如自定义代理、TLS 配置）：

```python
import httpx
from neuromemory_client import NeuroMemoryClient

# 创建自定义 httpx 客户端
http_client = httpx.Client(
    base_url="http://localhost:8765/v1",
    headers={"Authorization": "Bearer nm_xxx"},
    timeout=30.0,
    proxies="http://proxy.example.com:8080",
    verify=True  # TLS 验证
)

# 注意：需要手动管理客户端
# 当前 SDK 不支持注入自定义 httpx 客户端
# 这是一个潜在的扩展点
```

### 9.4 健康检查

在应用启动时检查服务可用性：

```python
def check_service_health(base_url):
    """检查 NeuroMemory 服务健康状态"""
    import httpx

    try:
        response = httpx.get(f"{base_url}/v1/health", timeout=5.0)
        response.raise_for_status()
        health = response.json()

        if health["status"] == "healthy":
            print("✓ Service is healthy")
            return True
        else:
            print(f"✗ Service is unhealthy: {health}")
            return False
    except Exception as e:
        print(f"✗ Service unavailable: {e}")
        return False

# 使用
if check_service_health("http://localhost:8765"):
    client = NeuroMemoryClient(api_key="nm_xxx")
    # 继续使用客户端
else:
    print("Please start the NeuroMemory service first")
```

### 9.5 用户记忆概览

获取用户的记忆统计信息：

```python
overview = client.get_user_memories(user_id="alice")

print(f"User: {overview['user_id']}")
print(f"Total memories: {overview['total_memories']}")
print(f"Memory types: {overview['memory_types']}")
print(f"Date range: {overview['earliest_memory']} to {overview['latest_memory']}")
```

---

## 附录

### A. 完整示例

```python
from neuromemory_client import NeuroMemoryClient
from datetime import datetime, date, timezone
import httpx

def main():
    # 初始化客户端
    client = NeuroMemoryClient(
        api_key="nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        base_url="http://localhost:8765"
    )

    try:
        # 1. 设置偏好
        client.preferences.set(
            user_id="alice",
            key="language",
            value="zh-CN"
        )
        print("✓ Preference set")

        # 2. 添加记忆
        memory = client.add_memory(
            user_id="alice",
            content="I work at ABC Company as a software engineer",
            memory_type="fact"
        )
        print(f"✓ Memory added: {memory['id']}")

        # 3. 语义检索
        results = client.search(
            user_id="alice",
            query="workplace",
            limit=5
        )
        print(f"✓ Search found {len(results)} results")

        # 4. 时间查询
        recent = client.get_recent_memories(
            user_id="alice",
            days=7
        )
        print(f"✓ Recent memories: {len(recent)}")

        # 5. 时间线统计
        timeline = client.get_memory_timeline(
            user_id="alice",
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 10)
        )
        print(f"✓ Timeline: {timeline['total_memories']} total")

    except httpx.HTTPStatusError as e:
        print(f"✗ HTTP Error: {e.response.status_code}")
        print(f"  Detail: {e.response.json()['detail']}")
    except Exception as e:
        print(f"✗ Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    main()
```

### B. 环境变量配置

推荐使用环境变量管理 API Key：

```python
import os
from neuromemory_client import NeuroMemoryClient

client = NeuroMemoryClient(
    api_key=os.environ["NEUROMEMORY_API_KEY"],
    base_url=os.environ.get("NEUROMEMORY_BASE_URL", "http://localhost:8765")
)
```

`.env` 文件：
```bash
NEUROMEMORY_API_KEY=nm_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
NEUROMEMORY_BASE_URL=http://localhost:8765
```

### C. 类型提示

SDK 返回的数据是字典（dict），可以使用类型提示增强代码可读性：

```python
from typing import Dict, List, Any

def process_search_results(results: List[Dict[str, Any]]) -> None:
    for result in results:
        content: str = result["content"]
        similarity: float = result["similarity"]
        print(f"[{similarity:.2f}] {content}")
```

---

**文档维护**: 本文档与 SDK 代码同步更新。如有问题，请提交 Issue。
