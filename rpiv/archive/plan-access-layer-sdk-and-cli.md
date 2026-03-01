---
description: "功能实施计划: access-layer-sdk-and-cli"
status: archived
created_at: 2026-01-23T00:00:00
updated_at: 2026-01-29T00:00:00
archived_at: 2026-01-29T00:00:00
---

# 功能：第一批（接入层）— Python SDK（NeuroMemory）与 CLI 工具

以下计划完整，实施前请验证文档与代码库模式。

---

## 功能描述

实现 [REMAINING_FEATURES_AND_ORDER.md](../docs/REMAINING_FEATURES_AND_ORDER.md) 中「第一批：接入层补齐」的两项：

1. **Python SDK（NeuroMemory 类）**：`from neuromemory import NeuroMemory`；封装 `add/search/ask/get_graph`，支持 `config`、`metadata`（metadata 首版可接受但暂不持久化）。底层委托 `PrivateBrain`（`get_brain()`），不重复实现业务逻辑。
2. **CLI 工具**：`neuromemory add/search/ask/graph export/graph visualize/status`，通过 [project.scripts] 入口；基于 Typer。`status` 复用 `health_checks`；其余命令基于 SDK 或 `get_brain()`。

**价值**：提升应用集成与调试易用性；CLI 可直接复用 SDK，减少重复。

---

## 用户故事

作为应用开发者，我希望通过 `from neuromemory import NeuroMemory` 使用 `add/search/ask/get_graph`，以便在脚本或服务中集成记忆能力而无需直接操作 `private_brain` 或 HTTP。

作为开发者，我希望通过 `neuromemory` 命令行进行添加、检索、问答、图谱导出/可视化及服务状态检查，以便在终端快速调试和演示。

---

## 问题陈述

- 当前无 `neuromemory` 可安装包，`from neuromemory import NeuroMemory` 不可用。
- 文档（API.md、COMPONENTS、GETTING_STARTED）中的 NeuroMemory 接口与 CLI 命令均未实现。
- `pyproject.toml` 仅有 `packages = ["tests"]`，无 `neuromemory` 包与 CLI 入口。

---

## 解决方案陈述

- **包结构**：新增 `neuromemory/` 包，`__init__.py` 导出 `NeuroMemory`；`neuromemory/cli.py` 为 Typer 入口。`NeuroMemory` 持有 `_brain = get_brain()`，`config` 非 `None` 时首版忽略并 log，后续可扩展 `PrivateBrain.from_config`。
- **SDK 接口**：`add(content, user_id="default", metadata=None) -> str`：调 `brain.add(content, user_id)`，成功返回 `result["memory_id"]`，失败抛 `ValueError`；`metadata` 接受但暂不传给 brain。`search(query, user_id="default", limit=10)`：调 `brain.search(..., limit)`，返回与 brain 一致的 `dict`（`memories`, `relations`, `metadata`）。`ask(question, user_id="default")`：调 `brain.ask`，成功返回 `result["answer"]`，失败抛 `ValueError`。`get_graph(user_id="default", depth=2)`：调 `brain.get_user_graph(user_id, depth)`，返回 `dict`。
- **CLI**：Typer 组 `app`；`add`/`search`/`ask` 各为命令；`graph` 为子组，下挂 `export`、`visualize`；`status` 独立命令。`status` 调 `health_checks.check_neo4j/qdrant/llm_config` 并打印；其余通过 `NeuroMemory()` 调 SDK。`graph export` 默认 JSON 到 stdout，`--output` 可选；`graph visualize` 生成临时 HTML（内嵌 vis-network CDN），用 `webbrowser.open` 打开。
- **pyproject**：`packages = ["neuromemory", "tests"]`；`[project.scripts]`：`neuromemory = "neuromemory.cli:app"`（Typer 实例可作入口）；新增依赖 `typer`。若 `uv pip install -e .` 后 `from neuromemory import NeuroMemory` 报 `No module named 'private_brain'`，则在 `[tool.setuptools]` 增加 `py-modules = ["config","private_brain","session_manager","coreference","consolidator","privacy_filter","health_checks"]`。

---

## 功能元数据

**功能类型**：新功能
**估计复杂度**：中
**主要受影响的系统**：包布局、pyproject、`neuromemory` 包、CLI
**依赖项**：typer；现有 private_brain、config、health_checks

