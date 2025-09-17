from typing import Any, Dict, List, Literal, Optional, TypeGuard

import dspy
from pydantic import BaseModel


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

    def import_chat_messages(
        self,
        lm: dspy.LM,
        last: bool = True,
    ):
        """Import chat messages from a DSPy LM object.

        Extracts conversation history from the DSPy LM and imports it into the chat.
        Can import either just the last conversation turn or the complete history.

        Args:
            lm (dspy.LM): The DSPy language model object containing conversation history
            last (bool): If True, only import the last conversation turn (system + user + assistant).
                        If False, import the complete conversation history. Defaults to True.
        """

        def is_valid_role(
            role: str,
        ) -> TypeGuard[Literal["system", "user", "assistant"]]:
            return role in ["system", "user", "assistant"]

        def process_history_entry(history_entry: Dict[str, Any]):
            """Process a single history entry and add messages to chat."""
            # Import the input messages (system + user)
            messages = history_entry.get("messages", [])
            for entry in messages:
                role = entry.get("role", "")
                if is_valid_role(role):
                    msg = Message(role=role, content=entry.get("content", ""))
                    self.append_msg(msg=msg)

            # Add assistant response if available
            if "response" in history_entry and history_entry["response"]:
                response = history_entry["response"]

                # Extract content from ModelResponse object
                choices = getattr(response, "choices", [])
                content = (
                    getattr(choices[0], "message", {}).get("content", str(response))
                    if choices
                    else str(response)
                )

                assistant_msg = Message(role="assistant", content=content)
                self.append_msg(msg=assistant_msg)

        # Check if LM has history
        if not hasattr(lm, "history") or not lm.history:
            return

        if last:
            # Import only the last conversation turn
            if lm.history:
                process_history_entry(lm.history[-1])
        else:
            # Import the complete conversation history
            for history_entry in lm.history:
                process_history_entry(history_entry)
