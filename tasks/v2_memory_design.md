# Skywalker V2 Memory 设计文档

---

## 1. 项目背景

### 1.1 V1 现状

- `core.py`：Message（frozen dataclass）、Role（含SYSTEM）、AgentState、LoopState
- `agent/context.py`：SimpleTokenizer，token 估算 + truncate_messages，缓存已修复
- `agent/loop.py`：状态机 INIT→THINKING→PARSING→TERMINATED，TERMINATED 预留钩子
- `llm/base.py` + `llm/anthropic.py`：LLM 统一接口
- `cli/main.py`：CLI 入口跑通

### 1.2 V1 存在的问题

1. **无跨会话记忆**：每次启动从零开始，用户偏好、项目规范无法保留
2. **对话历史无状态管理**：SimpleTokenizer 是无状态工具，长对话只能全量重算，没有增量管理
3. **无压缩机制**：token 超限时直接截断，旧消息中的有效信息永久丢失
4. **无检索能力**：记忆条目多时无法按相关性召回

### 1.3 V2 目标

- 实现三层记忆持久化：会话窗口、项目级、用户级
- ConversationManager 有状态队列，增量 token 管理
- 压缩接口抽象化，V2 用 LLM 实现，V5 可无缝替换为 SubAgent
- 启发式检索，支持中英文分词 + 多维度评分

---

## 2. 目录结构

```
skywalker/
├── core.py                        # 已在V1，新增 project_root 至 AgentState
├── agent/
│   ├── context.py                 # 已在V1，添加 should_compress() 钩子
│   └── loop.py                    # 已在V1，TERMINATED 挂载 memory 写回
├── memory/                        # V2 新增
│   ├── __init__.py                # 导出公共 API
│   ├── base.py                    # 抽象接口：MemoryType, MemoryEntry, MemoryStore
│   ├── schema.py                  # frontmatter 解析，md 格式定义
│   ├── short_term.py              # ConversationManager + CompressorBase/LLMCompressor
│   ├── long_term.py               # MEMORY.md / USER.md 读写
│   └── search.py                  # 启发式检索，多维度评分
└── config/
    └── settings.py                # 已在V1，新增 compressor_type / memory_path 配置

tests/
└── test_memory/
    ├── test_base.py
    ├── test_schema.py
    ├── test_short_term.py
    ├── test_long_term.py
    └── test_search.py
```

---

## 3. 旧版本修改方案

### 3.1 `core.py` — AgentState 新增 project_root

`long_term.py` 需要知道当前项目根目录才能定位 MEMORY.md。AgentState 是贯穿整个 loop 的状态容器，project_root 放这里最自然，loop.py 初始化时从 cli 传入，long_term.py 从 state 里取。

```python
project_root: str | None = None
```

默认 None，现有调用无需修改。

### 3.2 `agent/context.py` — 添加 should_compress() 钩子

loop.py 在 OBSERVING 状态后需要判断是否触发压缩。V1 无此方法，直接调用会 AttributeError。V2 由 ConversationManager 实现此方法，context.py 先留存根保持兼容。

```python
def should_compress(self, messages: list[Message]) -> bool:
    return False  # V2 由 ConversationManager 覆盖
```

### 3.3 `agent/loop.py` — TERMINATED 挂载写回钩子

V2 需要在对话结束时将关键信息写回 MEMORY.md / USER.md。TERMINATED 状态是唯一的统一出口，写回逻辑挂在这里，loop 不感知细节。

```python
case "TERMINATED":
    await memory_manager.on_shutdown(state)  # V2 新增，V1 此行不存在
```

### 3.4 `config/settings.py` — 新增 memory 相关配置

```python
compressor_type: str = "llm"           # "llm" | "subagent"（V5）
memory_dir: str = "~/.skywalker/memory"
project_memory_file: str = "MEMORY.md"
compress_threshold: float = 0.75       # token 使用率超过此值触发压缩
max_memory_entries: int = 100          # 单文件最大条目数
```

---

## 4. 依赖关系

```
core.py
  ↑
base.py            ← 无外部依赖，只依赖标准库
  ↑
schema.py          ← 依赖 base.py
  ↑
search.py          ← 依赖 base.py, schema.py
  ↑
long_term.py       ← 依赖 base.py, schema.py, search.py
  ↑
short_term.py      ← 依赖 base.py, core.py, llm/base.py（压缩时调用LLM）
  ↑
loop.py            ← 依赖 short_term.py, long_term.py（通过 memory_manager 统一调用）
```

依赖方向单向向上，loop.py 只依赖 memory 的公共 API，不直接 import 子模块。

---

## 5. 实现阶段

### 第一天：base.py + schema.py + search.py

这一天结束时，三个基础模块均为可工作、可测试的完整模块。它们构成 memory 子系统的数据层，后续所有模块都依赖它们。

---

#### `memory/base.py` — 抽象接口

**职责：** 定义所有 memory 子模块共享的数据结构和基类，作为模块间的共享契约。

**为什么需要独立文件：** `short_term.py`、`long_term.py`、`search.py` 都依赖 `MemoryEntry` 类型。若将其定义在某一子模块中，其他模块导入时会引入不必要的耦合，且容易造成循环导入。独立到 `base.py` 后，任何子模块只需导入 `base.py`。

**imports：**
```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
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
用于给每条记忆打类型标签，便于按类型过滤检索结果。值使用小写字符串，与 MEMORY.md 文件中的 `## [type]` 标题格式直接对应，解析时可直接映射。

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
    updated_at: datetime
    tags: list[str] = field(default_factory=list)
    use_count: int = 0
```
- `importance`：决定压缩时的保留优先级和检索结果的排序权重，越高越优先
- `source`：记录这条记忆从哪里来，便于后续审计和过滤
- `tags`：使用 `field(default_factory=list)` 而非 `= []`，避免所有实例共享同一个列表对象
- `use_count`：记录被检索命中的次数，用于检索评分中的频率加成

**`MemoryStore`（ABC）**
```python
class MemoryStore(ABC):
    @abstractmethod
    def add(self, entry: MemoryEntry) -> None: ...

    @abstractmethod
    def get(self, id: str) -> MemoryEntry | None: ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...

    @abstractmethod
    def delete(self, id: str) -> bool: ...
```
- `get()`：找不到 id 时返回 `None`，不抛出异常——调用方负责判断返回值
- `search()`：返回列表按相关性降序排列，长度不超过 `top_k`
- `delete()`：返回 `True` 表示删除成功，`False` 表示 id 不存在

**完整代码：**

```python
# skywalker/memory/base.py

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class MemoryType(Enum):
    """记忆条目类型，值与 MEMORY.md 的 [type] 标题对应"""
    FACT = "fact"
    PREFERENCE = "preference"
    ARCHITECTURE = "architecture"
    BUGFIX = "bugfix"


@dataclass
class MemoryEntry:
    """单条记忆的数据结构"""
    id: str
    type: MemoryType
    content: str
    importance: float          # 0.0 ~ 1.0
    source: str                # "user" | "inference" | "session"
    created_at: datetime
    updated_at: datetime
    tags: list[str] = field(default_factory=list)
    use_count: int = 0


class MemoryStore(ABC):
    """记忆存储的抽象基类"""

    @abstractmethod
    def add(self, entry: MemoryEntry) -> None:
        """添加一条记忆，id 重复时覆盖"""
        ...

    @abstractmethod
    def get(self, id: str) -> MemoryEntry | None:
        """按 id 获取记忆，不存在返回 None"""
        ...

    @abstractmethod
    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """按关键词搜索，返回相关性降序排列的结果"""
        ...

    @abstractmethod
    def delete(self, id: str) -> bool:
        """删除一条记忆，返回是否成功（id 不存在返回 False）"""
        ...
```

---

#### `memory/schema.py` — frontmatter 解析与 MEMORY.md 格式定义

**职责：** 将 MEMORY.md 的 Markdown 文本解析为 `MemoryEntry` 列表，以及将 `MemoryEntry` 列表序列化为 Markdown 文本。这是持久化层的格式契约。

**为什么需要独立文件：** 解析/序列化逻辑被 `long_term.py` 依赖。如果内联到 `long_term.py` 中，`search.py` 在构建索引时也需要理解格式，会导致格式逻辑分散。独立后，格式变更只需改一处。

**imports：**
```python
from __future__ import annotations
import re
from datetime import datetime
from typing import Optional
from skywalker.memory.base import MemoryEntry, MemoryType
```
- `re`：正则匹配 `## [type]` 标题行和 frontmatter 块
- `MemoryEntry, MemoryType`：解析的目标类型

