from skywalker.agent.context import SimpleTokenizer


# 测试代码
class TestMessage:
    def __init__(self, content, role="user"):
        self.content = content
        self.role = role
message = []

message.append("""(skywalker) j0hnny@the-only-skywalker:/Alpha/College_new/skywalker_agent$      
  skywalker                                                                      
  Traceback (most recent call last):                                             
    File "/home/j0hnny/miniconda3/envs/skywalker/bin/skywalker", line 3, in      
  <module>                                                                       
      from skywalker.cli.main import app                                         
  ImportError: cannot import name 'app' from 'skywalker.cli.main'                
  (/Alpha/College_new/skywalker_agent/skywalker/cli/main.py)  没有app的定义      

  Read 1 file, listed 1 directory (ctrl+o to expand)

● 问题是 pyproject.toml 配置了 app，但 main.py 只有 main() 函数。修复：

  Read 1 file (ctrl+o to expand)

● Update(pyproject.toml)
  ⎿  Added 1 line, removed 1 line
      29  ]
      30  
      31  [project.scripts]
      32 -skywalker = "skywalker.cli.main:app"                            
      32 +skywalker = "skywalker.cli.main:main"                           
      33  
      34  [tool.hatch.build.targets.wheel]
      35  packages = ["skywalker"]

● Bash(pip install -e . -q && echo "重新安装完成")
  ⎿  重新安装完成

● 已修复。pyproject.toml 中的入口从 app 改成了 main。

  重新运行：

  skywalker

✻ 翻炒了 40秒

※ recap: V1 demo 已完成，刚修复了 CLI 入口配置。现在运行 `skywalker`
  测试整个对话流程。 (disable recaps in /config)""")

