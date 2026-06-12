# Skywalker Agent V2 Memory System 设计文档

## 1. 项目背景

### 1.1 V1 现状

V1 已完成核心功能：
- `core.py`：Message、AgentState 类型定义
- `context.py`：SimpleTokenizer 粗略 token 计算 + 截断
- `loop.py`：状态机循环 INIT→THINKING→TERMINATED
- `cli/main.py`：CLI 交互，支持 Ctrl+Z 退出
- `llm/`：LLM 抽象接口 + Anthropic 实现

### 1.2 V1 存在的问题

1. **对话历史无限增长**：没有调用 truncate_messages，token 会持续累积
2. **无法跨会话保留知识**：每次启动都是全新对话
3. **缺少上下文压缩**：长对话会导致 token 超限
4. **Role.SYSTEM 缺失**：truncate_messages 中检查 `msg.role == "system"` 永远为 False
5. **should_compress 未预留**：V2 压缩逻辑没有接口钩子

### 1.3 V2 目标

实现四层 Memory 架构，支持：
- 跨会话记忆持久化（MEMORY.md）
- 单会话滑动窗口 + 压缩
- 上下文投影（token 预算管理）
- BM25 关键词检索

---

## 2. 四层 Memory 架构

```
Working Memory   → context.py        已在V1，每次API调用投影最近N轮
Episodic         → short_term.py     单次任务轨迹 + 滑动窗口 + 压缩
Long-term        → long_term.py      MEMORY.md / 项目根目录，跨会话
Procedural       → skills/           V3之后，Agent自写可复用脚本
```

### 2.1 各层职责

| 层级 | 模块 | 作用域 | 持久化 |
|------|------|--------|--------|
| Working | `working.py` (扩展 context.py) | 当前 API 调用 | 内存，单次调用 |
| Episodic | `short_term.py` | 单次会话轨迹 | 内存，单会话 |
| Long-term | `long_term.py` | 跨会话知识 | `MEMORY.md` 磁盘 |
| Procedural | `skills/` (V3) | Agent 可复用脚本 | 文件磁盘 |

### 2.2 架构图

```
                        +-----------------------+
                        |    cli/main.py        |
                        |  startup: load LTM    |
                        |  shutdown: write LTM  |
                        +-----------+-----------+
                                    |
                        +-----------v-----------+
                        |     loop.py           |
                        |  run_loop()           |
                        |  post-hook: compress  |
                        +-----------+-----------+
                                    |
               +--------------------+--------------------+
               |                    |                    |
    +----------v-------+  +--------v--------+  +--------v--------+
    |  Working Memory  |  | Episodic Memory |  | Long-term Memory|
    |  (context.py)    |  | (short_term.py) |  | (long_term.py)  |
    |                  |  |                 |  |                 |
    | SimpleTokenizer  |  | ConversationMgr |  | MemoryMDStore   |
    | truncate_messages|  | sliding window  |  | MEMORY.md R/W   |
    | project to API   |  | + compression   |  | YAML frontmatter|
    +--------+---------+  +--------+--------+  +--------+--------+
             |                     |                    |
             +---------------------+--------------------+
                                   |
                        +----------v---------+
                        |   retrieval.py     |
                        |   BM25Retriever    |
                        |   (vector later)   |
                        +--------------------+
```

---

## 3. 模块目录结构

```
skywalker/
├── core.py                    # 核心类型定义（Message, AgentState, Role）
├── agent/
│   ├── context.py             # SimpleTokenizer + WorkingMemory
│   └── loop.py                # 状态机循环，集成压缩钩子
├── cli/
│   └── main.py                # CLI 入口，启动/关闭流程
├── llm/
│   ├── base.py                # LLMClient 抽象接口
│   └── anthropic.py           # Anthropic 实现
└── memory/                    # V2 新增
    ├── __init__.py            # 包初始化，导出公共 API
    ├── base.py                # 抽象接口（MemoryType, MemoryEntry, MemoryStore）
    ├── working.py             # WorkingMemory（上下文投影）
    ├── short_term.py          # ConversationManager（滑动窗口 + 压缩）
    ├── long_term.py           # MemoryMDStore（MEMORY.md 读写）
    └── retrieval.py           # BM25Retriever（关键词检索）
```

---

## 4. 数据流转

### 4.1 启动流程