**`parse_memory_md(content: str) -> list[MemoryEntry]`**
```python
def parse_memory_md(content: str) -> list[MemoryEntry]: ...
```
- 输入：MEMORY.md 的完整文本内容
- 输出：解析后的 `MemoryEntry` 列表
- 解析规则：
  - YAML frontmatter（`---` 块）可选，缺失时从第一个 `## ` 开始解析
  - `## [type] Title` 格式的标题行，type 从方括号提取，无法匹配 MemoryType 时默认 `FACT`
  - `importance` 缺失默认 `0.5`，`tags` 缺失默认 `[]`，`use_count` 缺失默认 `0`
  - `##` 到下一个 `##` 之间的段落为 `MemoryEntry.content`（去除元数据行后的纯文本）
  - `id` 从标题的 hash 生成，保证同标题同内容不会重复

**`serialize_memory_md(entries: list[MemoryEntry], project: str = "", version: int = 1) -> str`**
```python
def serialize_memory_md(entries: list[MemoryEntry], project: str = "", version: int = 1) -> str: ...
```
- 输入：MemoryEntry 列表、项目名、版本号
- 输出：完整的 MEMORY.md 文本
- 写入规则：
  - 先写 frontmatter（`project`, `version`, `updated` 当前 UTC 时间 ISO 8601）
  - 按 `importance` 降序排列所有条目
  - 每个条目输出 `## [type] title` 标题行 + 元数据行 + 空行 + content 正文

**接口约定：**
- `parse_memory_md` 对格式不完整的文件做容错处理：缺失字段用默认值，而非抛异常
- `serialize_memory_md` 保证输出的文本能被 `parse_memory_md` 无损往返（round-trip）

**完整代码：**

```python
# skywalker/memory/schema.py

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Optional

from skywalker.memory.base import MemoryEntry, MemoryType

# 正则：匹配 ## [type] Title 格式的标题行
_HEADING_RE = re.compile(r"^##\s+\[([a-z]+)\]\s*(.*)")
# 正则：匹配元数据行（- key: value）
_META_RE = re.compile(r"^-\s+(\w+):\s*(.*)")
# 正则：匹配 frontmatter 块
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
# 正则：解析 frontmatter 中的键值对
_FM_KV_RE = re.compile(r"^(\w+):\s*(.*)")


def _generate_id(title: str, content: str) -> str:
    """从标题和内容生成稳定的 id"""
    raw = f"{title}|{content[:200]}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _parse_tags(raw: str) -> list[str]:
    """解析 [tag1, tag2] 格式的 tags 字符串"""
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1]
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def parse_memory_md(content: str) -> list[MemoryEntry]:
    """将 MEMORY.md 文本解析为 MemoryEntry 列表"""
    if not content or not content.strip():
        return []

    entries: list[MemoryEntry] = []
    pos = 0

    # 跳过 frontmatter
    fm_match = _FRONTMATTER_RE.match(content)
    if fm_match:
        pos = fm_match.end()

    # 按 ## 分割段落
    sections = re.split(r"(?=^## )", content[pos:], flags=re.MULTILINE)

    for section in sections:
        section = section.strip()
        if not section.startswith("## "):
            continue

        lines = section.split("\n")
        heading = lines[0]

        # 解析标题行
        hm = _HEADING_RE.match(heading)
        if not hm:
            continue

        type_str = hm.group(1)
        title = hm.group(2).strip()

        # 映射 MemoryType，无法匹配时默认 FACT
        try:
            mem_type = MemoryType(type_str)
        except ValueError:
            mem_type = MemoryType.FACT

        # 解析元数据行和正文
        importance = 0.5
        tags: list[str] = []
        source = "inference"
        created_at = datetime.now(timezone.utc)
        use_count = 0
        content_lines: list[str] = []
        in_meta = True

        for line in lines[1:]:
            if in_meta:
                mm = _META_RE.match(line)
                if mm:
                    key, val = mm.group(1), mm.group(2).strip()
                    if key == "importance":
                        try:
                            importance = float(val)
                        except ValueError:
                            pass
                    elif key == "tags":
                        tags = _parse_tags(val)
                    elif key == "source":
                        source = val
                    elif key == "created_at":
                        try:
                            created_at = datetime.fromisoformat(val.replace("Z", "+00:00"))
                        except ValueError:
                            pass
                    elif key == "use_count":
                        try:
                            use_count = int(val)
                        except ValueError:
                            pass
                    continue
                else:
                    in_meta = False

            # 跳过元数据块后的空行
            if in_meta is False and not line.strip() and not content_lines:
                in_meta = None  # 标记已过空行
                continue

            content_lines.append(line)

        entry_content = "\n".join(content_lines).strip()
        entry_id = _generate_id(title, entry_content)

        entries.append(MemoryEntry(
            id=entry_id,
            type=mem_type,
            content=entry_content,
            importance=importance,
            source=source,
            created_at=created_at,
            updated_at=created_at,
            tags=tags,
            use_count=use_count,
        ))

    return entries


def serialize_memory_md(
    entries: list[MemoryEntry],
    project: str = "",
    version: int = 1,
) -> str:
    """将 MemoryEntry 列表序列化为 MEMORY.md 文本"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    parts: list[str] = []

    # frontmatter
    parts.append("---")
    if project:
        parts.append(f"project: {project}")
    parts.append(f"version: {version}")
    parts.append(f"updated: {now}")
    parts.append("---")
    parts.append("")

    # 按 importance 降序排列
    sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)

    for entry in sorted_entries:
        # 标题行
        parts.append(f"## [{entry.type.value}] {entry.id}")
        parts.append("")

        # 元数据行
        parts.append(f"- importance: {entry.importance}")
        if entry.tags:
            parts.append(f"- tags: [{', '.join(entry.tags)}]")
        parts.append(f"- source: {entry.source}")
        parts.append(f"- created_at: {entry.created_at.strftime('%Y-%m-%dT%H:%M:%SZ')}")
        parts.append(f"- use_count: {entry.use_count}")
        parts.append("")

        # 正文
        parts.append(entry.content)
        parts.append("")

    return "\n".join(parts)
```

---

#### `memory/search.py` — 启发式检索

**职责：** 对 `MemoryEntry` 列表执行关键词匹配 + 多维度评分，返回排序后的结果。不依赖任何外部向量数据库或搜索引擎。

**为什么需要独立文件：** 检索逻辑被 `long_term.py`（读取 MEMORY.md 后搜索）和未来的 `short_term.py`（压缩前检索相关上下文）共同使用。独立后可单独测试评分算法。

**imports：**
```python
from __future__ import annotations
import re
from datetime import datetime, timedelta
from skywalker.memory.base import MemoryEntry
```
- `re`：中英文分词，ASCII 3字符以上词 + 汉字单字符
- `timedelta`：计算时效加成

**`tokenize(text: str) -> list[str]`**
```python
def tokenize(text: str) -> list[str]: ...
```
- 分词规则：ASCII 单词长度 ≥ 3 才保留；汉字逐字拆分；全部转小写
- 用途：将查询文本和条目文本统一拆分为 token 列表，用于命中计数

**`score_entry(entry: MemoryEntry, query_tokens: list[str], now: datetime | None = None) -> float`**
```python
def score_entry(entry: MemoryEntry, query_tokens: list[str], now: datetime | None = None) -> float: ...
```
评分公式：
```
score = meta_hits * 2.0        # 标题/描述命中
      + body_hits               # 正文命中
      + importance * 0.4        # 重要性权重
      + min(use_count, 5) * 0.1 # 使用频率（上限5）
      + recency_boost            # 时效加成（14天内+0.3，30天内+0.1）
```
- `meta_hits`：query tokens 在 tags 和 entry.type.value 中的命中数
- `body_hits`：query tokens 在 content 中的命中数
- `recency_boost`：基于 `entry.updated_at` 与当前时间的差值
- `now` 参数允许测试时注入固定时间，避免测试依赖系统时钟

**`search_entries(entries: list[MemoryEntry], query: str, top_k: int = 5) -> list[MemoryEntry]`**
```python
def search_entries(entries: list[MemoryEntry], query: str, top_k: int = 5) -> list[MemoryEntry]: ...
```
- 对每个 entry 调用 `score_entry`，按得分降序排列，返回前 `top_k` 个
- 查询为空字符串时返回空列表
- 命中时自动对 entry.use_count + 1（副作用，调用方需知悉）

**接口约定：**
- 返回列表长度 ≤ top_k，可能为 0
- 搜索是纯内存操作，不触发 I/O
- use_count 的自增是副作用，调用方如果需要保持 entry 不变，应传入副本

**完整代码：**

