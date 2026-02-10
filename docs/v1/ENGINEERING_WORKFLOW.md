# 工程推进流程指南

本文档说明如何基于 Claude 全局命令（`core_piv_loop`、`validation`、`create-prd`）理解和推进 NeuroMemory 的工程流程，适用于新成员上手和日常迭代。

## 1. 概述

### 1.1 命令来源与位置

- 命令定义于用户级：`~/.claude/commands/`（或项目内 `.claude/commands/` 若存在）。
- 本仓库相关产出目录：
  - **特性计划**：`docs/feature-plans/`（参见 [feature-plans/README.md](feature-plans/README.md)）
  - **需求文档**：`rpiv/requirements/`（prd-*.md）
  - **实施计划**：`rpiv/plans/`（plan-*.md）
  - **验证产出**：`rpiv/validation/`（code-review-*.md、exec-report-*.md、system-review-*.md）
  - **归档**：`rpiv/archive/`

### 1.2 三组命令的职责

| 命令组 | 职责 | 产出 |
|--------|------|------|
| **core_piv_loop** | 从理解项目 → 制定计划 → 按计划实施 | 项目摘要、特性计划、代码与测试 |
| **validation** | 质量门禁与复盘：验证、审查、修问题、改进流程 | 审查报告、执行报告、系统审查 |
| **create-prd** | 在写计划与代码之前锁定产品范围与共识 | PRD.md |

---

## 2. core_piv_loop：特性开发主循环

**PIV** 可理解为：**P**rime（加载上下文）→ **I**mplement/Plan（规划与执行）→ **V**alidate（验证）。形成一条完整的「理解 → 规划 → 实施」流水线。

### 2.1 `core_piv_loop/prime` — 加载项目上下文

**含义**：在不写代码的前提下，通过分析仓库结构、文档、git，建立对代码库的全局理解。

**软件工程价值**：
- 避免「盲目动手」：先搞清楚技术栈、目录约定、近期改动，再规划。
- 统一认知：项目概述、架构、当前状态作为后续计划与执行的共同基线。
- 提炼约束：从 CLAUDE.md、README、架构文档中提取原则、反模式、测试与部署习惯。

**典型输出**：结构化摘要，包括：
- 项目概述、用户需求、架构、技术栈、核心原则
- 当前状态：已完成/未完成目标、最近提交、活动分支

**何时使用**：新接手仓库、项目结构或技术栈有较大变化时；也可在每次大特性规划前跑一次。

---

### 2.2 `core_piv_loop/plan-feature` — 制定实施计划

**含义**：将功能需求或用户故事转化为**可直接交给执行者实施的计划**。此阶段**不写代码**，只产出计划。

**软件工程价值**：
- 搭建「需求 → 设计」的桥梁：明确在哪些文件、按什么顺序、用什么模式实现。
- 提高一次性实施成功率：计划中包含必读文件（含行号）、要遵循的既有模式、要创建的新文件、分阶段步骤、每步的 **VALIDATE** 命令，目标是执行方**第一次即可按计划完成**。
- 可审计、可复用：计划以 Markdown 形式保存，便于 Code Review 与后续类似需求复用。

**产出位置**：
- 命令默认：`rpiv/plans/{kebab-name}.md`
- 本仓库惯例：也可放在 `docs/feature-plans/`，与 [feature-plans/README.md](feature-plans/README.md) 一致。

**计划核心结构**（摘要）：
- 功能描述、用户故事、问题/方案陈述
- **上下文参考**：必读代码（含行号）、要新建的文件、外部文档
- **要遵循的模式**：命名、错误处理、日志、测试等
- **分阶段实施计划** + **逐步任务**（每项带 ACTION、PATTERN、VALIDATE）
- 测试策略、验收标准、完成检查清单

**原则**：「上下文为王」— 计划应尽量自带执行所需信息，减少执行阶段再猜测或查找。

**plan-feature 检查项（建议）**：
- **「要创建/修改的文件」与问题陈述一致**：若问题陈述中提到某文档 D（如 COMPONENTS.md、API.md）需体现本特性，则「要创建/修改的文件」须包含 D；若不修改 D，须在计划中显式写出「不修改 D，原因：…」。
- **Typer/Click 的 Path**：当逐步任务要求 `typer.Option(..., path_type=Path)` 或 `Optional[Path]` 且对 `output` 做 `output.write_text(...)` 时，须在 IMPLEMENT 或 GOTCHA 中写明：使用 `path_type=Path` 得到 `Path`，或约定采用 `Optional[str]` + `Path(output).write_text(...)` 为可接受等价实现。
- **验证命令的 Shell 与平台**：若「验证命令」或「VALIDATE」使用 `&&`、`||` 等 Bash 语法，须注明「Bash」或「Linux/macOS」；若需支持 Windows，应补充 PowerShell 写法（如 `;` 代替 `&&`），或写「Windows 下将 `&&` 改为 `;`」。

