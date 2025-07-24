import json
from pydantic import BaseModel
from typing import List, Literal, Optional


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Chat(BaseModel):
    messages: List[Message] = []
    model: Optional[str] = None

    def append_msg(self, msg: Message):
        self.messages.append(msg)

    def print(self):
        dump = [msg.model_dump_json(indent=2) for msg in self.messages]

        print("\n---\n".join(dump))