message.append(""" 不理解,为什么要创建这么多没有使用的"__init__.py"                               

● 因为 Python 需要 __init__.py 来识别目录是包。

  你的代码有跨模块导入：
  - cli/main.py 导入 skywalker.agent.loop
  - agent/loop.py 导入 skywalker.core
  - llm/deepseek.py 导入 skywalker.llm.base

  没有 __init__.py，这些导入会失败。

  测试一下：删除任意一个 __init__.py，运行 skywalker 会报 ModuleNotFoundError。

  如果觉得多余，可以只保留
  skywalker/__init__.py，其他目录改成平级结构（不推荐，V2 会扩展）。

❯ 如果要给cli增加按esc退出.是不是要增加函数def read_line_with_esc_exit() ?       

● 对，封装成独立函数是对的。

  核心逻辑：逐字符读取，检测 ESC (ASCII 27) 就退出，回车就返回当前输入。

  需要一个库 readchar 来做逐字符读取。你想用这个方案吗？还是有其他想法？

✻ 忙活了 33秒

※ recap: V1 demo 已完成，CLI 能跑通对话。现在要增加 ESC 退出功能。下一步：实现
  `read_line_with_esc_exit()` 函数。

❯ (skywalker) j0hnny@the-only-skywalker:/Alpha/College_new/skywalker_agent$      
  skywalker                                                                      
  Traceback (most recent call last):                                             
    File "/home/j0hnny/miniconda3/envs/skywalker/bin/skywalker", line 3, in      
  <module>                                                                       
      from skywalker.cli.main import main                                        
    File "/Alpha/College_new/skywalker_agent/skywalker/cli/main.py", line 1, in  
  <module>                                                                       
      from rich.ansi import line                                                 
  ImportError: cannot import name 'line' from 'rich.ansi' (/home/j0hnny/minicond 
  a3/envs/skywalker/lib/python3.11/site-packages/rich/ansi.py) 为什么不能?       

  Read 1 file (ctrl+o to expand)

● rich.ansi 没有 line 属性。这是个错误导入，删掉它。

  你的 read_line_with_esc 函数实现得很好，不需要那个导入。删掉第 1 行：

  from rich.ansi import line  # 删掉这行

  其他代码没问题，readchar 的用法正确。
""")
message.append("""
@skywalker/agent/context.py 应该是拿来截断token的,在每次skywalker回答之后,都进 
  行一次检查.实现history的滚动窗口.我需要你给出函数的具体思路,我应该怎么做?我对  
  这一方面比较迷茫,单论思路能说的顺畅                                            
  ⎿  Read skywalker/agent/context.py (1 lines)

● 好的，给你思路。

  核心问题：对话历史会超过 LLM 的 token 限制，需要动态截断。

  设计思路：

  1. Token 计算：需要一个函数估算 messages 的总 token 数
    - 方案 A：用 tiktoken 库精确计算（依赖 OpenAI 模型）
    - 方案 B：简单估算（中文约 1.5 字/token，英文约 4 字符/token）
  2. 截断策略：滑动窗口
    - 保留 system prompt（如果有）
    - 保留最近 N 条消息
    - 或者保留最近 N 个 token
    - 删除最老的消息
  3. 触发时机：在 run_loop 完成后调用截断函数
  4. 实现位置：context.py 专门处理这个逻辑

  函数设计：
  - count_tokens(messages: list[Message]) -> int：计算总 token
  - truncate_messages(messages: list[Message], max_tokens: int) ->
  list[Message]：截断到指定 token 数
  - 或者更简单：trim_history(messages: list[Message], max_turns: int) ->
  list[Message]：保留最近 N 轮对话

  你想用哪种方案？精确计算还是简单估算？按 token 截断还是按轮次截断？

❯ 精确计算                                                                       

● 好，用 tiktoken 精确计算。

  思路：

  1. 初始化：加载对应模型的 tokenizer（如 cl100k_base）
  2. 单条消息 token：编码 content + 加上 role 等元数据开销（约 4 token）
  3. 总 token：遍历所有消息累加
  4. 截断：从最老的消息开始删除，直到总 token <= 阈值

  函数结构：

  import tiktoken
  from skywalker.core import Message

  # 初始化 tokenizer（选一个模型，如 gpt-4 的编码）
  ENCODER = tiktoken.get_encoding("cl100k_base")

  def count_message_tokens(message: Message) -> int:
      #计算单条消息的 token 数
      # 你的实现：编码 content + 元数据开销

  def count_total_tokens(messages: list[Message]) -> int:
      #计算所有消息的总 token 数
      # 你的实现：遍历累加

  def truncate_messages(messages: list[Message], max_tokens: int) ->
  list[Message]:
      #截断消息列表到指定 token 数
      # 你的实现：从最老的消息开始删除

  集成点：在 loop.py 的 run_loop 结尾调用 truncate_messages，保持 history 在
  token 限制内。

  需要我给出具体实现吗？还是你先填？

❯ 你先把函数代码名字等写入文件,剩下的我先来试试                                  

  Read 1 file (ctrl+o to expand)

● Update(pyproject.toml)
  ⎿  Added 1 line
      18      "rich>=13.0.0",
      19      "pyyaml>=6.0",
      20      "readchar>=4.2.2",
      21 +    "tiktoken>=0.7.0",                                          
      22      "python-dotenv>=1.0.0",
      23  ]
      24  

● Write(skywalker/agent/context.py)
  ⎿  Wrote 32 lines to skywalker/agent/context.py
      1 import tiktoken
      2 from skywalker.core import Message
      3
      4 # 初始化 tokenizer（使用 cl100k_base 编码，适用于 GPT-4/3.5）
      5 ENCODER = tiktoken.get_encoding("cl100k_base")
      6
      7 # 每条消息的元数据开销（role + 分隔符等）
      8 MESSAGE_OVERHEAD_TOKENS = 4
      9
     … +23 lines (ctrl+o to expand)

● Bash(pip install -e . -q && echo "tiktoken 已安装")
  ⎿  tiktoken 已安装

● 完成。context.py 已写入函数结构，tiktoken 依赖已添加并安装。

  三个函数：
  - count_message_tokens：计算单条消息 token
  - count_total_tokens：计算总 token
  - truncate_messages：截断到指定 token 数

  实现后，在 loop.py 的 run_loop 结尾调用 truncate_messages，保持 history 在
  token 限制内。

  填完告诉我，我检查实现是否正确。

✻ 嚼了 37秒

※ recap: 目标：完成 Skywalker V1 demo。当前任务：实现 context.py 的 token
  截断函数。下一步：填充那三个函数，然后集成到 loop.py。 (disable recaps in
  /config)

❯ 但是这样精确计算的话,不同模型之间的方法完全不一样,而用户使用的并不是统一的mode 
  l,所以还是应该使用粗略计算方案                                                 

● 对，你说得对。不同模型 tokenizer 不一样，粗略计算更实用。

  改用简单估算：
  - 中文：约 1.5 字/token
  - 英文：约 4 字符/token
  - 统一公式：len(content) / 1.5（保守估算）

● Update(pyproject.toml)
  ⎿  Removed 1 line
      18      "rich>=13.0.0",
      19      "pyyaml>=6.0",
      20      "readchar>=4.2.2",
      21 -    "tiktoken>=0.7.0",                                          
      21      "python-dotenv>=1.0.0",
      22  ]
      23  

● Write(skywalker/agent/context.py)
  ⎿  Added 7 lines, removed 11 lines
       1 -import tiktoken                                                 
       1  from skywalker.core import Message
       2  
       4 -# 初始化 tokenizer（使用 cl100k_base 编码，适用于 GPT-4/3.5）   
       5 -ENCODER = tiktoken.get_encoding("cl100k_base")                  
       3 +# 粗略估算系数（保守估计，适用于中英文混合）                    
       4 +CHARS_PER_TOKEN = 1.5  # 中文约 1.5 字/token，英文约 4 字符/toke
         +n，取保守值                                                     
       5  
       7 -# 每条消息的元数据开销（role + 分隔符等）                       
       8 -MESSAGE_OVERHEAD_TOKENS = 4                                     
       6  
      10 -                                                                
      11 -def count_message_tokens(message: Message) -> int:              
      12 -    #计算单条消息的 token 数                               
      13 -    # 你的实现：编码 content + 元数据开销                       
       7 +def estimate_message_tokens(message: Message) -> int:           
       8 +    #估算单条消息的 token 数                              
       9 +    # 你的实现：len(content) / CHARS_PER_TOKEN + 元数据开销     
      10      pass
      11  
      12  
      17 -def count_total_tokens(messages: list[Message]) -> int:         
      18 -    #计算所有消息的总 token 数                            
      13 +def estimate_total_tokens(messages: list[Message]) -> int:      
      14 +    #估算所有消息的总 token 数                             
      15      # 你的实现：遍历累加
      16      pass
      17  

● 完成。改用粗略估算，删除了 tiktoken 依赖。

  三个函数：
  - estimate_message_tokens：估算单条消息 token（len(content) / 1.5 +
  元数据开销）
  - estimate_total_tokens：估算总 token
  - truncate_messages：截断到指定 token 数

  填完告诉我，我检查实现。""")
