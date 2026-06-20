2026年 06月 20日 星期六 17:54:45 CST
2026年 06月 20日 星期六 17:54:45 CST
2026年 06月 20日 星期六 17:54:45 CST
mimo不如deepseek
mimo不如deepseek
mimo不如deepseek

## 二、设计亮点

### 1. 事件驱动架构
```python
def render_event(self, event: StreamEvent) -> None:
    if isinstance(event, AssistantTextDelta):
        # 流式输出 Assistant 文本
    elif isinstance(event, AssistantTurnComplete):
        # Assistant 回复完成，转 Markdown 渲染
    elif isinstance(event, ToolExecutionStarted):
        # 工具开始执行，显示工具名 + 摘要
    elif isinstance(event, ToolExecutionCompleted):
        # 工具执行完成，渲染输出
    elif isinstance(event, CompactProgressEvent):
        # 压缩进度提示
```
- 每种事件类型都有**独立的渲染逻辑**
- 扩展性强：新增事件只需加一个 `elif` 分支

---

### 2. 流式输出支持
```python
if isinstance(event, AssistantTextDelta):
    self._assistant_buffer += event.text
    # 实时打印每个 delta，不等待完整回复
    self.console.print(event.text, end="", markup=False, highlight=False)
```
- 实现了**打字机效果**，用户体验流畅
- 同时缓存完整文本（`_assistant_buffer`），用于最终 Markdown 渲染

---

### 3. 智能 Markdown 检测
```python
def _has_markdown(text: str) -> bool:
    indicators = ["```", "## ", "### ", "- ", "* ", "1. ", "**", "__", "> "]
    return any(ind in text for ind in indicators)

# 在 AssistantTurnComplete 中
if _has_markdown(self._assistant_buffer):
    self.console.print(Markdown(self._assistant_buffer.strip()))
```
- **区分纯文本和 Markdown 内容**
- 包含 Markdown 语法（代码块、标题、列表等）时，用 `rich.Markdown` 渲染

---

### 4. 工具输出的差异化渲染
```python
def _render_tool_output(self, tool_name: str, tool_input: dict | None, output: str):
    lower = tool_name.lower()
    if lower == "bash":
        # Bash 命令：用 Panel 包装，显示命令
    elif lower in ("read", "fileread"):
        # 文件读取：语法高亮（根据扩展名选择 lexer）
        self.console.print(Syntax(output, lexer, theme="monokai", ...))
    elif lower in ("edit", "fileedit"):
        # 文件编辑：绿色面板
```
- 不同工具的输出**用不同视觉风格呈现**
- 文件内容支持**语法高亮**（Python、JS、Rust 等 20+ 种语言）
- 输出过长时自动截断（避免终端刷屏）

---

### 5. Spinner 反馈
```python
def show_thinking(self):
    self._spinner_status = self.console.status("[cyan]Thinking...[/cyan]", spinner="dots")
    self._spinner_status.start()
```
- 在等待模型响应时显示**动态旋转动画**
- 收到第一个 token 或工具执行时自动停止

---

### 6. 多风格支持
```python
def set_style(self, style_name: str) -> None:
    self._style_name = style_name  # "default" | "minimal"
```
- `default`：全功能渲染（颜色、面板、语法高亮）
- `minimal`：纯文本输出（适合日志或非交互环境）

---

### 7. 状态管理
- `_assistant_line_open`：追踪是否正在输出 Assistant 行，避免换行混乱
- `_assistant_buffer`：缓存完整回复，用于最终渲染
- `_last_tool_input`：保存最近一次工具输入，用于输出渲染时补充信息
- `_spinner_status`：管理 spinner 生命周期

---

## 三、渲染示例（终端输出）

```
▶ Skywalker Agent - 输入 'exit' 退出

You: 列出当前目录的文件

⏳ Thinking...

⎆ 我来列出当前目录的文件。

  ⏵ bash ls -la
    exit_code: 0
    stdout:
    drwxr-xr-x  ... skywalker/
    -rw-r--r--  ... main.py

You: 帮我修改 config.yaml

  ⏵ edit file_path=config.yaml
  ┌─ Edit: config.yaml ──┐
  │ ... 修改内容 ...      │
  └──────────────────────┘

model: claude-3-sonnet │ tokens: 1.2k↓ 0.8k↑ │ mode: default
```

---

## 四、总结

| 特性 | 实现方式 |
|------|----------|
| 流式输出 | `AssistantTextDelta` 逐字打印 |
| Markdown | `rich.Markdown` + `_has_markdown()` 检测 |
| 语法高亮 | `rich.Syntax` + 扩展名映射 |
| 工具反馈 | `Panel` 包装 + 差异化渲染 |
| 等待状态 | `Console.status()` + spinner |
| 多风格 | `_style_name` 分支控制 |
| 事件驱动 | `isinstance()` 分发 + 缓存状态 |

这个渲染器适合直接**集成到 Skywalker Agent 的 CLI 界面**，只需将 `StreamEvent` 从 `run_loop` 传递到 `OutputRenderer.render_event()` 即可。
deepseek不如mimo