```
cli/main.py: main()
    |
    +--> AnthropicClient()                       # 已有
    +--> AgentState(project_root=".")            # 已有，新增 project_root
    |
    +--> MemoryMDStore(project_root).load()      # 新增：扫描 MEMORY.md
    |       |
    |       +--> 如果文件存在：解析条目
    |       +--> 如果不存在：entries = []
    |
    +--> system_prompt = long_term.inject_into_system_prompt(SYSTEM_PROMPT)
    |       # 追加 "## Project Memory\n- [tag] entry content\n..."
    |       # 到基础系统提示
    |
    +--> state.system_prompt = system_prompt     # 存储富化提示
    |
    +--> ConversationManager()                   # 新增：初始化 episodic memory
```

### 4.2 对话轮次流程

```
run_loop(state, llm, user_input)
    |
    +--> state.messages.append(Message(USER, user_input))         # 已有
    |
    +--> projected = working_memory.project(state.messages)       # 新增 (V2)
    |       # 截断以适应 token 预算
    |
    +--> response = llm.chat(projected, system=state.system_prompt)  # 修改
    |       # 使用富化系统提示而非硬编码
    |
    +--> state.messages.append(Message(ASSISTANT, response))      # 已有
    |
    +--> episodic.add_turn(user_msg, assistant_msg)               # 新增 (V2)
    |       # 在滑动窗口中追踪
    |
    +--> if working_memory.should_compress(state.messages):       # 新增钩子
    |        episodic.compress()                                  # V2：摘要旧轮次
    |
    +--> state.current_response = response                        # 已有
```

### 4.3 关闭流程

```
cli/main.py: main() -- 用户按 Ctrl+Z 或输入 "exit"
    |
    +--> if state.messages:                                       # 新增
    |       |
    |       +--> entries = episodic.to_memory_entries()
    |       |       # 将会话轨迹转换为 MemoryEntry 对象
    |       |
    |       +--> # 过滤：只写入 importance > 阈值的条目
    |       |       # 或用户明确要求记住的条目
    |       |
    |       +--> for entry in entries:
    |       |        long_term.add(entry)
    |       |
    |       +--> long_term.save()
    |               # 写入 MEMORY.md 到磁盘
    |
    +--> console.print("已退出,下次见！")                          # 已有
```

---

## 5. MEMORY.md 文件格式

```markdown
---
project: skywalker
version: 1
updated: 2026-06-11T10:00:00
entries: 3
---

## [architecture] Project uses four-layer memory
- importance: 0.9
- tags: [architecture, design]
- source: user

Skywalker Agent uses working/episodic/long-term/procedural memory layers.
Working memory handles context projection, episodic handles session trajectory.

## [preference] User prefers concise answers
- importance: 0.7
- tags: [preference, style]
- source: inference

User responds better to short, direct answers. Avoid verbose explanations.

## [fact] pyproject.toml entry point fixed
- importance: 0.5
- tags: [bugfix, config]
- source: session

The CLI entry was changed from "app" to "main" in pyproject.toml.
```

YAML frontmatter 是可选的。解析器必须能优雅处理有 frontmatter 和无 frontmatter 的文件。

---

## 6. V1 需要的修改（接口钩子）

V1 需要最小修改来为 V2 做准备。所有修改向后兼容。

### 6.1 `core.py` — 添加 `Role.SYSTEM`

当前 `Role` 只有 `USER`/`ASSISTANT`。`truncate_messages` 第 66 行检查 `msg.role == "system"` 永远为 False。

需要新增 `Role.SYSTEM = "system"`

### 6.2 `core.py` — 扩展 `AgentState`

添加可选的 memory 引用，默认为 `None`：
- `project_root: str | None = None` — 用于 MEMORY.md 查找
- V2 中可扩展：`episodic`、`long_term` 等字段

### 6.3 `context.py` — 添加 `should_compress()` 存根

在 `SimpleTokenizer` 中添加存根方法，返回 `False`。
这是 `loop.py` 将调用的唯一钩子。

### 6.4 `loop.py` — 添加响应后压缩检查

在 `state.messages.append(Message(Role.ASSISTANT, response))` 之后添加：
- 调用 `SimpleTokenizer.should_compress(state.messages)`
- V1 中 body 为 `pass`，V2 填充为 `state.episodic.compress()`

### 6.5 `context.py` — 修复 `truncate_messages` bug

第 66 行检查 `if msg.role == "system"` 应改为 `if msg.role == Role.SYSTEM`