---

### 2.3 `core_piv_loop/execute` — 按计划实施

**含义**：严格按 `plan-feature` 产出的计划文件，从「逐步任务」第一项到最后一项依次实现，并在每步或每阶段后做校验。

**软件工程价值**：
- 把「计划」变为可执行工作流：逐步任务即显式 WBS，execute 按序完成并校验。
- 边做边验证：每次改动后做语法/类型/单元测试等，失败先修，通过再继续，避免攒到最后一口气再排查。
- 产出可供后续复盘：自然衔接 `validation/execution-report` 与 `validation/system-review`。

**执行要点**：
1. 通读计划，理解任务依赖与验证点。
2. 按「逐步任务」顺序：定位文件 → 按规范实现 → 做局部校验。
3. 完成实现后，按计划的「测试策略」补全并运行测试。
4. 按计划的「验证命令」从 Level 1 到 5 依次执行；任何失败：修复 → 重跑 → 通过后再继续。

**执行检查清单（建议）**：
- **Shell 检查**：若计划中的验证命令含 `&&`（或仅给出 Bash 示例），且当前环境为 **Windows PowerShell**，则先将 `&&` 替换为 `;` 再执行，或按计划/CLAUDE 中的 PowerShell 示例执行；执行报告中可简要记录「在 PowerShell 下使用 `;`」。
- **`[project.scripts]` 与 `py-modules` 的安装后验证**：对引入 `[project.scripts]` 入口且依赖项目根模块（如 `private_brain`）的计划，在 `uv pip install -e .` 之后，除 `python -c "from 包 import 类"` 外，应增加 `命令 --help` 或 `命令 status` 等，以验证通过 console_scripts 调用时 `py-modules` 已生效；若失败且报 `ModuleNotFoundError`，按计划中的「若…则添加 py-modules」处理并重装。

---

### 2.4 core_piv_loop 的推荐顺序

```
1. /core_piv_loop/prime
   → 得到项目上下文摘要

2. /core_piv_loop/plan-feature @<需求/设计文档 或 简短描述>
   → 产出 文档（如 docs/feature-plans/{feature}.md 或 rpiv/plans/{feature}.md）

3. （可选）人工审阅计划，必要时再跑 plan-feature 迭代

4. /core_piv_loop/execute @<计划文件路径>
   → 实现 + 测试 + 跑完计划中的 VALIDATE
```

- **何时重跑 prime**：项目结构、技术栈、团队约定有较大变化，或换全新仓库时。
- **何时重跑 plan-feature**：需求/范围变更，或 execute 中发现计划有明显遗漏时。
- **何时只重跑 execute**：计划无大碍，仅实现有误或测试遗漏，修完再跑即可。

---

## 3. validation：质量与反馈闭环

本组命令在实施前、实施中、实施后做检查、审查与复盘，形成质量与流程改进闭环。

### 3.1 `validation/validate` — 项目级验证流水线

**含义**：按项目约定顺序执行一整套验证命令（静态检查 → 测试 → 构建 → 可选端到端），并汇总为健康报告。

**本项目说明**：  
`validate` 的具体命令由 `~/.claude/commands/validation/validate.md` 或项目内对应文件定义。NeuroMemory 的典型验证可参考 CLAUDE.md，例如：

- 语法/风格：`ruff check .` 或项目既有 lint
- 单元/集成测试：`pytest`、`pytest -m "not slow"` 等（见 [CLAUDE.md](../CLAUDE.md) 常用命令）
- 可选：服务健康检查、MCP 基础验证等

**软件工程价值**：
- 统一「可否合入/发布」的标尺；便于 CI 接入。
- 分层验证：静态 → 单元 → 集成 → 构建 → 可选 E2E，便于快速定位失败层级。

---

### 3.2 `validation/code-review` — 提交前技术审查

**含义**：对 `git status`、`git diff`、未跟踪新文件做**技术向**审查，聚焦：逻辑错误、安全、性能、代码质量、对项目约定（CLAUDE.md、/docs、既有模式）的遵守。

