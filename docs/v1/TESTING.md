# 测试指南

> 返回 [主架构文档](ARCHITECTURE.md)

---

## 概述

NeuroMemory 提供基于 pytest 的测试套件，验证 Y 型分流架构的核心功能：

**测试重点：**
- 隐私过滤：PRIVATE 数据存储，PUBLIC 数据丢弃
- 检索功能：向量检索 + 图谱检索
- Y 型分流：同步检索 + 异步存储决策
- JSON 输出格式验证

**架构特点：**
- 只检索，不推理（推理交给调用方的主 LLM）
- 不依赖网络服务，直接调用 `PrivateBrain` 核心类
- 支持单元测试、集成测试和端到端测试

---

## 环境准备

### 1. 安装测试依赖

```powershell
# 使用 uv（推荐）
uv pip install -e ".[dev]"

# 或使用 pip
pip install -e ".[dev]"
```

### 2. 确保服务运行

测试需要 Neo4j 和 Qdrant 服务：

**重要**：在 Windows 上，必须先启动 **Docker Desktop**，然后才能运行 docker-compose 命令。

```powershell
# 1. 启动 Docker Desktop（如果未运行）
#    在开始菜单搜索 "Docker Desktop" 并启动
#    等待 Docker Desktop 完全启动（系统托盘图标显示为运行中）

# 2. 验证 Docker 是否可用
docker --version
docker ps

# 3. 启动数据库服务
docker-compose up -d

# 4. 确认服务状态为 running
docker-compose ps
```

**故障排除**：

1. **Docker Desktop 连接错误**：
   - 如果遇到 `open //./pipe/dockerDesktopLinuxEngine: The system cannot find the file specified` 错误，说明 Docker Desktop 未运行，请先启动 Docker Desktop
   - 如果 PowerShell 会话是在 Docker Desktop 启动前打开的，可能需要关闭并重新打开 PowerShell

2. **端口无法连接**：
   - 如果 Docker Desktop 显示容器在运行，但测试仍无法连接到 `localhost:6400` 或 `localhost:17687`：
     - 在 Docker Desktop 中查看容器日志（点击容器 → Logs 标签），检查服务是否正常启动
     - 尝试重启容器：在 Docker Desktop 中停止并重新启动 `neuromemory` 项目
     - 检查端口是否被占用：`netstat -ano | findstr ":6400"`
     - 等待 10-20 秒让服务完全启动后再运行测试

3. **容器状态异常**：
   - 如果容器频繁重启或状态异常，检查 Docker Desktop 的资源设置（Settings → Resources）
   - 确保有足够的内存和 CPU 资源分配给容器

### 3. 配置环境变量

确保 `.env` 文件包含必要的 API 密钥：

```
DEEPSEEK_API_KEY=your-key-here
GOOGLE_API_KEY=your-key-here
```

---

## 运行测试

### 基本命令

**重要**：在 Windows PowerShell 下，需要使用 `uv run pytest` 或先激活虚拟环境。

**方式 1：使用 uv run（推荐）**
```powershell
# 运行所有测试（默认显示完整输出）
uv run pytest

# 运行特定测试文件
uv run pytest tests/test_cognitive.py

# 运行特定测试类
uv run pytest tests/test_cognitive.py::TestPrivacyFilter

# 运行特定测试方法
uv run pytest tests/test_cognitive.py::TestMultiHopRetrieval::test_family_relationship_retrieval
```

**方式 2：激活虚拟环境后运行**
```powershell
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_cognitive.py
```

### 常用选项

| 选项 | 说明 |
|------|------|
| `-v` | 详细输出模式（已默认启用） |
| `-s` | 显示 print 输出（已默认启用） |
| `-x` | 遇到第一个失败就停止 |
| `--tb=short` | 简短的错误追踪信息 |
| `-k "关键词"` | 按名称筛选测试 |

### 按标记运行

```powershell
# 跳过慢速测试（只运行单元测试，不调用 LLM）
uv run pytest -m "not slow"

# 只运行慢速测试（需要 LLM 调用）
uv run pytest -m slow
```

### 指定测试目标服务器

通过 `--target` 参数可以指定测试目标服务器：

```powershell
# 测试本地 Docker Desktop（默认）
uv run pytest tests/test_cognitive.py

# 明确指定本地
uv run pytest tests/test_cognitive.py --target local

# 测试 Railway 远程服务器
# 配置已在 config.py 中设置默认值，无需设置环境变量
uv run pytest tests/test_cognitive.py --target railway
```