```python
# skywalker/memory/search.py

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from skywalker.memory.base import MemoryEntry

# 正则：匹配 ASCII 单词（3字符以上）或单个汉字
_TOKEN_RE = re.compile(r"[a-zA-Z0-9]{3,}|[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """将文本拆分为 token 列表"""
    return [t.lower() for t in _TOKEN_RE.findall(text)]


def score_entry(
    entry: MemoryEntry,
    query_tokens: list[str],
    now: datetime | None = None,
) -> float:
    """计算单条记忆与查询的相关性得分"""
    if not query_tokens:
        return 0.0

    if now is None:
        now = datetime.now(timezone.utc)

    # 构建 meta tokens（tags + type）
    meta_text = " ".join(entry.tags) + " " + entry.type.value
    meta_tokens = tokenize(meta_text)
    meta_hits = sum(1 for t in query_tokens if t in meta_tokens)

    # 构建 body tokens（content）
    body_tokens = tokenize(entry.content)
    body_hits = sum(1 for t in query_tokens if t in body_tokens)

    # 重要性权重
    importance_score = entry.importance * 0.4

    # 使用频率（上限 5）
    use_score = min(entry.use_count, 5) * 0.1

    # 时效加成
    recency_boost = 0.0
    if entry.updated_at:
        age = now - entry.updated_at
        if age <= timedelta(days=14):
            recency_boost = 0.3
        elif age <= timedelta(days=30):
            recency_boost = 0.1

    return meta_hits * 2.0 + body_hits + importance_score + use_score + recency_boost


def search_entries(
    entries: list[MemoryEntry],
    query: str,
    top_k: int = 5,
) -> list[MemoryEntry]:
    """对记忆列表执行关键词搜索，返回排序后的结果"""
    if not query.strip():
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    now = datetime.now(timezone.utc)

    scored: list[tuple[float, MemoryEntry]] = []
    for entry in entries:
        s = score_entry(entry, query_tokens, now)
        if s > 0:
            scored.append((s, entry))
            entry.use_count += 1  # 副作用：命中计数 +1

    scored.sort(key=lambda x: x[0], reverse=True)
    return [e for _, e in scored[:top_k]]
```

---

#### `tests/test_memory/test_base.py` — base.py 单元测试

核心测试场景：
- `MemoryType` 枚举值映射正确（`.value` 为小写字符串）
- `MemoryEntry` 构造时 `tags` 默认为空列表，多个实例不共享同一列表
- `MemoryEntry` 的 `importance` 范围验证（0.0~1.0）

**完整代码：**

```python
# tests/test_memory/test_base.py

from datetime import datetime, timezone

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType, MemoryStore


class TestMemoryType:
    def test_enum_values_are_lowercase_strings(self):
        assert MemoryType.FACT.value == "fact"
        assert MemoryType.PREFERENCE.value == "preference"
        assert MemoryType.ARCHITECTURE.value == "architecture"
        assert MemoryType.BUGFIX.value == "bugfix"

    def test_enum_from_value(self):
        assert MemoryType("fact") is MemoryType.FACT
        assert MemoryType("preference") is MemoryType.PREFERENCE

    def test_invalid_value_raises(self):
        with pytest.raises(ValueError):
            MemoryType("nonexistent")


class TestMemoryEntry:
    def _make_entry(self, **kwargs) -> MemoryEntry:
        now = datetime.now(timezone.utc)
        defaults = {
            "id": "test-id",
            "type": MemoryType.FACT,
            "content": "test content",
            "importance": 0.5,
            "source": "user",
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(kwargs)
        return MemoryEntry(**defaults)

    def test_tags_default_is_empty_list(self):
        entry = self._make_entry()
        assert entry.tags == []

    def test_tags_default_not_shared_between_instances(self):
        e1 = self._make_entry()
        e2 = self._make_entry()
        e1.tags.append("test")
        assert e2.tags == []

    def test_use_count_default_is_zero(self):
        entry = self._make_entry()
        assert entry.use_count == 0

    def test_importance_range(self):
        low = self._make_entry(importance=0.0)
        high = self._make_entry(importance=1.0)
        assert low.importance == 0.0
        assert high.importance == 1.0


class TestMemoryStoreInterface:
    def test_cannot_instantiate_abstract_class(self):
        with pytest.raises(TypeError):
            MemoryStore()
```

#### `tests/test_memory/test_schema.py` — schema.py 单元测试

核心测试场景：
- 有 frontmatter 时正确解析 project/version/updated
- 无 frontmatter 时从第一个 `## ` 开始解析
- 缺失字段（importance/tags/use_count）使用默认值
- type 无法匹配 MemoryType 时默认 FACT
- round-trip：`parse(serialize(entries)) == entries`

**完整代码：**

```python
# tests/test_memory/test_schema.py

from datetime import datetime, timezone

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.schema import parse_memory_md, serialize_memory_md


def _make_entry(**kwargs) -> MemoryEntry:
    now = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    defaults = {
        "id": "abc123",
        "type": MemoryType.FACT,
        "content": "Skywalker uses four-layer memory.",
        "importance": 0.9,
        "source": "inference",
        "created_at": now,
        "updated_at": now,
        "tags": ["architecture", "memory"],
        "use_count": 3,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


class TestParseMemoryMd:
    def test_empty_content_returns_empty_list(self):
        assert parse_memory_md("") == []
        assert parse_memory_md("   ") == []

    def test_with_frontmatter(self):
        content = """---
project: skywalker
version: 1
updated: 2026-06-01T10:00:00Z
---

## [fact] Test Entry
- importance: 0.8
- tags: [test]
- source: user
- created_at: 2026-06-01T10:00:00Z
- use_count: 1

Some content here.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.FACT
        assert entries[0].importance == 0.8
        assert entries[0].tags == ["test"]
        assert entries[0].content == "Some content here."

    def test_without_frontmatter(self):
        content = """## [architecture] Design
- importance: 0.9
- tags: [arch]
- source: inference
- created_at: 2026-06-01T10:00:00Z
- use_count: 0

Architecture description.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.ARCHITECTURE
        assert entries[0].content == "Architecture description."

    def test_missing_fields_use_defaults(self):
        content = """## [fact] Minimal
- source: user
- created_at: 2026-06-01T10:00:00Z

Just content.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].importance == 0.5
        assert entries[0].tags == []
        assert entries[0].use_count == 0

    def test_unknown_type_defaults_to_fact(self):
        content = """## [unknown] Something
- importance: 0.5
- source: user
- created_at: 2026-06-01T10:00:00Z
- use_count: 0

Content.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 1
        assert entries[0].type == MemoryType.FACT

    def test_multiple_entries(self):
        content = """## [fact] First
- importance: 0.7
- source: user
- created_at: 2026-06-01T10:00:00Z
- use_count: 0

First content.

## [bugfix] Second
- importance: 0.3
- source: session
- created_at: 2026-06-02T10:00:00Z
- use_count: 0

Second content.
"""
        entries = parse_memory_md(content)
        assert len(entries) == 2
        assert entries[0].type == MemoryType.FACT
        assert entries[1].type == MemoryType.BUGFIX


class TestSerializeMemoryMd:
    def test_produces_valid_frontmatter(self):
        entry = _make_entry()
        result = serialize_memory_md([entry], project="skywalker", version=1)
        assert result.startswith("---\n")
        assert "project: skywalker" in result
        assert "version: 1" in result
        assert "updated:" in result

    def test_entries_sorted_by_importance_desc(self):
        low = _make_entry(id="low", importance=0.3, content="low")
        high = _make_entry(id="high", importance=0.9, content="high")
        result = serialize_memory_md([low, high])
        # high 应该出现在 low 之前
        pos_high = result.find("[fact] high")
        pos_low = result.find("[fact] low")
        assert pos_high < pos_low

    def test_empty_entries(self):
        result = serialize_memory_md([])
        assert "---" in result
        assert "##" not in result


class TestRoundTrip:
    def test_parse_serialize_round_trip(self):
        entry = _make_entry()
        serialized = serialize_memory_md([entry])
        parsed = parse_memory_md(serialized)
        assert len(parsed) == 1
        assert parsed[0].type == entry.type
        assert parsed[0].importance == entry.importance
        assert parsed[0].tags == entry.tags
        assert parsed[0].source == entry.source
        assert parsed[0].use_count == entry.use_count
        assert parsed[0].content == entry.content
```

#### `tests/test_memory/test_search.py` — search.py 单元测试

核心测试场景：
- 空索引返回空列表
- 单条目精确匹配
- 多条目按得分排序
- 中文分词（汉字逐字拆分）
- 英文短词过滤（< 3 字符被忽略）
- 时效加成：14天内的条目得分高于 30天前的条目
- use_count 上限为 5

**完整代码：**

