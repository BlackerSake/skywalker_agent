---
name: version-design-markdown-creator
description: 当用户想要升级项目版本时，根据用户提供的需求编写版本升级设计文档（Markdown 格式）
short_description: 编写项目版本升级设计文档
---

# 版本升级设计文档编写指南

本技能指导如何为软件项目编写版本升级设计文档（如 V1→V2）。
文档的读者是参与实现的开发者，目标是让开发者无需追问就能独立完成升级工作。

## 文档包含的内容

每份版本升级设计文档必须覆盖以下七节，顺序固定：

1. **项目背景**：旧版本已实现的功能、存在的问题、新版本的目标
2. **目录结构**：新版本完整的文件树，标注新增与保留的文件
3. **旧版本修改方案**：需要对已有文件做哪些微小改动，每条说明原因
4. **实现阶段计划**：将工作拆分为有序的 Phase，每个 Phase 内逐文件展开：职责、代码、字段/函数逐一解释
5. **验证方式**：单元测试、集成测试、手动验证的具体步骤
6. **关键文件清单**：所有涉及文件的汇总表

---

## 核心原则

### 原因先行

文档的主要价值不是告诉开发者"做什么"，而是告诉他们"为什么这样做"。
每一条修改方案、每一个设计决策，都必须先给出原因，再描述做法。

没有原因的指令会让开发者在遇到特殊情况时无法判断是否需要变通；有了原因，他们才能在理解意图的基础上执行。

### 信息充分再动笔

收到请求后，先确认你拥有足够的信息再开始写文档。如果用户的描述缺少以下任何一项，先提问，不要用猜测填充：

- 旧版本（VN）已实现的核心功能列表
- 旧版本存在的具体问题（不是泛泛的"功能不足"）
- 新版本（VN+1）要新增的模块或功能

**提问示例：**
> "你提到要升级到 V2，但我还不清楚 V1 存在哪些具体问题。能描述一下吗？比如：token 是否会溢出、是否缺少跨会话记忆、还是有其他架构上的限制？"

### 简洁，不多余

只写开发者尚不具备的信息。不解释语言基础知识，不重复项目通用知识，不在已有示例之外追加冗余说明。
对每一段内容问自己：读者不看这段，会做出错误的实现决策吗？如果不会，删掉。

---

## 文档创建过程

### 步骤一：信息收集

开始前确认以下信息齐全。任何一项缺失，暂停并向用户提问：

**必须收集：**
- 旧版本（VN）已实现的模块和功能
- 旧版本存在的已知问题，及每个问题导致的具体后果
- 新版本计划新增的模块或功能

**有助于提升质量（缺失时可合理推断，但需在文档中标注假设）：**
- 项目技术栈（语言、框架）
- 现有目录结构
- 各 Phase 的优先级或时间约束

---

### 步骤二：撰写项目背景

项目背景固定分三个子节，按以下顺序撰写。

#### 子节 1：旧版本现状（列举已实现的模块）

格式：`- \`文件名\`：一句话描述该文件的职责`，不解释实现细节。

```markdown
### 1.1 V1 现状

V1 已完成核心功能：
- `core.py`：Message、AgentState 类型定义
- `context.py`：SimpleTokenizer 粗略 token 计算 + 截断
- `loop.py`：状态机循环 INIT→THINKING→TERMINATED
```

#### 子节 2：旧版本存在的问题

每个问题独立编号，格式为 `问题名称：问题的直接后果`。后果是关键——它解释了为什么这个问题必须在新版本中解决。

```markdown
### 1.2 V1 存在的问题

1. **对话历史无限增长**：没有调用 truncate_messages，长对话会导致 token 超限报错
2. **Role.SYSTEM 缺失**：truncate_messages 第 66 行检查 `msg.role == "system"` 永远为
   False，系统消息会被错误截断
3. **should_compress 未预留**：V2 的压缩逻辑无处挂载，导致 V2 无法与 V1 代码兼容共存
```

#### 子节 3：新版本目标

目标列表应与上方问题列表对应——读者能看出"这个目标解决了上面第 N 个问题"。不需要显式写出对应关系，顺序和措辞对齐即可。

```markdown
### 1.3 V2 目标

实现四层 Memory 架构，支持：
- 跨会话记忆持久化（MEMORY.md）          ← 解决"无法跨会话保留知识"
- 单会话滑动窗口 + 压缩                   ← 解决"对话历史无限增长"
- 上下文投影（token 预算管理）
- BM25 关键词检索
```

注：注释行（`← 解决...`）是说明示例用途的，实际文档中不需要保留这些注释。

---

### 步骤三：描述新版本目录结构

用代码块呈现完整文件树。每个文件后附行内注释说明职责；旧版本保留的文件注明 `# 已在VN`，新版本新增的文件注明 `# VN+1 新增`（将 N 替换为实际版本号）。