**说明**：
- `--target local`：使用本地 Docker Desktop 中的数据库（localhost）
- `--target railway`：使用 Railway 远程服务器中的数据库
- 默认值为 `local`，如果不指定参数则测试本地环境

**Railway 远程测试配置**：
- Railway 测试配置在 `config.py` 中的 `RAILWAY_TEST_CONFIG` 中设置，包含默认值：
  - `base_url`: `https://<your-app>.up.railway.app`
  - `neo4j_host`: `neo4j-neuromemory` (Railway 内部服务名称)
  - `qdrant_host`: `qdrant-neuromemory` (Railway 内部服务名称)
  - `neo4j_password`: `railway2025`
- 这些默认值很少修改，如需临时覆盖，可通过环境变量设置（如 `$env:RAILWAY_NEO4J_HOST="..."`）

---

## 测试结构

```
tests/
├── __init__.py
└── test_cognitive.py      # 认知流程测试
```

### 测试类说明

| 测试类 | 类型 | 说明 | 需要 LLM |
|--------|------|------|----------|
| `TestIdentityExtraction` | 单元测试 | 用户身份提取功能 | No |
| `TestPronounResolution` | 单元测试 | 代词消解功能 | No |
| `TestPrivacyFilter` | 集成测试 | 隐私分类（PRIVATE/PUBLIC） | Yes |
| `TestPrivateBrain` | 集成测试 | 核心功能（检索、存储、JSON 格式） | Yes |
| `TestYSplitFlow` | 端到端测试 | Y 型分流完整流程 | Yes |
| `TestMultiHopRetrieval` | 端到端测试 | 多跳检索能力 | Yes |
| `TestPerformance` | 性能测试 | 响应时间验证 | Yes |

---

## 测试示例

### 快速验证（不调用 LLM）

```powershell
pytest -m "not slow" -v
```

预期输出：

```
tests/test_cognitive.py::TestIdentityExtraction::test_extract_name_pattern_1 PASSED
tests/test_cognitive.py::TestIdentityExtraction::test_extract_name_pattern_2 PASSED
tests/test_cognitive.py::TestIdentityExtraction::test_extract_name_pattern_3 PASSED
tests/test_cognitive.py::TestIdentityExtraction::test_no_identity_in_input PASSED
tests/test_cognitive.py::TestPronounResolution::test_resolve_my PASSED
tests/test_cognitive.py::TestPronounResolution::test_resolve_me PASSED
tests/test_cognitive.py::TestPronounResolution::test_skip_identity_statement PASSED
tests/test_cognitive.py::TestPronounResolution::test_no_identity_no_resolution PASSED
```

### 隐私过滤测试

```powershell
uv run pytest tests/test_cognitive.py::TestPrivacyFilter -v -s
```

预期输出：

```
--- 测试个人信息分类 ---
类型: PRIVATE
理由: 这是用户在陈述自己的名字，属于个人身份信息

--- 测试公共事实分类 ---
类型: PUBLIC
理由: 这是一个公共常识，不是个人私有信息

--- 测试查询问句分类 ---
类型: PUBLIC
理由: 这是一个查询问句，不是个人信息陈述
```

### Y 型分流测试

```powershell
uv run pytest tests/test_cognitive.py::TestYSplitFlow::test_private_data_stored -v -s
```

预期输出（调试模式）：

```
============================================================
测试：私有数据应被存储
============================================================

>>> 输入私有数据: 我叫测试用户_abc123

=== 检索过程 ===
[向量检索] 查询: "我叫测试用户_abc123"
  - 无匹配结果

[图谱检索]
  - 无关联关系

=== 存储决策 ===
[LLM 分类] 类型: PRIVATE
[分类理由] 这是用户在陈述自己的名字，属于个人身份信息
[决策] 存储

=== 性能统计 ===
- 检索耗时: 45ms
- 隐私分类耗时: 520ms
- 总耗时: 565ms

=== 原始数据 ===
向量结果数量: 0
图谱关系数量: 0
```

### 多跳检索测试

```powershell
uv run pytest tests/test_cognitive.py::TestMultiHopRetrieval::test_family_relationship_retrieval -v -s
```

预期输出：