**软件工程价值**：
- 在合并前做一次人工/AI 双重把关。
- 输出可操作：每个 issue 带 `severity`、`file`、`line`、`suggestion`，便于直接修或交给 `code-review-fix`。

**产出**：`rpiv/validation/[appropriate-name].md`

---

### 3.3 `validation/code-review-fix` — 按审查结果修复

**含义**：以 code-review 的 Markdown 文件（或问题列表）为输入，逐条：解释问题 → 修改代码 → 补/跑相关测试；全部修完后跑 `validation/validate`。

**软件工程价值**：
- 把 Code Review 的结论闭环，避免「审完无人修」。
- 可重复、可审计：同一份 review 可多次跑 fix，或交给不同执行方。

**用法示例**：`/validation/code-review-fix @rpiv/validation/xxx-review.md`

---

### 3.4 `validation/execution-report` — 实施过程复盘

**含义**：在完成一次实施（如 `core_piv_loop/execute` 或一轮手工特性开发）后，撰写「做了什么、与计划对齐情况、遇到的困难、偏离与跳过」的报告。

**软件工程价值**：
- 实施可追溯，便于日后理解「为何这样实现」。
- 为 `system-review` 提供输入：system-review 对比「计划 vs 执行报告」，改进流程与资产，而非再逐行审代码。

**产出**：`rpiv/validation/[feature-name].md`

**典型内容**：元信息（计划路径、改动文件、行数）、验证结果（语法/类型/单元/集成）、顺利点、困难点、与计划的偏离、跳过的项、对计划/执行/CLAUDE 的改进建议。

---

### 3.5 `validation/system-review` — 流程与元层面改进

**含义**：**不做代码级审错**，而是分析「计划、执行命令、执行报告」之间的一致性，识别：哪些偏离合理、哪些暴露了流程/模板/命令设计问题，并给出对 CLAUDE.md、计划模板、执行命令、新命令的改进建议。

**软件工程价值**：
- 改进「下次怎么做」：通过计划 vs 实际的差异，更新 CLAUDE.md、plan-feature 模板、execute 检查项或命令。
- 区分好/坏偏离：好的（如发现更优实现、计划假设错误）与坏的（违反明确约束、引入技术债、误解需求）。
- 面向资产与自动化：输出具体到「在 CLAUDE.md 加哪条、在 plan-feature 加哪步、是否新增 validation 命令、在 execute 加哪类校验」。

**输入**：计划文件（$1）、执行报告（$2）；会参考 `plan-feature` 与 `execute` 的指导逻辑。

**产出**：`rpiv/validation/[feature-name]-review.md`

---

### 3.6 validation 的推荐顺序与插入点

**与 core_piv_loop 的配合**（实施完成后）：

```
/core_piv_loop/execute @<计划> 完成后：

→ /validation/execution-report
  → rpiv/validation/{feature}.md

→ /validation/system-review <计划> <执行报告>
  → rpiv/validation/{feature}-review.md
  → 按建议更新 CLAUDE.md、计划/执行模板或命令
```

**与日常提交/合并的配合**：

```
改动完成后：

→ /validation/code-review
  → rpiv/validation/{name}.md

若有 issue：
  → /validation/code-review-fix @rpiv/validation/{name}.md
  → 修完后再跑 /validation/validate

最后 /commit 或走既有提交流程
```

**validate 的典型使用场景**：
- 在 `code-review-fix` 全部修完后的终检；
- 在 `execute` 的「最终验证」中调用项目定义在 validate 中的命令集合；
- 在 CI 中与 validate 中定义的命令集保持一致。

---

## 4. create-prd — 先于实现的产品需求

**含义**：基于当前对话和你指定的文档（`$ARGUMENTS`），生成结构化产品需求文档（PRD），缺失处通过对话补全，输出到 `PRD.md`。

**软件工程价值**：
- **先锁定范围再写计划与代码**：避免边做边想，先把使命、目标用户、MVP 范围、用户故事、成功标准、阶段划分说清楚。
- **与 plan-feature 的分工**：
  - **create-prd**：产品视角 — 做什么、给谁用、做到什么程度、不做什么。
  - **plan-feature**：工程视角 — 在现有代码库里如何实现、动哪些文件、用哪些模式、如何验证。

**与后续流程的衔接**：
- create-prd 产出 `PRD.md`（产品层）。
- plan-feature 的输入可以是 PRD 的某一节、某条用户故事，或 `@PRD.md`；产出工程层计划（如 `docs/feature-plans/xxx.md` 或 `rpiv/plans/xxx.md`）。

---

## 5. 整体顺序与推进策略