```markdown
## 2. 目录结构

skywalker/
├── core.py                    # 核心类型定义（已在V1）
├── agent/
│   ├── context.py             # SimpleTokenizer + WorkingMemory（已在V1）
│   └── loop.py                # 状态机循环（已在V1）
└── memory/                    # V2 新增
    ├── __init__.py            # 包初始化，导出公共 API（V2 新增）
    ├── base.py                # 抽象接口：MemoryType、MemoryEntry、MemoryStore（V2 新增）
    ├── short_term.py          # 滑动窗口 + 会话压缩（V2 新增）
    └── long_term.py           # MEMORY.md 跨会话读写（V2 新增）
```

树结构只描述"有什么文件、各自负责什么"，不描述文件内部的实现——那是各 Phase 内部展开的内容。

---

### 步骤四：撰写旧版本修改方案

这是文档的核心部分，直接决定开发者能否正确改动已有代码。

**每条修改的固定格式：**

```
### N.M `文件名` — 改动的简短标题

[原因段落] 描述当前代码存在什么问题，以及不修改会导致什么后果。
引用具体的行号、函数名或错误类型，让读者能快速定位。

[修改段落] 说明需要做什么改动。可以附代码片段，但代码片段不能替代文字说明。
```

格式中没有字面的 `[原因]` 和 `[修改]` 标签——这两段之间只有换行分隔，通过内容本身区分（先描述问题，后给出方案）。

**正确示例：**

```markdown
### 6.1 `core.py` — 添加 `Role.SYSTEM`

当前 `Role` 枚举只有 `USER` 和 `ASSISTANT`。`truncate_messages` 第 66 行用字符串
`"system"` 与 `msg.role` 比较，由于 `msg.role` 是枚举值而非字符串，比较永远为 False，
系统消息永远不会被识别为"需要保留"的消息类型。

在 `Role` 枚举末尾新增 `SYSTEM = "system"`。

### 6.2 `context.py` — 修复 `truncate_messages` 角色判断

第 66 行 `if msg.role == "system"` 是字符串字面量比较。修复 6.1 后，Role.SYSTEM 已
存在，这里的比较方式仍然不一致，不会因为新增枚举值而自动修复。

将第 66 行改为 `if msg.role == Role.SYSTEM`，与其他角色判断的写法保持一致。

### 6.3 `context.py` — 添加 `should_compress()` 存根

`loop.py` 在 V2 中需要在每次 ASSISTANT 消息追加后调用此方法决定是否触发压缩。
V1 中该方法不存在，若直接在 loop.py 中调用会抛出 AttributeError。
V1 阶段先添加存根以保持向后兼容，V2 实现时再填充实际逻辑。

在 `SimpleTokenizer` 中添加方法，固定返回 `False`：
```python
def should_compress(self, messages: list[Message]) -> bool:
    return False
```
```

**反例（不要这样写）：**

```markdown
### 修改 core.py
在 Role 枚举中加一个 SYSTEM 值。
```

问题：没有说明当前代码为什么有问题，也没有说明不加会出现什么错误。开发者不理解原因，遇到变体情况无法判断是否需要调整。

---

### 步骤五：规划实现阶段

将所有新增工作按**每天能完成并测试的实际产出**来划分 Phase。**每个 Phase 内，按文件逐一展开完整的实现说明**，开发者读完一个 Phase 就能独立完成该 Phase 的所有文件。

**Phase 划分的两条规则：**

规则一：**依赖先行。** 被其他文件 import 的模块必须排在更早的 Phase。画出 import 关系图，被最多文件依赖的排最前。

规则二：**当天写完、当天测完。** 每个 Phase 内的文件在该 Phase 结束时必须是可运行、可测试的真实模块，不能是空壳或存根。测试文件也属于该 Phase，和被测文件一起列出。

同一天内，优先安排依赖少、可独立测试的文件并行完成（如纯数据结构文件 + 两个互不依赖的功能模块）；需要跨模块联动才能测试的文件，推迟到依赖项全部就绪的那一天。

**示例（正确的划分方式）：**

```
第一天：base.py（纯数据结构）+ retrieval.py（只依赖 base）+ short_term.py（只依赖 core/context）
        → 三个文件当天全部写完并测试，retrieval 和 short_term 是可工作的完整模块

第二天：long_term.py（依赖 base + retrieval）+ 集成 cli/main.py 的启动/关闭流程
        → long_term 写完并测试，cli 集成后跑完整的 startup→shutdown 流程
```

**反例（不要这样划分）：**