```
============================================================
测试：家庭关系检索
============================================================

--- 阶段 1: 构建记忆 ---
>>> 存储: 小朱有两个孩子
>>> 存储: 灿灿是小朱的女儿
>>> 存储: 灿灿还有一个弟弟叫帅帅

[等待索引更新...]

--- 阶段 2: 测试检索 ---
>>> 查询: 小朱的儿子叫什么名字

检索结果:
  - 向量记忆数: 3
  - 图谱关系数: 2

  向量记忆:
    - 灿灿还有一个弟弟叫帅帅 (score: 0.87)
    - 小朱有两个孩子 (score: 0.82)
    - 灿灿是小朱的女儿 (score: 0.78)

  图谱关系:
    - 小朱 --[女儿]--> 灿灿
    - 灿灿 --[弟弟]--> 帅帅

✓ 检索到相关信息: True

提示：调用方 LLM 可根据以上信息推理出：
  帅帅是灿灿的弟弟 → 帅帅是男性 → 帅帅是小朱的儿子
```

---

## 直接运行测试文件

也可以直接运行测试文件（不通过 pytest 命令）：

```powershell
uv run python tests/test_cognitive.py
```

---

## 添加新测试

### 示例：添加隐私过滤测试

```python
# tests/test_cognitive.py

class TestPrivacyFilter:
    
    @pytest.mark.slow
    def test_my_new_privacy_case(self):
        """测试新的隐私分类场景"""
        from privacy_filter import classify_privacy
        
        print("\n--- 测试新场景 ---")
        privacy_type, reason = classify_privacy("我明天要去北京出差")
        print(f"类型: {privacy_type}")
        print(f"理由: {reason}")
        
        # 个人计划应被分类为 PRIVATE
        assert privacy_type == "PRIVATE"
```

### 示例：添加检索测试

```python
# tests/test_cognitive.py

class TestMultiHopRetrieval:
    
    @pytest.mark.slow
    def test_my_retrieval_scenario(self, brain, unique_user_id):
        """测试新的检索场景"""
        
        # 构建记忆
        memories = ["事实 1", "事实 2", "事实 3"]
        for memory in memories:
            brain.add(memory, unique_user_id)
        
        time.sleep(2)  # 等待索引
        
        # 检索
        result = brain.search("查询", unique_user_id)
        
        # 验证（memories、relations）
        assert result["metadata"]["has_memory"]
        assert len(result.get("memories", [])) > 0
```

---

## 架构关键点

### 只检索，不推理

NeuroMemory 只负责检索，返回结构化 JSON：

```json
{
    "status": "success",
    "resolved_query": "消解后的查询",
    "memories": [
        {"content": "灿灿还有一个弟弟叫帅帅", "score": 0.87}
    ],
    "relations": [
        {"source": "灿灿", "relation": "弟弟", "target": "帅帅"}
    ],
    "metadata": {
        "retrieval_time_ms": 123,
        "has_memory": true
    }
}
```

推理由调用方的主 LLM 完成。

### 隐私过滤

- **PRIVATE**（存储）：个人偏好、经历、私有关系、计划
- **PUBLIC**（丢弃）：公共知识、百科事实、查询问句

---

## 故障排除

### 问题：找不到 pytest 命令

```powershell
# 错误：pytest: 无法识别命令
# 解决：使用 uv run pytest 或先激活虚拟环境

# 方式 1：使用 uv run（推荐）
uv run pytest tests/test_cognitive.py

# 方式 2：激活虚拟环境
.\.venv\Scripts\Activate.ps1
pytest tests/test_cognitive.py
```

### 问题：测试连接数据库失败

**本地测试**：
```powershell
# 确保 Docker 服务正在运行
docker-compose ps
docker-compose up -d

# 确认使用 --target local（默认）
uv run pytest tests/test_cognitive.py --target local
```

**远程测试**：
```powershell
# 使用 --target railway，配置已在 config.py 中设置默认值
uv run pytest tests/test_cognitive.py --target railway

# 如需临时覆盖默认配置，可通过环境变量设置
$env:RAILWAY_NEO4J_HOST="custom-neo4j-host"
$env:RAILWAY_QDRANT_HOST="custom-qdrant-host"
uv run pytest tests/test_cognitive.py --target railway
```

### 问题：LLM API 调用失败

```
检查 .env 文件中的 API 密钥配置
检查网络连接
```

### 问题：测试输出不显示

```powershell
# 确保使用 -s 参数
uv run pytest -s

# 或检查 pyproject.toml 中的 pytest 配置
```

### 问题：异步存储测试不稳定

```python
# 在存储后添加等待时间
brain.add("记忆内容", user_id)
time.sleep(3)  # 等待索引更新
result = brain.search("查询", user_id)
```

---

## 下一步

- [快速开始](GETTING_STARTED.md) - 环境搭建和基础使用
- [配置参考](CONFIGURATION.md) - 模型和数据库配置
- [架构文档](ARCHITECTURE.md) - 系统整体架构
- [主架构文档](ARCHITECTURE.md) - Y 型分流架构详解
