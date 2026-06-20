from skywalker.core import Message, Role



def print_msg(text: str, style: str = ""):
    """打印消息，支持简单的颜色标记"""
    colors = {
        "bold blue": "\033[1;34m",
        "bold cyan": "\033[1;36m",
        "bold orange1": "\033[1;33m",
        "bold red": "\033[1;31m",
        "dim": "\033[2m",
    }
    reset = "\033[0m"

    if style and style in colors:
        print(f"{colors[style]}{text}{reset}", end="")
    else:
        print(text, end="")



def render_message(message: Message):
    """渲染单条消息，根据 role 添加前缀和颜色"""
    if message.role == Role.USER:
        print_msg("You: ", "bold blue")
        print(message.text_content)
    elif message.role == Role.ASSISTANT:
        print_msg("Agent: ", "bold cyan")
        print(message.text_content)
    elif message.role == Role.SYSTEM:
        print_msg("System: ", "dim")
        print(message.text_content)

def render_messages(messages: list[Message]):
    """渲染多条消息历史"""
    for msg in messages:
        render_message(msg)
    print()  # 最后空一行