```python
# tests/test_memory/test_search.py

from datetime import datetime, timedelta, timezone

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.search import tokenize, score_entry, search_entries


def _make_entry(**kwargs) -> MemoryEntry:
    now = datetime.now(timezone.utc)
    defaults = {
        "id": "test-id",
        "type": MemoryType.FACT,
        "content": "test content",
        "importance": 0.5,
        "source": "user",
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "use_count": 0,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


class TestTokenize:
    def test_english_words(self):
        tokens = tokenize("Hello World Python")
        assert tokens == ["hello", "world", "python"]

    def test_short_words_filtered(self):
        tokens = tokenize("I am a Go dev")
        # "I" (1字符), "am" (2字符), "a" (1字符), "Go" (2字符) 被过滤
        assert tokens == ["dev"]

    def test_chinese_chars(self):
        tokens = tokenize("记忆系统")
        assert tokens == ["记", "忆", "系", "统"]

    def test_mixed_chinese_english(self):
        tokens = tokenize("Memory记忆系统")
        assert "memory" in tokens
        assert "记" in tokens
        assert "忆" in tokens

    def test_empty_string(self):
        assert tokenize("") == []

    def test_numbers_included_if_3chars(self):
        tokens = tokenize("abc 123 x")
        assert "abc" in tokens
        assert "123" in tokens
        assert "x" not in tokens


class TestScoreEntry:
    def test_no_query_tokens_returns_zero(self):
        entry = _make_entry()
        assert score_entry(entry, []) == 0.0

    def test_meta_hits_weight(self):
        entry = _make_entry(tags=["architecture"], type=MemoryType.ARCHITECTURE)
        tokens = ["architecture"]
        score = score_entry(entry, tokens)
        # meta_hits = 2 (tag "architecture" + type value "architecture")
        # 2 * 2.0 = 4.0, plus importance 0.5 * 0.4 = 0.2
        assert score >= 4.0

    def test_body_hits(self):
        entry = _make_entry(content="Skywalker uses memory system")
        tokens = ["skywalker"]
        score = score_entry(entry, tokens)
        # body_hits = 1
        assert score >= 1.0

    def test_recency_boost_14_days(self):
        now = datetime.now(timezone.utc)
        recent = _make_entry(updated_at=now - timedelta(days=5))
        old = _make_entry(updated_at=now - timedelta(days=40))
        tokens = ["test"]
        score_recent = score_entry(recent, tokens, now=now)
        score_old = score_entry(old, tokens, now=now)
        # recent 应比 old 多 0.3 的时效加成
        assert score_recent > score_old

    def test_recency_boost_30_days(self):
        now = datetime.now(timezone.utc)
        entry = _make_entry(updated_at=now - timedelta(days=20))
        tokens = ["test"]
        score = score_entry(entry, tokens, now=now)
        # 20天在 14~30 天区间，应有 0.1 加成
        base = 0.5 * 0.4  # importance only
        assert score >= base + 0.1

    def test_use_count_capped_at_5(self):
        entry_high = _make_entry(use_count=10)
        entry_cap = _make_entry(use_count=5)
        tokens = ["test"]
        score_high = score_entry(entry_high, tokens)
        score_cap = score_entry(entry_cap, tokens)
        # use_count 超过 5 时得分应相同
        assert abs(score_high - score_cap) < 0.01


class TestSearchEntries:
    def test_empty_query_returns_empty(self):
        entries = [_make_entry(content="hello world")]
        assert search_entries(entries, "") == []
        assert search_entries(entries, "   ") == []

    def test_empty_entries_returns_empty(self):
        assert search_entries([], "query") == []

    def test_single_match(self):
        entry = _make_entry(content="Skywalker agent runtime")
        results = search_entries([entry], "skywalker")
        assert len(results) == 1
        assert results[0].id == entry.id

    def test_multiple_entries_ranked(self):
        high = _make_entry(
            id="high",
            content="Python memory management",
            importance=0.9,
        )
        low = _make_entry(
            id="low",
            content="Unrelated content",
            importance=0.1,
        )
        results = search_entries([high, low], "python memory")
        assert len(results) == 2
        # high 应排在前面
        assert results[0].id == "high"

    def test_top_k_limits_results(self):
        entries = [_make_entry(id=f"e{i}", content=f"test {i}") for i in range(10)]
        results = search_entries(entries, "test", top_k=3)
        assert len(results) == 3

    def test_use_count_incremented(self):
        entry = _make_entry(content="searchable content")
        assert entry.use_count == 0
        search_entries([entry], "searchable")
        assert entry.use_count == 1

    def test_no_match_returns_empty(self):
        entry = _make_entry(content="hello world")
        results = search_entries([entry], "xyz123")
        assert len(results) == 0
```

---

### 第二天：short_term.py

这一天结束时，ConversationManager 和压缩器均为可工作、可测试的完整模块。它们负责单会话内的 token 管理和上下文压缩。

---

#### `memory/short_term.py` — 会话管理与压缩

**职责：** 管理单次会话的消息队列，增量追踪 token 使用量，在超限时触发压缩。压缩器将旧消息摘要为一条 system 消息，释放 token 空间。

**为什么需要独立文件：** ConversationManager 是有状态对象，生命周期与会话绑定，与 `base.py` 的无状态数据结构和 `long_term.py` 的持久化读写职责不同。独立后可单独测试滑动窗口和压缩触发逻辑。

**imports：**
```python
from __future__ import annotations
from abc import ABC, abstractmethod
from skywalker.core import Message, Role
from skywalker.memory.base import MemoryEntry
```
- `Message, Role`：操作消息队列的核心类型
- `MemoryEntry`：压缩生成的摘要可转化为 MemoryEntry 用于长期记忆

**`CompressorBase`（ABC）**
```python
class CompressorBase(ABC):
    @abstractmethod
    async def compress(self, messages: list[Message]) -> str: ...
```
- 输入：需要被压缩的旧消息列表
- 输出：摘要文本（纯字符串，不含 role 标记）
- 抽象接口，V2 由 LLMCompressor 实现，V5 由 SubAgentCompressor 实现

**`LLMCompressor(CompressorBase)`**
```python
class LLMCompressor(CompressorBase):
    def __init__(self, llm): ...

    async def compress(self, messages: list[Message]) -> str: ...
```
- `llm`：`llm/base.py` 定义的 LLM 接口实例
- `compress` 实现：将消息列表格式化为上下文，调用 LLM 生成摘要
- 摘要 prompt 要求 LLM 保留关键事实、决策和待办事项，丢弃冗余对话

**`SubAgentCompressor(CompressorBase)`**（V5 占位）
```python
class SubAgentCompressor(CompressorBase):
    async def compress(self, messages: list[Message]) -> str: ...
```
- 接口与 LLMCompressor 一致，V5 实现时替换内部逻辑即可

**`ConversationManager`**
```python
class ConversationManager:
    def __init__(self, compressor: CompressorBase, max_tokens: int, compress_threshold: float = 0.75): ...

    def add_message(self, msg: Message) -> None: ...

    def should_compress(self) -> bool: ...

    async def compress(self) -> None: ...

    @property
    def messages(self) -> list[Message]: ...

    @property
    def total_tokens(self) -> int: ...
```
- `max_tokens`：当前模型的上下文窗口大小
- `compress_threshold`：token 使用率超过此值（0.0~1.0）时 `should_compress()` 返回 True
- `add_message()`：追加消息并增量更新 token 计数，不触发压缩（由调用方决定何时压缩）
- `should_compress()`：检查 `total_tokens / max_tokens > compress_threshold`
- `compress()`：取 oldest 非 system 消息调用 compressor，生成摘要消息（role=SYSTEM，标记 `[SUMMARY]`），插入队列头部，删除被压缩的原始消息，重新计算 total_tokens
- `messages` 属性：返回当前队列的只读副本
- `total_tokens` 属性：返回当前 token 总量

**接口约定：**
- `add_message` 不做压缩，调用方（loop.py）在 OBSERVING 状态后主动检查 `should_compress()` 再调用 `compress()`
- `compress()` 是 async 方法，因为需要调用 LLM
- 压缩后的摘要消息 role 为 `Role.SYSTEM`，content 前缀 `[SUMMARY]`，便于后续识别

**完整代码：**

