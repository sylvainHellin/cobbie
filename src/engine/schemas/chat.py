from pydantic import BaseModel
from typing import List, Literal, Optional, Dict, TypeGuard


class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class Chat(BaseModel):
    messages: List[Message] = []
    model: Optional[str] = None

    def append_msg(self, msg: Message):
        """Append a message to the chat conversation.

        Args:
            msg (Message): The message to append to the chat messages list.
        """
        self.messages.append(msg)

    def print(self):
        """Print all messages in the chat to the console.

        Each message is printed as a JSON-formatted string with proper indentation,
        separated by "---" dividers for readability.
        """
        dump = [msg.model_dump_json(indent=2) for msg in self.messages]

        print("\n---\n".join(dump))

    def to_string(self) -> str:
        """Convert all chat messages to a single formatted string.

        Returns:
            str: A comma-separated string of all messages formatted as JSON.
        """
        dump = [msg.model_dump_json(indent=2) for msg in self.messages]
        return ",\n".join(dump)

    def import_chat_messages(self, messages: List[Dict[str, str]]):
        """Import messages from a list of dictionaries and add them to the chat.

        Validates that each message has a valid role ("system", "user", or "assistant")
        before creating Message objects and appending them to the chat.

        Args:
            messages (List[Dict[str, str]]): List of message dictionaries containing
                'role' and 'content' keys. Invalid roles will be skipped.
        """

        def is_valid_role(
            role: str,
        ) -> TypeGuard[Literal["system", "user", "assistant"]]:
            return role in ["system", "user", "assistant"]

        for entry in messages:
            role = entry.get("role", "")

            if is_valid_role(role):
                msg = Message(role=role, content=entry.get("content", ""))
                self.append_msg(msg=msg)