### 5.1 从 0 到 1 的新功能（推荐路径）

```
1) /create-prd [@需求/竞品/头脑风暴文档]
   → PRD.md，必要时多轮对话补全

2) /core_piv_loop/prime
   → 项目上下文（新项目或大变更时必做）

3) /core_piv_loop/plan-feature @PRD.md 或 @PRD 某节 / 用户故事
   → 如 docs/feature-plans/{feature}.md

4) （可选）人工审阅计划，有需要再跑 plan-feature

5) /core_piv_loop/execute @<计划文件>
   → 实现 + 测试 + 跑完计划中的 VALIDATE

6) /validation/execution-report
   → rpiv/validation/{feature}.md

7) /validation/system-review <计划> <执行报告>
   → rpiv/validation/{feature}-review.md
   → 按建议更新 CLAUDE.md、plan/execute 模板或命令

8) /validation/code-review
   → rpiv/validation/xxx.md

9) 如有 issue：/validation/code-review-fix @<审查文件>
   → 修完再 /validation/validate

10) /commit 或既有提交流程
```

### 5.2 在已有 PRD/需求上做迭代

- PRD 已定：可从 `prime`（若许久未做）或直接 `plan-feature` 开始。
- 小范围修改：可省略 create-prd，用 `plan-feature @简短需求` 或直接 `execute @对旧计划的局部更新`。

### 5.3 仅做质量闭环（不开发新功能）

- **提交前**：`code-review` →（若有问题）`code-review-fix` → `validate` → `commit`。
- **完成一次大 feature 后**：`execution-report` → `system-review`，专门做流程与资产改进。

### 5.4 命令与产出速查