```python
# skywalker/memory/short_term.py

from __future__ import annotations

from abc import ABC, abstractmethod

from skywalker.core import Message, Role
from skywalker.memory.base import MemoryEntry


class CompressorBase(ABC):
    """压缩器抽象基类"""

    @abstractmethod
    async def compress(self, messages: list[Message]) -> str:
        """将消息列表压缩为摘要文本"""
        ...


class LLMCompressor(CompressorBase):
    """V2 实现：调用 LLM 生成摘要"""

    def __init__(self, llm):
        self._llm = llm

    async def compress(self, messages: list[Message]) -> str:
        """调用 LLM 将消息压缩为摘要"""
        # 格式化消息为上下文文本
        context_parts = []
        for msg in messages:
            role_name = msg.role.value.upper()
            context_parts.append(f"[{role_name}]: {msg.content}")
        context_text = "\n".join(context_parts)

        summary_prompt = (
            "请将以下对话历史压缩为简洁的摘要，保留关键事实、决策和待办事项，"
            "丢弃冗余的寒暄和重复内容。摘要应控制在 200 字以内。\n\n"
            f"对话历史：\n{context_text}"
        )

        summary_msg = Message(Role.USER, summary_prompt)
        return self._llm.chat([summary_msg])


class SubAgentCompressor(CompressorBase):
    """V5 占位：SubAgent 压缩器，接口与 LLMCompressor 一致"""

    async def compress(self, messages: list[Message]) -> str:
        raise NotImplementedError("SubAgentCompressor 将在 V5 实现")


class ConversationManager:
    """有状态的会话管理器，管理消息队列和 token 用量"""

    def __init__(
        self,
        compressor: CompressorBase,
        max_tokens: int,
        compress_threshold: float = 0.75,
    ):
        self._compressor = compressor
        self._max_tokens = max_tokens
        self._compress_threshold = compress_threshold
        self._messages: list[Message] = []
        self._total_tokens = 0
        # 导入 tokenizer 用于 token 估算
        from skywalker.agent.context import SimpleTokenizer
        self._tokenizer = SimpleTokenizer()

    def add_message(self, msg: Message) -> None:
        """追加消息并增量更新 token 计数"""
        self._messages.append(msg)
        self._total_tokens += self._tokenizer.estimate_message_tokens(msg)
        self._total_tokens += self._tokenizer.OVERHEAD_PER_MESSAGE

    def should_compress(self) -> bool:
        """检查是否需要触发压缩"""
        if self._max_tokens <= 0:
            return False
        usage = self._total_tokens / self._max_tokens
        return usage > self._compress_threshold

    async def compress(self) -> None:
        """执行压缩：将旧消息摘要为一条 system 消息"""
        if not self._messages:
            return

        # 分离系统消息和非系统消息
        system_msgs = [m for m in self._messages if m.role == Role.SYSTEM]
        non_system_msgs = [m for m in self._messages if m.role != Role.SYSTEM]

        if not non_system_msgs:
            return

        # 取前半部分非系统消息进行压缩（保留最近的消息）
        split_point = len(non_system_msgs) // 2
        to_compress = non_system_msgs[:split_point]
        to_keep = non_system_msgs[split_point:]

        if not to_compress:
            return

        # 调用压缩器生成摘要
        summary_text = await self._compressor.compress(to_compress)

        # 构造摘要消息
        summary_msg = Message(
            Role.SYSTEM,
            f"[SUMMARY] {summary_text}",
        )

        # 重建消息队列：系统消息 + 摘要 + 保留的消息
        self._messages = system_msgs + [summary_msg] + to_keep

        # 重新计算 token 总量
        self._total_tokens = self._tokenizer.estimate_total_tokens(self._messages)

    @property
    def messages(self) -> list[Message]:
        """返回当前消息队列的只读副本"""
        return list(self._messages)

    @property
    def total_tokens(self) -> int:
        """返回当前 token 总量"""
        return self._total_tokens
```

---

#### `tests/test_memory/test_short_term.py` — short_term.py 单元测试

核心测试场景：
- `add_message` 后 token 增量正确
- `should_compress` 在 token 低于阈值时返回 False，超过时返回 True
- `compress` 后消息数减少，token 总量下降，摘要消息被正确插入
- 系统消息不被压缩（只压缩非 system 消息）
- Mock CompressorBase 验证 compress 被正确调用

**完整代码：**

```python
# tests/test_memory/test_short_term.py

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from skywalker.core import Message, Role
from skywalker.memory.short_term import (
    CompressorBase,
    ConversationManager,
    LLMCompressor,
)


class StubCompressor(CompressorBase):
    """测试用压缩器，返回固定摘要"""

    def __init__(self, summary: str = "compressed summary"):
        self.summary = summary
        self.call_count = 0
        self.last_messages: list[Message] = []

    async def compress(self, messages: list[Message]) -> str:
        self.call_count += 1
        self.last_messages = list(messages)
        return self.summary


def _run(coro):
    """同步运行 async 函数的辅助"""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestConversationManagerAddMessage:
    def test_add_message_increases_token_count(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=1000)
        assert cm.total_tokens == 0

        cm.add_message(Message(Role.USER, "hello world"))
        assert cm.total_tokens > 0

    def test_add_multiple_messages_accumulates(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=1000)

        cm.add_message(Message(Role.USER, "first"))
        t1 = cm.total_tokens
        cm.add_message(Message(Role.ASSISTANT, "second"))
        t2 = cm.total_tokens
        assert t2 > t1

    def test_messages_property_returns_copy(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=1000)
        cm.add_message(Message(Role.USER, "hello"))

        msgs = cm.messages
        msgs.append(Message(Role.USER, "extra"))
        assert len(cm.messages) == 1


class TestShouldCompress:
    def test_below_threshold_returns_false(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000, compress_threshold=0.75)
        cm.add_message(Message(Role.USER, "short message"))
        assert cm.should_compress() is False

    def test_above_threshold_returns_true(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10, compress_threshold=0.5)
        # 添加足够多的消息使 token 超过阈值
        for i in range(20):
            cm.add_message(Message(Role.USER, f"message number {i} with some content"))
        assert cm.should_compress() is True

    def test_zero_max_tokens_returns_false(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=0, compress_threshold=0.75)
        cm.add_message(Message(Role.USER, "hello"))
        assert cm.should_compress() is False


class TestCompress:
    def test_compress_reduces_message_count(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)

        for i in range(10):
            cm.add_message(Message(Role.USER, f"message {i}"))

        before = len(cm.messages)
        _run(cm.compress())
        after = len(cm.messages)
        assert after < before

    def test_compress_inserts_summary_message(self):
        compressor = StubCompressor(summary="test summary")
        cm = ConversationManager(compressor, max_tokens=10000)

        for i in range(6):
            cm.add_message(Message(Role.USER, f"message {i}"))

        _run(cm.compress())

        summary_msgs = [m for m in cm.messages if "[SUMMARY]" in m.content]
        assert len(summary_msgs) == 1
        assert summary_msgs[0].role == Role.SYSTEM

    def test_compress_preserves_recent_messages(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)

        for i in range(6):
            cm.add_message(Message(Role.USER, f"message {i}"))

        _run(cm.compress())

        # 最近的消息应保留
        contents = [m.content for m in cm.messages]
        assert "message 5" in contents

    def test_compress_does_not_compress_system_messages(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)

        cm.add_message(Message(Role.SYSTEM, "system instruction"))
        for i in range(6):
            cm.add_message(Message(Role.USER, f"message {i}"))

        before_system = [m for m in cm.messages if m.role == Role.SYSTEM]
        _run(cm.compress())
        after_system = [m for m in cm.messages if m.role == Role.SYSTEM]

        # 系统消息数量应增加（原系统消息 + 摘要消息）
        assert len(after_system) >= len(before_system)

    def test_compress_calls_compressor(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)

        for i in range(6):
            cm.add_message(Message(Role.USER, f"message {i}"))

        _run(cm.compress())
        assert compressor.call_count == 1
        assert len(compressor.last_messages) > 0

    def test_compress_with_no_messages_does_nothing(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)
        _run(cm.compress())
        assert compressor.call_count == 0

    def test_compress_with_only_system_messages_does_nothing(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)
        cm.add_message(Message(Role.SYSTEM, "system only"))
        _run(cm.compress())
        assert compressor.call_count == 0

    def test_compress_reduces_token_count(self):
        compressor = StubCompressor()
        cm = ConversationManager(compressor, max_tokens=10000)

        for i in range(10):
            cm.add_message(Message(Role.USER, f"message number {i} with substantial content for testing"))

        before_tokens = cm.total_tokens
        _run(cm.compress())
        after_tokens = cm.total_tokens
        assert after_tokens < before_tokens
```

---

### 第三天：long_term.py + __init__.py

这一天结束时，MEMORY.md / USER.md 的读写模块可工作、可测试，`__init__.py` 导出公共 API。

---

#### `memory/long_term.py` — 持久化记忆读写

**职责：** 负责 MEMORY.md（项目级）和 USER.md（用户级）的读取、写入、条目增删。是 memory 子系统与文件系统的唯一接口。

**为什么需要独立文件：** 持久化逻辑涉及文件 I/O、路径解析、条目排序和截断，与 `base.py` 的纯数据结构和 `search.py` 的纯计算逻辑职责不同。独立后可 mock 文件系统单独测试。

**imports：**
```python
from __future__ import annotations
import os
from pathlib import Path
from datetime import datetime, timezone
from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.schema import parse_memory_md, serialize_memory_md
from skywalker.memory.search import search_entries
```
- `parse_memory_md, serialize_memory_md`：格式化读写
- `search_entries`：加载后支持按关键词检索

**`LongTermMemory`**
```python
class LongTermMemory:
    def __init__(self, file_path: str, max_entries: int = 100): ...

    def load(self) -> list[MemoryEntry]: ...

    def save(self, entries: list[MemoryEntry]) -> None: ...

    def add_entry(self, entry: MemoryEntry) -> None: ...

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...
```
- `file_path`：MEMORY.md 或 USER.md 的绝对路径
- `max_entries`：单文件最大条目数，save 时超出则丢弃最低 importance 的条目
- `load()`：读取文件内容，调用 `parse_memory_md` 解析；文件不存在时返回空列表
- `save()`：按 importance 降序排列，超过 max_entries 时截断，调用 `serialize_memory_md` 写入
- `add_entry()`：load → 追加 → save（幂等，重复调用不会产生重复条目，基于 id 去重）
- `search()`：load → search_entries，封装了"读文件 + 搜索"的常见模式