# 创建测试消息
msgs = [
    TestMessage(content=message[0], role="system"),
    TestMessage(content=message[1], role="user"),
    TestMessage(content=message[2], role="user"),
]

# 打印原始总 token 数
original_tokens = SimpleTokenizer.estimate_total_tokens(msgs)
print(f"原始总 token 数: {original_tokens}")

# 截断
max_tokens = 2048
truncated = SimpleTokenizer.truncate_messages(msgs, max_tokens=max_tokens)

# 打印每条消息的 token 数
print("=== 每条消息的 token 数 ===")
for i, msg in enumerate(msgs):
    msg_tokens = SimpleTokenizer.estimate_message_tokens(msg)
    print(f"消息{i+1} ({msg.role}): {msg_tokens} tokens (内容)")

# 打印截断后的总 token 数
truncated_tokens = SimpleTokenizer.estimate_total_tokens(truncated)
print(f"截断后总 token 数: {truncated_tokens}")
print(f"限制 max_tokens: {max_tokens}")

# 打印详细信息
print(f"\n原消息数: {len(msgs)}")
print(f"截断后消息数: {len(truncated)}")
if truncated:
    print(f"保留了从第 {msgs.index(truncated[0]) + 1} 条到最后")
print(f"保留的消息内容:")
for msg in truncated:
    print(f"  {msg.role}: {msg.content[:20]}...")