---

## 上下文参考

### 必读代码

- [private_brain.py](../private_brain.py) 第 418–432 行：`search(query, user_id, limit=10)`；第 432–477 行：`ask`；第 479–501 行：`add` 返回 `{status, memory_id}` 或 `{status, error}`；第 348–420 行：`get_user_graph(user_id, depth=2)`。
- [config.py](../config.py) 第 1–50 行：`MEM0_CONFIG`、`get_chat_config`；[health_checks.py](../health_checks.py) 第 11–62 行：`check_neo4j`、`check_qdrant`、`check_llm_config`。
- [http_server.py](../http_server.py) 第 117–145 行：`AddMemoryRequest/Response`、`AskRequest/Response` 等 Pydantic 模型与 REST API 调用方式。
- [pyproject.toml](../pyproject.toml) 全文：`[project]`、`[tool.setuptools]`、`packages`。

### 要创建/修改的文件

- `neuromemory/__init__.py`：`NeuroMemory` 类及 `__all__ = ["NeuroMemory"]`。
- `neuromemory/cli.py`：Typer `app`，命令 `add`/`search`/`ask`/`graph`/`status`，`graph` 子命令 `export`、`visualize`。
- `pyproject.toml`：`packages` 增加 `neuromemory`；`[project.scripts]`；依赖 `typer`；必要时 `py-modules`。
- `tests/test_sdk.py`：`NeuroMemory` 的 `add`/`search`/`ask`/`get_graph` 封装与错误行为。
- `tests/test_cli.py`：`neuromemory status`、`add`、`search`、`graph export` 等（可标 `@pytest.mark.slow` 或 `requires_db` 的用例）。
- `docs/API.md`、`docs/GETTING_STARTED.md`：将 Python SDK、CLI 由 🚧/📋 标为 ✅ 并补充使用示例（含 `pip install -e .`、`neuromemory status`）。

### 相关文档