**`MemoryManager`**
```python
class MemoryManager:
    def __init__(self, project_memory: LongTermMemory, user_memory: LongTermMemory, compressor: CompressorBase): ...

    async def on_shutdown(self, state) -> None: ...

    def get_system_context(self) -> str: ...
```
- `on_shutdown()`：从 state.messages 提取关键信息（调用 LLM），写入 project_memory 和 user_memory
- `get_system_context()`：合并项目记忆和用户记忆为系统提示文本，注入优先级：用户级 > 项目级

**完整代码：**

```python
# skywalker/memory/long_term.py

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.schema import parse_memory_md, serialize_memory_md
from skywalker.memory.search import search_entries


class LongTermMemory:
    """持久化记忆存储，负责单个 MEMORY.md / USER.md 的读写"""

    def __init__(self, file_path: str, max_entries: int = 100):
        self._file_path = Path(os.path.expanduser(file_path))
        self._max_entries = max_entries

    def load(self) -> list[MemoryEntry]:
        """从文件加载记忆条目，文件不存在时返回空列表"""
        if not self._file_path.exists():
            return []
        content = self._file_path.read_text(encoding="utf-8")
        return parse_memory_md(content)

    def save(self, entries: list[MemoryEntry]) -> None:
        """保存记忆条目到文件，超过 max_entries 时截断低重要性条目"""
        # 按 importance 降序排列
        sorted_entries = sorted(entries, key=lambda e: e.importance, reverse=True)
        # 截断超出部分
        if len(sorted_entries) > self._max_entries:
            sorted_entries = sorted_entries[: self._max_entries]

        content = serialize_memory_md(sorted_entries)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_path.write_text(content, encoding="utf-8")

    def add_entry(self, entry: MemoryEntry) -> None:
        """添加一条记忆（幂等，基于 id 去重）"""
        entries = self.load()
        # 去重：移除相同 id 的旧条目
        entries = [e for e in entries if e.id != entry.id]
        entries.append(entry)
        self.save(entries)

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """加载文件后执行关键词搜索"""
        entries = self.load()
        return search_entries(entries, query, top_k=top_k)


class MemoryManager:
    """统一管理项目级和用户级记忆"""

    def __init__(
        self,
        project_memory: LongTermMemory,
        user_memory: LongTermMemory,
        compressor,
    ):
        self._project_memory = project_memory
        self._user_memory = user_memory
        self._compressor = compressor

    async def on_shutdown(self, state) -> None:
        """对话结束时提取关键信息并写回记忆文件"""
        from skywalker.core import Message, Role

        if not state.messages:
            return

        # 调用压缩器提取摘要
        try:
            summary = await self._compressor.compress(state.messages)
        except Exception:
            summary = None

        if not summary:
            return

        now = datetime.now(timezone.utc)

        # 写入项目记忆
        project_entry = MemoryEntry(
            id=f"session-{now.strftime('%Y%m%d%H%M%S')}",
            type=MemoryType.FACT,
            content=summary,
            importance=0.6,
            source="session",
            created_at=now,
            updated_at=now,
            tags=["session-summary"],
        )
        self._project_memory.add_entry(project_entry)

    def get_system_context(self) -> str:
        """合并项目记忆和用户记忆为系统提示文本"""
        parts: list[str] = []

        # 用户记忆优先级更高
        user_entries = self._user_memory.load()
        if user_entries:
            user_texts = [e.content for e in user_entries[:5]]
            parts.append("用户偏好：\n" + "\n".join(f"- {t}" for t in user_texts))

        # 项目记忆
        project_entries = self._project_memory.load()
        if project_entries:
            project_texts = [e.content for e in project_entries[:5]]
            parts.append("项目记忆：\n" + "\n".join(f"- {t}" for t in project_texts))

        return "\n\n".join(parts)
```

**MEMORY.md 格式规范：**

```markdown
---
project: skywalker
version: 1
updated: 2026-06-11T10:00:00Z
---

## [architecture] Four-layer memory system
- importance: 0.9
- tags: [architecture, memory]
- source: inference
- created_at: 2026-06-01T10:00:00Z
- use_count: 3

Skywalker uses working / episodic / long-term / procedural memory layers.
```

**解析规则：**
- frontmatter 可选，缺失时从第一个 `## ` 开始解析
- `importance` 缺失默认 `0.5`，`tags` 缺失默认 `[]`，`use_count` 缺失默认 `0`
- `##` 到下一个 `##` 之间的段落为 `MemoryEntry.content`
- type 从标题行 `[type]` 提取，无法匹配 MemoryType 时默认 `FACT`

**写入规则：**
- shutdown 时全量覆写，按 importance 降序排列
- 超过 max_memory_entries 时丢弃最低 importance 的条目
- updated 写入当前 UTC 时间，ISO 8601 格式

USER.md 格式与 MEMORY.md 相同，路径为 `~/.skywalker/USER.md`。

---

#### `memory/__init__.py` — 包初始化

**职责：** 导出公共 API，让 `loop.py` 只需 `from skywalker.memory import MemoryManager`。

```python
from skywalker.memory.base import MemoryType, MemoryEntry, MemoryStore
from skywalker.memory.short_term import ConversationManager, CompressorBase, LLMCompressor
from skywalker.memory.long_term import LongTermMemory, MemoryManager
from skywalker.memory.search import search_entries

__all__ = [
    "MemoryType", "MemoryEntry", "MemoryStore",
    "ConversationManager", "CompressorBase", "LLMCompressor",
    "LongTermMemory", "MemoryManager",
    "search_entries",
]
```

---

#### `tests/test_memory/test_long_term.py` — long_term.py 单元测试

核心测试场景：
- 文件不存在时 load 返回空列表
- save 后 load 往返一致
- add_entry 幂等性（重复添加同 id 不产生重复）
- 超过 max_entries 时最低 importance 的条目被丢弃
- search 正确调用 search_entries 并返回结果

**完整代码：**