```
Phase 1：base.py + retrieval.py（存根）+ short_term.py（存根）
Phase 2：填充 retrieval.py 实现 + 填充 short_term.py 实现
```
问题：Phase 1 结束时没有任何可测试的产出，开发者无法验证当天工作是否正确，错误会累积到 Phase 2 才暴露。

---

#### Phase 的顶层格式

```markdown
### 第N天：阶段标题

一句话说明这一天结束时，哪些模块已经是可工作、可测试的完整产出。
```

Phase 标题下直接跟各文件的展开说明，不需要再用"新建文件 / 修改文件"列表过渡。

---

#### 新建文件的展开格式

每个新建文件依次包含以下四部分，顺序固定：

**① 职责与独立原因**
说明这个文件负责什么，以及为什么它需要是一个独立文件（而不是合并进其他文件）。
"为什么独立"是必写项——它解释了架构决策，防止开发者把逻辑合并到错误的地方。

**② import 声明**
列出该文件需要导入的所有依赖，附一句话说明每条 import 的用途。

**③ 逐类 / 逐函数展开**
每个类或函数单独呈现：先给出代码，紧接着解释字段含义、参数约定、返回值规则、边界处理。
代码和解释必须成对出现，不能只有代码没有解释，也不能只有解释没有代码。

**④ 接口约定（如有跨文件约定）**
说明其他文件调用此模块时需要遵守的规则，例如返回值顺序、异常处理约定、线程安全要求等。

**示例：**

````markdown
### 第一天：打基础 + 独立模块

这一天结束时，`base.py` 定义完成，`retrieval.py` 和 `short_term.py` 均为可工作、可测试的完整模块。

---

#### `memory/base.py` — 抽象接口

**职责：** 定义所有 memory 子模块共享的数据结构和基类，作为模块间的共享契约。

**为什么需要独立文件：** `short_term.py`、`long_term.py`、`retrieval.py` 都依赖
`MemoryEntry` 类型。若将其定义在某一子模块中，其他模块导入时会引入不必要的耦合，
且容易造成循环导入。独立到 `base.py` 后，任何子模块只需导入 `base.py`。

**imports：**
```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
```
- `ABC / abstractmethod`：定义 MemoryStore 抽象基类，强制子类实现所有方法
- `dataclass`：简化 MemoryEntry 的字段声明，自动生成 `__init__` 和 `__repr__`
- `field`：为 `tags` 等列表字段提供安全的默认值（避免可变默认参数陷阱）

**`MemoryType`（Enum）**
```python
class MemoryType(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    ARCHITECTURE = "architecture"
    BUGFIX = "bugfix"
```
用于给每条记忆打类型标签，便于按类型过滤检索结果。值使用小写字符串，
与 MEMORY.md 文件中的 `## [type]` 标题格式直接对应，解析时可直接映射。

**`MemoryEntry`（dataclass）**
```python
@dataclass
class MemoryEntry:
    id: str
    type: MemoryType
    content: str
    importance: float          # 范围 0.0~1.0
    source: str                # "user" | "inference" | "session"
    created_at: datetime
    tags: list[str] = field(default_factory=list)
```
- `importance`：决定压缩时的保留优先级和检索结果的排序权重，越高越优先
- `source`：记录这条记忆从哪里来，便于后续审计和过滤
- `tags`：使用 `field(default_factory=list)` 而非 `= []`，避免所有实例共享同一个列表对象

**`MemoryStore`（ABC）**
```python
class MemoryStore(ABC):
    @abstractmethod
    def add(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    def get(self, id: str) -> Optional[MemoryEntry]: ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...

    @abstractmethod
    def delete(self, id: str) -> bool: ...
```
- `get()`：找不到 id 时返回 `None`，不抛出异常——调用方负责判断返回值
- `search()`：返回列表按相关性降序排列，长度不超过 `top_k`
- `delete()`：返回 `True` 表示删除成功，`False` 表示 id 不存在
````

---

#### 修改已有文件的展开格式

修改已有文件时，只展开改动部分，不重复整个文件的内容。每处改动独立说明原因和影响范围。

**示例：**

````markdown
#### `core.py` — 新增字段

**改动 1：`AgentState` 添加 `project_root`**
```python
project_root: str | None = None
```
字段默认为 `None`，所有现有的 `AgentState()` 调用无需修改即可继续工作。
V2 中 `cli/main.py` 在初始化时传入项目根目录路径，`long_term.py` 用它定位 MEMORY.md。
````

---

#### 引入自定义文件格式时的补充写法

如果某个文件负责读写自定义持久化格式（如 `.md`、`.json` 配置文件），在该文件的展开说明末尾追加格式规范，说明示例结构和所有边界条件。

**示例：**