- [API 接口设计](../docs/API.md) — Python SDK、CLI 签名与返回。
- [REMAINING_FEATURES_AND_ORDER 第一批](../docs/REMAINING_FEATURES_AND_ORDER.md#三开发顺序建议) — 产出与顺序。
- [COMPONENTS NeuroMemory 目标设计](../docs/COMPONENTS.md#python-sdk-neuromemory-类-开发中) — 目标接口形态。

### 要遵循的模式

- **错误处理**：SDK 中 `brain.add`/`brain.ask` 返回 `status=="error"` 或含 `error` 时，`raise ValueError(result.get("error","未知错误"))`；与 [http_server.py](../http_server.py) 中 `HTTPException` 的"失败即报错"一致。
- **日志**：`import logging`；`logger = logging.getLogger("neuromemory.sdk")` 或 `neuromemory.cli`；`config` 非 None 时 `logger.debug("NeuroMemory(config=...) 暂未使用 config，将使用默认 get_brain()")`。
- **CLI 输出**：`status` 打印可读的 `neo4j/qdrant/llm: ok/fail`；`graph export` 默认为 JSON 至 stdout；`add` 成功后打印 `memory_id`；`ask` 打印 `answer`；`search` 打印 `memories`/`relations` 的简明摘要或 JSON。

---

## 实施计划

### 阶段 1：包与 SDK

- 新建 `neuromemory/`，`__init__.py` 定义 `NeuroMemory`，`from private_brain import get_brain`；实现 `add/search/ask/get_graph` 并对 `brain` 的 error 形态抛 `ValueError`。
- 修改 `pyproject.toml`：`packages = ["neuromemory", "tests"]`；确认 `uv pip install -e .` 后 `from neuromemory import NeuroMemory` 可用，必要时加 `py-modules`。

### 阶段 2：CLI

- 新建 `neuromemory/cli.py`，Typer `app`；实现 `add`、`search`、`ask`、`graph export`、`graph visualize`、`status`；`status` 调用 `health_checks`；其余通过 `NeuroMemory()` 调用。`graph visualize` 生成临时 HTML（vis-network CDN），`webbrowser.open`。
- `pyproject.toml` 增加 `typer` 依赖、`[project.scripts] neuromemory = "neuromemory.cli:app"`。

### 阶段 3：测试与文档

- `tests/test_sdk.py`：`NeuroMemory` 的 `add`（含 `memory_id`）、`search`（含 `limit`）、`get_graph`（含 `nodes`/`edges`）；错误时 `ValueError`。可按需 `@pytest.mark.slow` 或 `requires_db`。
- `tests/test_cli.py`：`status`（不依赖 DB）；`add`/`search`/`graph export` 等可标 slow/requires_db。
- 更新 `docs/API.md`、`docs/GETTING_STARTED.md`：SDK、CLI 标为已实现，并给出 `pip install -e .`、`Neuromemory`、`neuromemory status` 示例。

---

## 逐步任务

### 1. CREATE neuromemory/__init__.py

- **IMPLEMENT**：`from private_brain import get_brain`。`class NeuroMemory:` 在 `__init__(self, config: dict = None)` 中：`if config is not None: import logging; logging.getLogger("neuromemory.sdk").debug("NeuroMemory(config=...) 暂未使用，使用 get_brain()")`；`self._brain = get_brain()`。`add(self, content, user_id="default", metadata=None) -> str`：`r = self._brain.add(content, user_id)`；若 `r.get("status")=="error"`：`raise ValueError(r.get("error","添加失败"))`；return `r["memory_id"]`。（`metadata` 接受不传 brain。）`search(self, query, user_id="default", limit=10)`：return `self._brain.search(query, user_id, limit=limit)`。`ask(self, question, user_id="default")`：`r = self._brain.ask(question, user_id)`；若 `r.get("error")`：`raise ValueError(r["error"])`；return `r["answer"]`。`get_graph(self, user_id="default", depth=2)`：return `self._brain.get_user_graph(user_id, depth=depth)`。`__all__ = ["NeuroMemory"]`。
- **IMPORTS**：`get_brain` from `private_brain`。
- **GOTCHA**：`get_brain` 依赖项目根在 path；若安装后缺 `private_brain`，在后续任务中加 `py-modules`。
- **VALIDATE**：`python -c "from neuromemory import NeuroMemory; m=NeuroMemory(); print(m.get_graph('u')['status'])"`

### 2. UPDATE pyproject.toml — 包与可安装性

- **IMPLEMENT**：`[tool.setuptools]` 中 `packages = ["neuromemory", "tests"]`（原 `packages = ["tests"]` 改为二者）。若存在 `py-modules = []`，可保留或删除。保存后执行 `uv pip install -e .`，再 `python -c "from neuromemory import NeuroMemory; print(NeuroMemory)"`；若 `ModuleNotFoundError: private_brain`，则添加 `py-modules = ["config","private_brain","session_manager","coreference","consolidator","privacy_filter","health_checks"]` 并重试。
- **VALIDATE**：`uv pip install -e .` 且 `python -c "from neuromemory import NeuroMemory; print(NeuroMemory)"` 无错。

### 3. CREATE neuromemory/cli.py

- **IMPLEMENT**：`import typer`, `import json`, `import tempfile`, `import webbrowser`；`from neuromemory import NeuroMemory`；`from health_checks import check_neo4j, check_qdrant, check_llm_config`。`app = typer.Typer()`。`@app.command() def add(content: str, user: str = typer.Option("default", "--user","-u"))`：`m=NeuroMemory()`；`mid=m.add(content, user)`；`typer.echo(mid)`。`@app.command() def search(query: str, user: str = typer.Option("default","--user","-u"), limit: int = typer.Option(10,"--limit","-l"))`：`m=NeuroMemory()`；`d=m.search(query, user, limit=limit)`；`typer.echo(json.dumps(d, ensure_ascii=False, indent=2))`。`@app.command() def ask(question: str, user: str = typer.Option("default","--user","-u"))`：`m=NeuroMemory()`；`a=m.ask(question, user)`；`typer.echo(a)`。`graph_app = typer.Typer()`；`app.add_typer(graph_app, name="graph")`。`@graph_app.command("export")`：`user: str = typer.Option("default","--user","-u")`，`output: Optional[Path] = typer.Option(None,"--output","-o")`；`m=NeuroMemory()`；`g=m.get_graph(user)`；`s=json.dumps(g, ensure_ascii=False, indent=2)`；若 `output` 则 `output.write_text(s, encoding="utf-8")` 否则 `typer.echo(s)`。`@graph_app.command("visualize")`：`user: str = typer.Option("default","--user","-u")`，`open_browser: bool = typer.Option(True,"--open-browser/--no-open-browser")`；`m=NeuroMemory()`；`g=m.get_graph(user)`；构建 HTML 字符串：`<html><head><script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script></head><body><div id="n"/></body><script>var n=[...nodes...],e=[...edges...]; new vis.Network(container,{nodes:n,edges:e},{});</script></html>`（将 `g["nodes"]` 转为 `{id,label}`，`g["edges"]` 转为 `{from:source,to:target}`）；写入 `tmp = tempfile.NamedTemporaryFile(suffix=".html", delete=False)`；若 `open_browser` 则 `webbrowser.open("file://"+tmp.name)`；`typer.echo(f"已生成: {tmp.name}")`。`@app.command() def status()`：`neo=check_neo4j()`, `qd=check_qdrant()`, `llm=check_llm_config()`；`typer.echo("neo4j: ok" if neo else "neo4j: fail")` 等。
- **IMPORTS**：`typer`、`json`、`tempfile`、`webbrowser`、`Path`、`Optional`；`NeuroMemory`；`health_checks`。
- **GOTCHA**：`graph visualize` 的 vis-network 节点需 `{id: n["id"], label: n.get("name",n["id"])}`；边需 `{from: e["source"], to: e["target"]}`。`webbrowser` 在无图形环境可能失败，可 `try/except` 后仍输出文件路径。
- **VALIDATE**：`neuromemory status` 输出三行 ok/fail；`neuromemory add "test" --user u` 输出 memory_id（需 DB）；`neuromemory graph export --user u` 输出 JSON。

### 4. UPDATE pyproject.toml — typer 与 scripts

- **IMPLEMENT**：`dependencies` 中加入 `typer`。`[project.scripts]` 新增 `neuromemory = "neuromemory.cli:app"`（Typer 实例作入口，需 Typer 支持直接 invokable；若本环境需 `main`，则 `def main(): app()`，且 `neuromemory = "neuromemory.cli:main"`）。Typer 对象可被 `typer.run` 或作为 `app()` 调用；`console_scripts` 通常需要 callable。查 Typer 文档：`app` 为 `typer.Typer()` 时，`app` 自身可执行，等价于 `app()`。故 `neuromemory = "neuromemory.cli:app"` 可行；若报错则改为 `main` 包装。
- **VALIDATE**：`uv pip install -e .` 后 `neuromemory --help` 列出 `add`、`search`、`ask`、`graph`、`status`。

### 5. ADD tests/test_sdk.py

- **IMPLEMENT**：`from neuromemory import NeuroMemory`。`TestNeuroMemory`：`test_get_graph_structure`：`m=NeuroMemory()`；`g=m.get_graph("u")`；`assert "status" in g`，`assert "nodes" in g`，`assert "edges" in g`。`test_add_returns_memory_id`：`m=NeuroMemory()`；`mid=m.add("sdk test", "sdk_user")`；`assert isinstance(mid, str)` 且 `len(mid)>0`；可标 `@pytest.mark.slow` 或 `requires_db`。`test_search_returns_dict`：`m.search("x", "u", limit=2)`；`assert "memories" in r`，`assert "metadata" in r`。`test_ask_error_raises`：当 `brain.ask` 返回 `error` 时应 `ValueError`；可用 mock 或标 slow 用真实调用再测正常返回。
- **PATTERN**：与 [tests/test_api_v1.py](../tests/test_api_v1.py) 的断言风格一致。
- **VALIDATE**：`pytest tests/test_sdk.py -v -m "not slow"`（至少 `test_get_graph_structure`、`test_search_returns_dict` 通过）。

### 6. ADD tests/test_cli.py

- **IMPLEMENT**：`from typer.testing import CliRunner`；`from neuromemory.cli import app`；`runner = CliRunner()`。`test_status_exits_zero`：`r=runner.invoke(app, ["status"])`；`assert r.exit_code == 0`；`assert "neo4j" in r.output` 或 `"qdrant" in r.output`。`test_help`：`runner.invoke(app, ["--help"])` 含 `add`、`search`、`graph`、`status`。`test_graph_export_exits_zero`：`runner.invoke(app, ["graph","export","--user","u"])` 为 0，输出含 `"status"` 或 `"nodes"`；可标 slow。
- **VALIDATE**：`pytest tests/test_cli.py -v -m "not slow"`。

### 7. UPDATE docs/API.md

- **IMPLEMENT**：将「Python SDK 接口」标题旁 `[🚧 开发中]` 改为 `[✅ 已实现]`；在代码块下加一行：`from neuromemory import NeuroMemory`，并示例 `m=NeuroMemory()`；`m.add("...", user_id="u")`；`m.search("...", user_id="u", limit=5)` 等。将「CLI 接口」`[📋 规划]` 改为 `[✅ 已实现]`，并注明：`uv pip install -e .` 或 `pip install -e .` 后使用 `neuromemory` 命令；保留原命令示例。
- **VALIDATE**：阅读 API.md 无错字。

### 8. UPDATE docs/GETTING_STARTED.md

- **IMPLEMENT**：将「使用 SDK (开发中)」改为「使用 SDK」；示例改为 `from neuromemory import NeuroMemory`；`memory = NeuroMemory()`；`memory.add(...)`；`memory.search(...)`；`memory.ask(...)`。可补充：安装方式 `pip install -e .` 或 `uv pip install -e .`。CLI 示例：`neuromemory status`，`neuromemory add "..." --user u`。
- **VALIDATE**：阅读 GETTING_STARTED 无错字。

---

## 测试策略

- **单元**：`NeuroMemory` 各方法在 `get_brain()` 可用时，返回类型与错误时 `ValueError`；`metadata` 接受不报错。
- **集成**：`neuromemory status` 不依赖 DB；`add`/`search`/`graph export` 依赖 DB 时可标 `@pytest.mark.slow` 或 `requires_db`。
- **边缘**：`graph visualize` 在无 `webbrowser` 环境下仍写出文件；`search` 的 `limit=0` 或 `1`；`add` 在 brain 返回 error 时 `ValueError`。

---

## 验证命令

- **语法**：`python -m py_compile neuromemory/__init__.py neuromemory/cli.py`
- **安装与导入**：`uv pip install -e .`；`python -c "from neuromemory import NeuroMemory; print(NeuroMemory)"`
- **CLI**：`neuromemory --help`；`neuromemory status`
- **测试**：`pytest tests/test_sdk.py tests/test_cli.py -v -m "not slow"`；完整：`pytest tests/test_sdk.py tests/test_cli.py -v`

---

## 验收标准

- [ ] `from neuromemory import NeuroMemory` 可用，`NeuroMemory().add/search/ask/get_graph` 行为符合 API.md，`add`/`ask` 失败时 `ValueError`。
- [ ] `metadata` 在 `add` 中接受且不报错；`config` 非 None 时忽略并 log。
- [ ] `neuromemory add/search/ask/graph export/graph visualize/status` 均已实现且 `--help` 正确。
- [ ] `neuromemory status` 调用 `health_checks` 并输出 neo4j/qdrant/llm；`graph visualize` 生成 HTML 并可用浏览器打开。
- [ ] `docs/API.md`、`docs/GETTING_STARTED.md` 中 SDK、CLI 已标为已实现并附示例。
- [ ] `pytest tests/test_sdk.py tests/test_cli.py -m "not slow"` 通过。

---

## 完成检查清单

- [ ] neuromemory 包与 `NeuroMemory`、`cli` 已创建并接入 pyproject。
- [ ] `py-modules` 已按需添加（仅当 `import neuromemory` 报缺 `private_brain` 时）。
- [ ] `neuromemory --help`、`neuromemory status`、`neuromemory graph export` 可用。
- [ ] 测试与文档更新已完成。

---

## 备注

- **PrivateBrain 与 config**：首版 `NeuroMemory` 不向 `PrivateBrain` 传入 `config`；`PrivateBrain.from_config` 留作后续。
- **graph visualize**：vis-network 若 CDN 不可用可降级为仅写 HTML 并提示用本地浏览器打开；`webbrowser` 在无头环境可 except 后仅输出路径。
- **Typer 入口**：若 `neuromemory.cli:app` 在 `console_scripts` 下无法执行，可改为 `def main(): app()` 且 `neuromemory = "neuromemory.cli:main"`。