```python
# tests/test_memory/test_long_term.py

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from skywalker.memory.base import MemoryEntry, MemoryType
from skywalker.memory.long_term import LongTermMemory, MemoryManager
from skywalker.memory.short_term import CompressorBase


def _make_entry(id: str = "test-1", importance: float = 0.5, **kwargs) -> MemoryEntry:
    now = datetime.now(timezone.utc)
    defaults = {
        "id": id,
        "type": MemoryType.FACT,
        "content": f"content for {id}",
        "importance": importance,
        "source": "user",
        "created_at": now,
        "updated_at": now,
        "tags": [],
        "use_count": 0,
    }
    defaults.update(kwargs)
    return MemoryEntry(**defaults)


@pytest.fixture
def tmp_memory_path(tmp_path):
    return str(tmp_path / "MEMORY.md")


class TestLongTermMemoryLoad:
    def test_nonexistent_file_returns_empty(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        assert ltm.load() == []

    def test_load_after_save(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        entry = _make_entry()
        ltm.save([entry])
        loaded = ltm.load()
        assert len(loaded) == 1
        assert loaded[0].type == entry.type
        assert loaded[0].importance == entry.importance
        assert loaded[0].content == entry.content


class TestLongTermMemorySave:
    def test_save_creates_parent_dirs(self, tmp_path):
        nested = str(tmp_path / "a" / "b" / "MEMORY.md")
        ltm = LongTermMemory(nested)
        ltm.save([_make_entry()])
        assert Path(nested).exists()

    def test_save_sorted_by_importance_desc(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        low = _make_entry(id="low", importance=0.2)
        high = _make_entry(id="high", importance=0.9)
        ltm.save([low, high])
        loaded = ltm.load()
        assert loaded[0].importance >= loaded[1].importance

    def test_save_truncates_beyond_max_entries(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path, max_entries=3)
        entries = [_make_entry(id=f"e{i}", importance=i * 0.1) for i in range(10)]
        ltm.save(entries)
        loaded = ltm.load()
        assert len(loaded) <= 3


class TestLongTermMemoryAddEntry:
    def test_add_entry_idempotent(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        entry = _make_entry(id="same-id")
        ltm.add_entry(entry)
        ltm.add_entry(entry)
        loaded = ltm.load()
        assert len(loaded) == 1

    def test_add_different_entries(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        ltm.add_entry(_make_entry(id="a"))
        ltm.add_entry(_make_entry(id="b"))
        loaded = ltm.load()
        assert len(loaded) == 2

    def test_add_updates_existing_entry(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        old = _make_entry(id="x", importance=0.3, content="old")
        new = _make_entry(id="x", importance=0.8, content="new")
        ltm.add_entry(old)
        ltm.add_entry(new)
        loaded = ltm.load()
        assert len(loaded) == 1
        assert loaded[0].content == "new"
        assert loaded[0].importance == 0.8


class TestLongTermMemorySearch:
    def test_search_returns_matching_entries(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        ltm.add_entry(_make_entry(id="match", content="Python memory management"))
        ltm.add_entry(_make_entry(id="no-match", content="unrelated"))
        results = ltm.search("python")
        assert any(r.id == "match" for r in results)

    def test_search_empty_file(self, tmp_memory_path):
        ltm = LongTermMemory(tmp_memory_path)
        assert ltm.search("query") == []


class StubCompressor(CompressorBase):
    async def compress(self, messages):
        return "shutdown summary"


class TestMemoryManager:
    def _make_state(self, messages=None):
        from unittest.mock import MagicMock
        state = MagicMock()
        state.messages = messages or []
        return state

    def test_on_shutdown_saves_summary(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()
        manager = MemoryManager(proj, user, compressor)

        from skywalker.core import Message, Role
        state = self._make_state([
            Message(Role.USER, "hello"),
            Message(Role.ASSISTANT, "hi there"),
        ])

        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.on_shutdown(state))
        loop.close()

        loaded = proj.load()
        assert len(loaded) >= 1
        assert "shutdown summary" in loaded[0].content

    def test_on_shutdown_empty_messages_does_nothing(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()
        manager = MemoryManager(proj, user, compressor)

        state = self._make_state([])
        loop = asyncio.new_event_loop()
        loop.run_until_complete(manager.on_shutdown(state))
        loop.close()

        assert proj.load() == []

    def test_get_system_context_merges_memories(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()

        proj.add_entry(_make_entry(id="p1", content="project info"))
        user.add_entry(_make_entry(id="u1", content="user preference"))

        manager = MemoryManager(proj, user, compressor)
        context = manager.get_system_context()

        assert "project info" in context
        assert "user preference" in context

    def test_get_system_context_user_higher_priority(self, tmp_path):
        proj_path = str(tmp_path / "MEMORY.md")
        user_path = str(tmp_path / "USER.md")
        proj = LongTermMemory(proj_path)
        user = LongTermMemory(user_path)
        compressor = StubCompressor()

        proj.add_entry(_make_entry(id="p1", content="project info"))
        user.add_entry(_make_entry(id="u1", content="user preference"))

        manager = MemoryManager(proj, user, compressor)
        context = manager.get_system_context()

        # 用户记忆应出现在项目记忆之前
        user_pos = context.find("user preference")
        proj_pos = context.find("project info")
        assert user_pos < proj_pos
```

---

### 第四天：集成

这一天结束时，完整的 startup → conversation → shutdown 流程跑通，MEMORY.md 读写验证通过。

---

#### `core.py` — 修改

**改动：`AgentState` 添加 `project_root`**

```python
project_root: str | None = None
```

字段默认为 `None`，所有现有的 `AgentState()` 调用无需修改即可继续工作。V2 中 `cli/main.py` 在初始化时传入项目根目录路径，`long_term.py` 用它定位 MEMORY.md。

#### `agent/context.py` — 修改

**改动：添加 `should_compress()` 存根**

`loop.py` 在 V2 中需要在每次 ASSISTANT 消息追加后调用此方法决定是否触发压缩。V1 中该方法不存在，若直接在 loop.py 中调用会抛出 AttributeError。V1 阶段先添加存根以保持向后兼容，V2 实现时由 ConversationManager 覆盖。

```python
def should_compress(self, messages: list[Message]) -> bool:
    return False
```

#### `agent/loop.py` — 修改

**改动：TERMINATED 状态挂载 memory 写回钩子**

V2 需要在对话结束时将关键信息写回 MEMORY.md / USER.md。TERMINATED 状态是唯一的统一出口，写回逻辑挂在这里，loop 不感知细节。

```python
case "TERMINATED":
    await memory_manager.on_shutdown(state)
```

#### `config/settings.py` — 修改

新增 memory 相关配置项：

```python
compressor_type: str = "llm"           # "llm" | "subagent"（V5）
memory_dir: str = "~/.skywalker/memory"
project_memory_file: str = "MEMORY.md"
compress_threshold: float = 0.75       # token 使用率超过此值触发压缩
max_memory_entries: int = 100          # 单文件最大条目数
```

#### `cli/main.py` — 修改

**启动链路：**
```
cli/main.py
  → 读取 settings（project_root, memory_dir）
  → long_term.load_project_memory(project_root)   # 读 MEMORY.md
  → long_term.load_user_memory()                   # 读 USER.md
  → 注入 system prompt 静态区
  → 初始化 ConversationManager
  → 启动 loop
```

注入优先级：用户级 > 项目级 > 会话摘要

**完整代码（修改后的 cli/main.py）：**

```python
# skywalker/cli/main.py — V2 完整版

import asyncio
import os
import sys
from pathlib import Path

from rich.console import Console
from readchar import readkey, key

from skywalker.core import AgentState, Message, Role
from skywalker.agent.loop import run_loop
from skywalker.llm.anthropic import AnthropicClient
from skywalker.memory import (
    ConversationManager,
    LLMCompressor,
    LongTermMemory,
    MemoryManager,
)
from skywalker.agent.context import SimpleTokenizer

console = Console()

# V2 配置
MEMORY_DIR = os.path.expanduser("~/.skywalker/memory")
PROJECT_MEMORY_FILE = "MEMORY.md"
COMPRESS_THRESHOLD = 0.75
MAX_TOKENS = 8000  # 模型上下文窗口大小


def read_line_with_ctrlz(prompt: str) -> str | None:
    """使用 readchar 实现 CTRL+Z 退出"""
    console.print(prompt, end="")
    sys.stdout.flush()
    line = []
    while True:
        ch = readkey()
        if ch == key.CTRL_Z:
            console.print()
            return None
        elif ch == key.ENTER:
            console.print()
            break
        elif ch == key.BACKSPACE:
            if line:
                line.pop()
                sys.stdout.write('\b \b')
                sys.stdout.flush()
        elif len(ch) == 1 and ch.isprintable():
            line.append(ch)
            sys.stdout.write(ch)
            sys.stdout.flush()
    return ''.join(line)


def _init_memory(project_root: str):
    """初始化记忆系统"""
    # 项目记忆路径
    project_memory_path = os.path.join(project_root, PROJECT_MEMORY_FILE)
    project_memory = LongTermMemory(project_memory_path)

    # 用户记忆路径
    user_memory_path = os.path.join(MEMORY_DIR, "USER.md")
    user_memory = LongTermMemory(user_memory_path)

    # 压缩器
    llm = AnthropicClient()
    compressor = LLMCompressor(llm)

    # 记忆管理器
    memory_manager = MemoryManager(project_memory, user_memory, compressor)

    return memory_manager, compressor


def _build_system_prompt(memory_manager: MemoryManager) -> str:
    """构建系统提示，注入记忆上下文"""
    base_prompt = "你是一个有用的助手。简洁回答问题。"
    memory_context = memory_manager.get_system_context()
    if memory_context:
        return f"{base_prompt}\n\n{memory_context}"
    return base_prompt


def main():
    console.print("[bold orange1]Skywalker Agent[/bold orange1] - 按下 'Ctrl+Z' 退出\n")

    # 获取项目根目录
    project_root = os.getcwd()

    # 初始化记忆系统
    memory_manager, compressor = _init_memory(project_root)

    # 加载记忆并显示
    project_entries = memory_manager._project_memory.load()
    user_entries = memory_manager._user_memory.load()
    total = len(project_entries) + len(user_entries)
    console.print(f"[dim]已加载 {total} 条记忆（项目：{len(project_entries)}，用户：{len(user_entries)}）[/dim]\n")

    # 初始化 LLM 和会话管理器
    llm = AnthropicClient()
    conv_manager = ConversationManager(
        compressor=compressor,
        max_tokens=MAX_TOKENS,
        compress_threshold=COMPRESS_THRESHOLD,
    )

    # 构建带记忆的系统提示
    system_prompt = _build_system_prompt(memory_manager)

    state = AgentState(project_root=project_root)

    while True:
        user_input = read_line_with_ctrlz("[bold blue]You:[/bold blue] ")
        if user_input is None:
            console.print("正在保存记忆...")
            # shutdown 时写回记忆
            loop = asyncio.new_event_loop()
            loop.run_until_complete(memory_manager.on_shutdown(state))
            loop.close()
            console.print("已退出，记忆已保存！")
            break

        if user_input.strip().lower() == "exit":
            console.print("正在保存记忆...")
            loop = asyncio.new_event_loop()
            loop.run_until_complete(memory_manager.on_shutdown(state))
            loop.close()
            console.print("记忆已保存！")
            break

        if not user_input.strip():
            continue

        # 添加用户消息到会话管理器
        user_msg = Message(Role.USER, user_input)
        conv_manager.add_message(user_msg)
        state.messages.append(user_msg)

        # 检查是否需要压缩
        if conv_manager.should_compress():
            console.print("[dim]正在压缩历史消息...[/dim]")
            loop = asyncio.new_event_loop()
            loop.run_until_complete(conv_manager.compress())
            loop.close()
            # 同步压缩后的消息到 state
            state.messages = conv_manager.messages

        # 调用 LLM
        try:
            response = llm.chat(conv_manager.messages, system=system_prompt)
            assistant_msg = Message(Role.ASSISTANT, response)
            conv_manager.add_message(assistant_msg)
            state.messages.append(assistant_msg)
            state.current_response = response
        except Exception as e:
            state.loop_state.error = str(e)
            console.print(f"[bold red]Error:[/bold red] {e}\n")
            continue

        if state.current_response:
            console.print(f"[bold cyan]Agent:[/bold cyan] {state.current_response}\n")


if __name__ == "__main__":
    main()
```