| 命令 | 在工程中的角色 | 主要产出 |
|------|----------------|----------|
| **create-prd** | 产品范围与共识 | PRD.md |
| **core_piv_loop/prime** | 项目与上下文快照 | 项目摘要（可文档化） |
| **core_piv_loop/plan-feature** | 技术设计与任务分解 | docs/feature-plans/*.md 或 rpiv/plans/*.md |
| **core_piv_loop/execute** | 按计划实施与自验 | 代码 + 测试 + 验证结果 |
| **validation/validate** | 统一健康检查 | 通过/失败 + 报告 |
| **validation/code-review** | 提交前技术审查 | rpiv/validation/*.md |
| **validation/code-review-fix** | 把审查结论修完 | 修改后代码 + 再次 validate |
| **validation/execution-report** | 实施复盘 | rpiv/validation/*.md |
| **validation/system-review** | 流程与资产改进 | rpiv/validation/*.md + 改进清单 |

---

## 6. 与本仓库的衔接

### 6.1 既有结构

- **CLAUDE.md**：项目约定、常用命令、反模式；prime、plan-feature、execute、validation 均应遵守。
- **docs/feature-plans/**：特性计划存放与规范见 [feature-plans/README.md](feature-plans/README.md)。
- **rpiv/**：requirements、plans、validation、archive 的目录已在使用。

### 6.2 验证命令（validate）的定制

- 本仓库常用命令见 [CLAUDE.md](../CLAUDE.md)（如 `pytest`、`pytest -m "not slow"` 等）。
- 若使用 `validation/validate`，建议在 `~/.claude/commands/validation/validate.md` 或项目内等效文件中，按本仓库技术栈定义：lint、测试、可选的服务健康检查等，并与 CI 保持一致。

### 6.3 计划产出位置

- **plan-feature** 默认写到 `rpiv/plans/`；本仓库也可按惯例写到 `docs/feature-plans/`，与现有特性文档统一，并在 plan 中写明输出路径。

---

## 7. 相关文档

- [CLAUDE.md](../CLAUDE.md) — 项目规则与常用命令
- [feature-plans/README.md](feature-plans/README.md) — 特性开发文档规范
- [ARCHITECTURE.md](ARCHITECTURE.md) — 架构说明，供 prime / plan-feature 理解上下文

---

## 8. rpiv 过程文件的清理

执行完整流程（core_piv_loop + validation）时，`rpiv/` 下会生成多类过程性产出。本节说明：哪些算过程文件、何时清理、如何清理，以及是否纳入版本库。

### 8.1 目录结构

| 子目录 | 性质 | 说明 |
|--------|------|------|
| **requirements/** | PRD | 产品需求文档（prd-*.md）。 |
| **plans/** | 半持久 / 可迁 | 实施计划（plan-*.md）；若已有一份在 `docs/feature-plans/`，此处为工作副本可删；**若计划仅在此**，应先迁移到 `docs/feature-plans/` 再删，或归档。 |
| **validation/** | 过程文件 | 代码审查（code-review-*.md）、执行报告（exec-report-*.md）、系统审查（system-review-*.md）。审查修完、改进落实后可删。 |
| **archive/** | 归档 | 已完结特性的过程文件归档存放。 |

**结论**：`validation/` 以**过程文件**为主；`plans` 需区分：已有「正式版」在 `docs/feature-plans/` 则可删，否则先迁后删或归档。

### 8.2 何时执行清理

**推荐时机**：该 feature 的**全流程已走完**，且满足：

1. **代码已合并**：`/commit` 或 PR 已合并到目标分支（如 `master`）。
2. **system-review 已消化**：对 CLAUDE.md、计划/执行模板、execute 检查项等的修改已落地。
3. **code-review 已闭环**：若有 issue，已通过 `code-review-fix` 修完并通过 `validate`。

满足后，可对该 feature 对应的 `rpiv` 文件做清理，**不必**等「整仓所有 feature 都完成」再统一清。

**不推荐的时机**：

- system-review 尚未做，或做了但改进项还没落实到 CLAUDE/模板；
- 该 feature 的 PR 尚未合并，且可能还会基于同一份 code-review / execution-report 做迭代。

### 8.3 如何清理

#### 方案 A：直接删除（推荐用于纯过程文件）

对**已完结**的单个 feature，按名称删除对应文件，例如：

```powershell
# 在项目根目录，PowerShell 示例：清理 feature「access-layer-sdk-and-cli」相关
Remove-Item -ErrorAction SilentlyContinue rpiv/validation/access-layer-*.md
Remove-Item -ErrorAction SilentlyContinue rpiv/validation/access-layer-sdk-and-cli.md
Remove-Item -ErrorAction SilentlyContinue rpiv/validation/access-layer-sdk-and-cli-review.md
# plans：若 docs/feature-plans/ 中已有同名或等价计划，再删
Remove-Item -ErrorAction SilentlyContinue rpiv/plans/access-layer-sdk-and-cli.md
```

- **code-reviews**：可按 `*review.md` 或 feature 前缀批量删。
- **execution-reports**、**system-reviews**：一般与 feature 名一一对应，按名删即可。
- **plans**：确认 `docs/feature-plans/` 已有再删；否则先 `Copy-Item` 到 `docs/feature-plans/`。

#### 方案 B：归档后删（适合要留审计/案例的场景）

若希望保留「我们如何做 code-review / 复盘 / 流程改进」的案例，可建归档目录，按 feature 或按时间迁移后再删 `rpiv` 内原文件：

- 归档位置示例：`docs/engineering-archive/{feature}/` 或 `rpiv/archive/YYYY-MM/{feature}/`
- 建议：**仅归档你认为对流程复现、内训有用的** report/review，不必全部保留。

#### 方案 C：.gitignore 整个 rpiv（过程文件不进版本库）

若团队约定：`rpiv` 仅作为**本地或 CI 中的过程工作区**，不纳入版本库，可把 `rpiv/` 加入 `.gitignore`。这样：

- 不需要通过「清理后 commit 删除」来维护 repo；
- 清理完全是**本地操作**：本地随时删、按需归档即可；
- 新 clone 的成员不会拿到别人的 process 产出，需自己跑一遍流程。

**与本仓库的衔接**：当前 `.gitignore` 已包含 `rpiv/`。`rpiv` 为本地过程目录，不提交。

### 8.4 建议汇总

| 偏好 | 清理时机 | 清理方式 | 版本库 |
|------|----------|----------|--------|
| **轻量、少留痕** | 每个 feature 合并且 system-review 落实后 | 方案 A：直接删；plans 先迁 `docs/feature-plans/` 再删 | 可不提交 rpiv，或提交前删干净 |
| **留审计/案例** | 同上 | 方案 B：拣选后归档到 `docs/engineering-archive/` 等，再删 rpiv 原文件 | 仅提交归档目录中要长期保留的 |
| **过程纯本地** | 本地随时 | 方案 A 或 B，仅本地执行 | 方案 C：.gitignore `rpiv/`，不提交 |

**对 `plans` 的单独建议**：优先把「仅存在于 `rpiv/plans/`」的计划迁移到 `docs/feature-plans/`，并补到 [feature-plans/README.md](feature-plans/README.md) 的文档列表，再删除 `rpiv/plans/` 中副本。这样计划成为项目正式文档，`rpiv` 只做过程工作区。
