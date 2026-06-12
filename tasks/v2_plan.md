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

`long_term.py` 需要知道当前项目根目录才能定位 MEMORY.md。
AgentState 是贯穿整个 loop 的状态容器，project_root 放这里最自然，
loop.py 初始化时从 cli 传入，long_term.py 从 state 里取。

```python
project_root: str | None = None
```

默认 None，现有调用无需修改。

### 3.2 `agent/context.py` — 添加 should_compress() 钩子

loop.py 在 OBSERVING 状态后需要判断是否触发压缩。
V1 无此方法，直接调用会 AttributeError。
V2 由 ConversationManager 实现此方法，context.py 先留存根保持兼容。

```python
def should_compress(self, messages: list[Message]) -> bool:
    return False  # V2 由 ConversationManager 覆盖
```

### 3.3 `agent/loop.py` — TERMINATED 挂载写回钩子

V2 需要在对话结束时将关键信息写回 MEMORY.md / USER.md。
TERMINATED 状态是唯一的统一出口，写回逻辑挂在这里，loop 不感知细节。

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

## 5. 核心逻辑链路

### 5.1 启动链路

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

### 5.2 对话中链路

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

### 5.3 退出链路

```
loop: TERMINATED 状态
  → memory_manager.on_shutdown(state)
      → 提取本次会话关键信息（调用 LLM）
      → long_term.write_project_memory(entries)   # 写回 MEMORY.md
      → long_term.write_user_memory(entries)       # 写回 USER.md
```

---

## 6. 关键接口定义

### base.py

```python
class MemoryType(Enum):
    FACT = "fact"
    PREFERENCE = "preference"
    ARCHITECTURE = "architecture"
    BUGFIX = "bugfix"

@dataclass
class MemoryEntry:
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
    def add(self, entry: MemoryEntry) -> None: ...
    def get(self, id: str) -> MemoryEntry | None: ...
    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]: ...
    def delete(self, id: str) -> bool: ...
```

### short_term.py 压缩接口

```python
class CompressorBase(ABC):
    @abstractmethod
    async def compress(self, messages: list[Message]) -> str: ...

class LLMCompressor(CompressorBase):
    # V2 实现，调用 llm/base.py 生成摘要
    async def compress(self, messages: list[Message]) -> str: ...

class SubAgentCompressor(CompressorBase):
    # V5 占位，接口一致
    async def compress(self, messages: list[Message]) -> str: ...
```

### search.py 评分方案（参考 OpenHarness）

```
score = meta_hits * 2.0        # 标题/描述命中
      + body_hits               # 正文命中
      + importance * 0.4        # 重要性权重
      + min(use_count, 5) * 0.1 # 使用频率（上限5）
      + recency_boost            # 时效加成（14天内+0.3，30天内+0.1）
```

分词：ASCII 3字符以上词 + 汉字单字符，支持中英文混合查询。

---

## 7. MEMORY.md 格式规范

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

## 8. 实现阶段

```
第一天：base.py + schema.py + search.py
        三个文件互不依赖或单向依赖，当天写完当天测试

第二天：short_term.py（ConversationManager + Compressor）
        依赖 base.py + llm/base.py，当天写完当天测试

第三天：long_term.py + __init__.py
        依赖 base.py + schema.py + search.py，当天写完当天测试

第四天：集成
        修改 core.py / context.py / loop.py / settings.py
        跑完整 startup → conversation → shutdown 流程
        验证 MEMORY.md 写入和读取
```

---

## 9. 关键文件清单

| 文件 | 操作 | 阶段 | 说明 |
|------|------|------|------|
| `skywalker/core.py` | 修改 | 第四天 | AgentState 新增 project_root |
| `skywalker/agent/context.py` | 修改 | 第四天 | 添加 should_compress() 存根 |
| `skywalker/agent/loop.py` | 修改 | 第四天 | TERMINATED 挂载写回钩子 |
| `skywalker/config/settings.py` | 修改 | 第四天 | 新增 memory 相关配置 |
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