#### `agent/loop.py` — 完整修改代码

```python
# skywalker/agent/loop.py — V2 完整版

import asyncio

from skywalker.llm.base import LLMClient
from skywalker.core import AgentState, LoopPhase, LoopState, Message, Role
from skywalker.agent.context import SimpleTokenizer
from skywalker.memory import ConversationManager, MemoryManager

__all__ = ["AgentState", "LoopPhase", "LoopState", "Message", "Role"]

SYSTEM_PROMPT = "你是一个有用的助手。简洁回答问题。"


async def run_loop(
    state: AgentState,
    llm: LLMClient,
    user_input: str,
    conv_manager: ConversationManager | None = None,
    memory_manager: MemoryManager | None = None,
    system_prompt: str | None = None,
) -> AgentState:
    """运行一次完整的对话循环：INIT → THINKING → TERMINATED"""

    state.messages.append(Message(Role.USER, user_input))
    state.loop_state.phase = LoopPhase.THINKING

    # 使用会话管理器的消息列表（如果提供）
    messages = conv_manager.messages if conv_manager else state.messages
    prompt = system_prompt or SYSTEM_PROMPT

    try:
        response = llm.chat(messages, system=prompt)
        state.messages.append(Message(Role.ASSISTANT, response))

        # 会话管理器追加消息
        if conv_manager:
            conv_manager.add_message(Message(Role.ASSISTANT, response))
            # 检查是否需要压缩
            if conv_manager.should_compress():
                await conv_manager.compress()
                state.messages = conv_manager.messages

        state.current_response = response
        state.loop_state.phase = LoopPhase.TERMINATED
    except Exception as e:
        state.loop_state.error = str(e)
        state.loop_state.phase = LoopPhase.TERMINATED

    return state


async def run_loop_with_shutdown(
    state: AgentState,
    llm: LLMClient,
    user_input: str,
    conv_manager: ConversationManager,
    memory_manager: MemoryManager,
    system_prompt: str,
) -> AgentState:
    """带 shutdown 钩子的对话循环"""
    state = await run_loop(
        state, llm, user_input,
        conv_manager=conv_manager,
        memory_manager=memory_manager,
        system_prompt=system_prompt,
    )
    return state


async def shutdown(memory_manager: MemoryManager, state: AgentState) -> None:
    """对话结束时的清理钩子，写回记忆"""
    await memory_manager.on_shutdown(state)
```

#### `config/settings.py` — 完整代码

```python
# skywalker/config/settings.py — V2 完整版

from dataclasses import dataclass, field


@dataclass
class Settings:
    """Skywalker 全局配置"""

    # LLM 配置
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096

    # 记忆系统配置
    compressor_type: str = "llm"           # "llm" | "subagent"（V5）
    memory_dir: str = "~/.skywalker/memory"
    project_memory_file: str = "MEMORY.md"
    compress_threshold: float = 0.75       # token 使用率超过此值触发压缩
    max_memory_entries: int = 100          # 单文件最大条目数

    # 上下文配置
    context_window: int = 8000             # 模型上下文窗口大小

    # 项目配置
    project_root: str = "."


# 全局设置实例
settings = Settings()
```

#### 集成验证

完整流程：
1. 启动 → 加载 MEMORY.md 和 USER.md → 注入 system prompt
2. 对话中 → ConversationManager 管理消息 → 超限时触发压缩
3. 退出 → TERMINATED → on_shutdown → 写回 MEMORY.md / USER.md

---

## 6. 核心逻辑链路

### 6.1 启动链路

```
cli/main.py
  → 读取 settings（project_root, memory_dir）
  → long_term.load_project_memory(project_root)   # 读 MEMORY.md
  → long_term.load_user_memory()                   # 读 USER.md
  → 注入 system prompt 静态区
  → 初始化 ConversationManager
  → 启动 loop
```

注入优先级：用户级 > 项目级 > 会话摘要

### 6.2 对话中链路

```
loop: OBSERVING 状态
  → ConversationManager.add_message(msg)
      → 增量计算 token
      → should_compress() ?
          → 否：继续
          → 是：compressor.compress(old_messages) → summary_str
                → 插入 summary message（role=system，标记[SUMMARY]）
                → 删除被压缩的原始消息
                → 更新 total_tokens
```

### 6.3 退出链路

```
loop: TERMINATED 状态
  → memory_manager.on_shutdown(state)
      → 提取本次会话关键信息（调用 LLM）
      → long_term.write_project_memory(entries)   # 写回 MEMORY.md
      → long_term.write_user_memory(entries)       # 写回 USER.md
```

---

## 7. 验证方式

### 7.1 单元测试（`tests/test_memory/`）

- `test_base.py`：MemoryEntry 构造、MemoryType 枚举映射、tags 默认值隔离
- `test_schema.py`：frontmatter 有/无、缺字段默认值、type 默认 FACT、round-trip 往返
- `test_search.py`：空索引、单条匹配、多条排序、中英文分词、时效加成、use_count 上限
- `test_short_term.py`：token 增量、阈值判断、压缩后消息减少、system 消息不被压缩
- `test_long_term.py`：文件不存在、读写往返、add_entry 幂等、max_entries 截断

### 7.2 集成测试

完整 startup → conversation → shutdown 流程：
1. 初始化 MemoryManager，加载空的 MEMORY.md
2. 进行多轮对话，验证 ConversationManager token 追踪正确
3. 触发压缩，验证摘要消息被插入
4. 触发 shutdown，验证 MEMORY.md 被写入
5. 再次启动，验证上次写入的内容被正确加载并注入 system prompt

### 7.3 手动验证

- 启动 skywalker，确认终端输出"已加载 N 条记忆"（N ≥ 0）
- 发送消息，观察 token 使用量变化
- 输入多轮对话触发压缩，确认摘要消息出现
- Ctrl+C 退出，打开 MEMORY.md 确认内容已更新
- 再次启动，确认上次记录的内容出现在系统提示中

---

## 8. 关键文件清单

| 文件 | 操作 | 阶段 | 说明 |
|------|------|------|------|
| `skywalker/core.py` | 修改 | 第四天 | AgentState 新增 project_root |
| `skywalker/agent/context.py` | 修改 | 第四天 | 添加 should_compress() 存根 |
| `skywalker/agent/loop.py` | 修改 | 第四天 | TERMINATED 挂载写回钩子 |
| `skywalker/config/settings.py` | 修改 | 第四天 | 新增 memory 相关配置 |
| `skywalker/cli/main.py` | 修改 | 第四天 | 启动/关闭链路集成 |
| `skywalker/memory/__init__.py` | 新建 | 第三天 | 导出公共 API |
| `skywalker/memory/base.py` | 新建 | 第一天 | MemoryType, MemoryEntry, MemoryStore |
| `skywalker/memory/schema.py` | 新建 | 第一天 | frontmatter 解析，md 格式定义 |
| `skywalker/memory/search.py` | 新建 | 第一天 | 启发式检索，多维度评分 |
| `skywalker/memory/short_term.py` | 新建 | 第二天 | ConversationManager + Compressor |
| `skywalker/memory/long_term.py` | 新建 | 第三天 | MEMORY.md / USER.md 读写 |
| `tests/test_memory/test_base.py` | 新建 | 第一天 | MemoryEntry 构造、MemoryType 映射 |
| `tests/test_memory/test_schema.py` | 新建 | 第一天 | frontmatter 有无、缺字段默认值 |
| `tests/test_memory/test_search.py` | 新建 | 第一天 | 空索引、单条、多条评分排序 |
| `tests/test_memory/test_short_term.py` | 新建 | 第二天 | 滑动窗口、压缩触发、摘要插入 |
| `tests/test_memory/test_long_term.py` | 新建 | 第三天 | 读写、frontmatter 兼容、importance 排序 |