---

## 7. 模块依赖关系

```
core.py          ← 无依赖（叶子节点）
    ^
    |
context.py       ← 依赖 core.py
    ^
    |
memory/base.py   ← 依赖 core.py
    ^       ^
    |       |
    |   memory/retrieval.py  ← 依赖 base.py
    |
memory/working.py    ← 依赖 context.py, core.py
memory/short_term.py ← 依赖 core.py, context.py, base.py
memory/long_term.py  ← 依赖 base.py, retrieval.py
    ^
    |
loop.py          ← 依赖 core.py, context.py, (V2: memory modules)
    ^
    |
cli/main.py      ← 依赖 loop.py, llm/, (V2: memory modules)
```

依赖方向严格无环。`memory/base.py` 是共享契约。`memory/working.py` 依赖 `context.py`（不是反过来）。`loop.py` 和 `cli/main.py` 是集成点。

---

## 8. 实现阶段

### Phase 1: V1 接口预留（0.5天）

修改 V1 文件，添加 V2 钩子，向后兼容。

**修改文件**：
- `skywalker/core.py`：添加 Role.SYSTEM，扩展 AgentState
- `skywalker/agent/context.py`：修复 bug，添加 should_compress 钩子
- `skywalker/agent/loop.py`：添加压缩检查钩子

### Phase 2: Memory 基础模块（0.5天）

**新建文件**：
- `skywalker/memory/__init__.py`
- `skywalker/memory/base.py`：MemoryType、MemoryEntry、MemoryStore

### Phase 3: 短期记忆（1天）

**新建文件**：
- `skywalker/memory/short_term.py`：ConversationTurn、ConversationManager

### Phase 4: 检索引擎（0.5天）

**新建文件**：
- `skywalker/memory/retrieval.py`：BM25Retriever、VectorRetriever 占位

### Phase 5: 长期记忆（1天）

**新建文件**：
- `skywalker/memory/long_term.py`：MemoryMDStore

**修改文件**：
- `skywalker/cli/main.py`：启动/关闭流程集成 memory

### Phase 6: 集成测试（1天）

**修改文件**：
- `skywalker/cli/main.py`：完整启动/对话/关闭流程
- `skywalker/agent/loop.py`：使用富化系统提示，调用 episodic 追踪

**新建文件**：
- `tests/test_memory/test_working.py`
- `tests/test_memory/test_short_term.py`
- `tests/test_memory/test_long_term.py`
- `tests/test_memory/test_retrieval.py`

---

## 9. 关键文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `skywalker/core.py` | 修改 | 添加 Role.SYSTEM，扩展 AgentState |
| `skywalker/agent/context.py` | 修改 | 修复 bug，添加 should_compress 钩子 |
| `skywalker/agent/loop.py` | 修改 | 添加压缩检查钩子 |
| `skywalker/cli/main.py` | 修改 | 启动/关闭流程集成 memory |
| `skywalker/memory/__init__.py` | 新建 | 包初始化 |
| `skywalker/memory/base.py` | 新建 | 抽象接口 |
| `skywalker/memory/short_term.py` | 新建 | 短期记忆 |
| `skywalker/memory/long_term.py` | 新建 | 长期记忆 |
| `skywalker/memory/retrieval.py` | 新建 | BM25 检索 |

---

## 10. 验证方式

1. **单元测试**：每个 memory 模块独立测试
2. **集成测试**：完整 startup → conversation → shutdown 流程
3. **手动测试**：
   - 启动 skywalker，确认 MEMORY.md 被加载
   - 对话几轮，确认滑动窗口工作
   - 退出，确认 MEMORY.md 被更新
   - 再次启动，确认历史记忆被注入系统提示

---

## 11. 潜在挑战与缓解

| 挑战 | 缓解措施 |
|------|----------|
| `Message` 是 `frozen=True` | 保持 frozen；需要时使用外部索引 |
| `Role` 枚举值不匹配 | 添加 `Role.SYSTEM` 后修复比较逻辑 |
| 系统提示是单个字符串 | 保持字符串拼接；Anthropic SDK 支持长系统字符串 |
| MEMORY.md 合并冲突 | V2 单实例 CLI 暂不考虑；V3 使用文件锁 |
| 压缩质量 | V1 stub 简单拼接；V2 调用 LLM 生成摘要 |

---

## 12. 预估工时

Phase 1-6 共计 **4.5 天**