`````markdown
#### `memory/long_term.py` — MEMORY.md 读写

**职责：** ...（正常展开）

**MEMORY.md 格式规范：**

````markdown
---
project: skywalker
version: 1
updated: 2026-06-11T10:00:00
---

## [architecture] Project uses four-layer memory
- importance: 0.9
- tags: [architecture, design]
- source: user

Skywalker Agent uses working/episodic/long-term/procedural memory layers.
````

**解析规则：**
- YAML frontmatter（`---` 块）是可选的；文件不以 `---` 开头时，直接从第一个 `## ` 标题开始解析
- `importance` 缺失时默认 `0.5`；`tags` 缺失时默认 `[]`
- 标题行到下一个 `## ` 之间的段落作为 `MemoryEntry.content`

**写入规则：**
- 每次 shutdown 时全量覆写，以 `importance` 降序排列
- `updated` 写入当前 UTC 时间，格式 ISO 8601
`````

---

### 步骤六：说明验证方式

分三个层次描述，从局部到整体：

- **单元测试**：针对单个模块，隔离外部依赖，列出测试文件路径和核心测试场景
- **集成测试**：跨模块的完整流程，例如 `startup → conversation → shutdown`
- **手动验证**：开发者可逐条执行的步骤，每步描述预期的可观测结果

```markdown
## 10. 验证方式

1. **单元测试**（`tests/test_memory/`）
   - `test_short_term.py`：验证滑动窗口在消息数超限时正确丢弃最早的非系统消息
   - `test_long_term.py`：验证 MEMORY.md 的读写、有无 frontmatter 的解析兼容性
   - `test_retrieval.py`：验证 BM25 检索在空索引、单条、多条时的返回结果

2. **集成测试**：完整 startup → conversation → shutdown 流程，验证 MEMORY.md
   在退出后被写入，再次启动后内容被注入系统提示

3. **手动验证**：
   - 启动 skywalker，确认终端输出"已加载 N 条记忆"（N ≥ 0）
   - 发送 5 条消息，确认第 1 条消息在窗口满后从历史中消失
   - 输入 Ctrl+Z 退出，打开 MEMORY.md 确认内容已更新
   - 再次启动，确认上次记录的内容出现在系统提示中
```

---

### 步骤七：撰写关键文件清单

用表格汇总所有涉及的文件，四列：文件路径、操作类型（新建 / 修改）、所属 Phase、一句话说明。

```markdown
| 文件 | 操作 | 第几天 | 说明 |
|------|------|--------|------|
| `skywalker/core.py` | 修改 | 前置 | 添加 Role.SYSTEM，扩展 AgentState |
| `skywalker/agent/context.py` | 修改 | 前置 | 修复角色判断 bug，添加 should_compress 存根 |
| `skywalker/memory/base.py` | 新建 | 第一天 | 抽象接口：MemoryType、MemoryEntry、MemoryStore |
| `skywalker/memory/retrieval.py` | 新建 | 第一天 | BM25 检索，当天测试完成 |
| `skywalker/memory/short_term.py` | 新建 | 第一天 | 滑动窗口 + 会话压缩，当天测试完成 |
| `skywalker/memory/long_term.py` | 新建 | 第二天 | MEMORY.md 读写，依赖 base + retrieval |
```

---

## 常见错误

| 错误写法 | 问题所在 | 正确做法 |
|----------|----------|----------|
| 修改方案只写"加一个 SYSTEM 值" | 读者不知道为什么要加，遇到变体情况无法判断 | 先说当前代码为什么有问题及其后果，再给出修改方案 |
| Phase 按功能模块分组，而非按当天可完成的产出划分 | Phase 结束时没有可测试的产出，错误累积到后续才暴露 | 每个 Phase 当天写完、当天测完；依赖少、可独立测试的文件优先安排在同一天 |
| 目录结构树不区分新旧文件 | 读者无法判断哪些文件是新增的、哪些是保留的 | 旧文件标注 `# 已在VN`，新文件标注 `# VN+1 新增` |
| Phase 内只列文件名和一句话职责 | 开发者拿到的信息不足以独立实现，还需要额外追问 | 每个文件完整展开：职责 → imports → 逐类/逐函数代码 + 解释 |
| 代码片段后没有解释，或解释后没有代码 | 只有代码读者不知道为什么这样写；只有解释读者无法直接实现 | 代码和解释成对出现，顺序固定：先代码，后解释 |
| 新建文件只写职责，不写为什么独立 | 读者不理解架构决策，容易把逻辑合并到错误的文件 | 说明若不独立会带来什么问题（循环导入、耦合等） |
| 验证方式只写"写单元测试" | 没有可执行的验证步骤，开发者不知道测什么 | 列出具体测试场景和手动验证的可观测预期结果 |
| 自定义文件格式只给示例，不写边界条件 | 解析器在缺字段、格式不完整时行为不一致 | 明确说明每个可选字段缺失时的默认值和兜底行为 |