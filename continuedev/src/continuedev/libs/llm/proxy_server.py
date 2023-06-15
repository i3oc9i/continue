from functools import cached_property
import json
from typing import Any, Dict, Generator, List, Literal, Union
import requests
import tiktoken

from ...core.main import ChatMessage
from ..llm import LLM

MAX_TOKENS_FOR_MODEL = {
    "gpt-3.5-turbo": 4097,
    "gpt-4": 4097,
}
DEFAULT_MAX_TOKENS = 2048
CHAT_MODELS = {
    "gpt-3.5-turbo", "gpt-4"
}

SERVER_URL = "http://127.0.0.1:8002"


class ProxyServer(LLM):
    unique_id: str
    default_model: Literal["gpt-3.5-turbo", "gpt-4"]

    def __init__(self, unique_id: str, default_model: Literal["gpt-3.5-turbo", "gpt-4"], system_message: str = None):
        self.unique_id = unique_id
        self.default_model = default_model
        self.system_message = system_message

    @cached_property
    def __encoding_for_model(self):
        aliases = {
            "gpt-3.5-turbo": "gpt3"
        }
        return tiktoken.encoding_for_model(self.default_model)

    def count_tokens(self, text: str):
        return len(self.__encoding_for_model.encode(text, disallowed_special=()))

    def stream_chat(self, prompt, with_history: List[ChatMessage] = [], **kwargs) -> Generator[Union[Any, List, Dict], None, None]:
        resp = requests.post(f"{SERVER_URL}/stream_complete", json={
            "chat_history": self.compile_chat_messages(with_history, prompt),
            "model": self.default_model,
            "unique_id": self.unique_id,
        }, stream=True)
        for line in resp.iter_lines():
            if line:
                yield line.decode("utf-8")

    def __prune_chat_history(self, chat_history: List[ChatMessage], max_tokens: int, tokens_for_completion: int):
        tokens = tokens_for_completion
        for i in range(len(chat_history) - 1, -1, -1):
            message = chat_history[i]
            tokens += self.count_tokens(message.content)
            if tokens > max_tokens:
                return chat_history[i + 1:]
        return chat_history

    def compile_chat_messages(self, msgs: List[ChatMessage], prompt: str) -> List[Dict]:
        msgs = self.__prune_chat_history(msgs, MAX_TOKENS_FOR_MODEL[self.default_model], self.count_tokens(
            prompt) + 1000 + self.count_tokens(self.system_message or ""))
        history = []
        if self.system_message:
            history.append({
                "role": "system",
                "content": self.system_message
            })
        history += [msg.dict() for msg in msgs]
        history.append({
            "role": "user",
            "content": prompt
        })

        return history

    def complete(self, prompt: str, with_history: List[ChatMessage] = [], **kwargs) -> str:

        resp = requests.post(f"{SERVER_URL}/complete", json={
            "chat_history": self.compile_chat_messages(with_history, prompt),
            "model": self.default_model,
            "unique_id": self.unique_id,
        })
        return json.loads(resp.text)