import json
from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, TypeGuard


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

    def import_chat_messages(self, messages: List[Dict[str, str]]):
        def is_valid_role(
            role: str,
        ) -> TypeGuard[Literal["system", "user", "assistant"]]:
            return role in ["system", "user", "assistant"]

        for entry in messages:
            role = entry.get("role", "")

            if is_valid_role(role):
                msg = Message(role=role, content=entry.get("content", ""))
                self.append_msg(msg=msg)
