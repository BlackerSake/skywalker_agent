import os
from dotenv import load_dotenv
from anthropic import Anthropic
from skywalker.core import Message, Role
from skywalker.llm.base import LLMClient

load_dotenv(override=True)

MODEL = os.environ["MODEL_ID"]
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL")
API_KEY = os.environ["ANTHROPIC_API_KEY"]


class AnthropicClient(LLMClient):
    def __init__(self):
        self.client = Anthropic(base_url=BASE_URL, api_key=API_KEY)
        self.model = MODEL

    def chat(self, messages: list[Message], system: str | None = None) -> str:
        formatted = [
            {"role": m.role.value, "content": m.content}
            for m in messages
        ]

        kwargs = {
            "model": self.model,
            "messages": formatted,
            "max_tokens": 4096,
        }
        if system:
            kwargs["system"] = system

        response = self.client.messages.create(**kwargs)
        return response.content[0].text