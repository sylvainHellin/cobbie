"""
Custom ChatAdapter that fixes the parsing issue for Optional[str] fields.

This adapter extends the default DSPy ChatAdapter to properly handle Optional[str] fields
containing descriptive text, preventing them from being incorrectly parsed as Python literals.
"""

import re
import textwrap
from typing import Any, Dict, NamedTuple, Optional, Type, Union, get_args, get_origin
import ast
import enum

from litellm import ContextWindowExceededError
from pydantic.fields import FieldInfo
import json_repair
from pydantic import TypeAdapter

from dspy.adapters.base import Adapter
from dspy.adapters.utils import (
    format_field_value,
    get_annotation_name,
    get_field_description_string,
    translate_field_type,
)
from dspy.clients.lm import LM
from dspy.signatures.signature import Signature
from dspy.utils.callback import BaseCallback

field_header_pattern = re.compile(r"\[\[ ## (\w+) ## \]\]")


class FieldInfoWithName(NamedTuple):
    name: str
    info: FieldInfo


def find_enum_member(enum, identifier):
    """
    Finds the enum member corresponding to the specified identifier, which may be the
    enum member's name or value.
    """
    # Check if the identifier is a valid enum member value *before* checking if it's a valid enum
    # member name, since the identifier will be a value for explicitly-valued enums
    for member in enum:
        if member.value == identifier:
            return member

    # If the identifier is not a valid enum member value, check if it's a valid enum member name
    if identifier in enum.__members__:
        return enum[identifier]

    raise ValueError(
        f"{identifier} is not a valid name or value for the enum {enum.__name__}"
    )


def custom_parse_value(value, annotation):
    """
    Custom parse_value function that properly handles Optional[str] fields.

    This fixes the issue where descriptive text in Optional[str] fields was being
    incorrectly parsed as Python literals instead of being treated as plain strings.
    """
    if annotation is str:
        return str(value)

    if isinstance(annotation, enum.EnumMeta):
        return find_enum_member(annotation, value)

    origin = get_origin(annotation)

    if origin is Union:
        # Handle Optional[str] or Union[str, None] - should return string as-is
        args = get_args(annotation)
        if len(args) == 2 and type(None) in args and str in args:
            return str(value) if value is not None else None

    if origin is Union and hasattr(annotation, "__args__"):
        from typing import Literal

        if hasattr(annotation, "__origin__") and annotation.__origin__ is Literal:
            allowed = get_args(annotation)
            if value in allowed:
                return value

            if isinstance(value, str):
                v = value.strip()
                if v.startswith(("Literal[", "str[")) and v.endswith("]"):
                    v = v[v.find("[") + 1 : -1]
                if len(v) > 1 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]

                if v in allowed:
                    return v

            raise ValueError(f"{value!r} is not one of {allowed!r}")

    if not isinstance(value, str):
        return TypeAdapter(annotation).validate_python(value)

    candidate = json_repair.loads(value)  # json_repair.loads returns "" on failure.
    if candidate == "" and value != "":
        # For string or Optional[str] fields, don't try to parse as literals - return as string
        if annotation is str or (origin is Union and str in get_args(annotation)):
            candidate = value
        else:
            try:
                candidate = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                candidate = value

    try:
        return TypeAdapter(annotation).validate_python(candidate)
    except Exception:  # Broad exception to catch pydantic ValidationError and others
        if (
            origin is Union
            and type(None) in get_args(annotation)
            and str in get_args(annotation)
        ):
            return str(candidate)
        raise


class CustomChatAdapter(Adapter):
    """
    Custom ChatAdapter that fixes the parsing issue for Optional[str] fields.

    This adapter uses a custom parse_value function that properly handles
    descriptive text in Optional[str] fields without trying to parse them
    as Python literals.
    """

    def __init__(self, callbacks: Optional[list[BaseCallback]] = None):
        super().__init__(callbacks)

    def __call__(
        self,
        lm: LM,
        lm_kwargs: dict[str, Any],
        signature: Type[Signature],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            return super().__call__(lm, lm_kwargs, signature, demos, inputs)
        except Exception as e:
            # fallback to JSONAdapter
            from dspy.adapters.json_adapter import JSONAdapter

            if isinstance(e, ContextWindowExceededError) or isinstance(
                self, JSONAdapter
            ):
                # On context window exceeded error or already using JSONAdapter, we don't want to retry with a different
                # adapter.
                raise e
            return JSONAdapter()(lm, lm_kwargs, signature, demos, inputs)

    def format_field_description(self, signature: Type[Signature]) -> str:
        return (
            f"Your input fields are:\n{get_field_description_string(signature.input_fields)}\n"
            f"Your output fields are:\n{get_field_description_string(signature.output_fields)}"
        )

    def format_field_structure(self, signature: Type[Signature]) -> str:
        """
        `ChatAdapter` requires input and output fields to be in their own sections, with section header using markers
        `[[ ## field_name ## ]]`. An arbitrary field `completed` ([[ ## completed ## ]]) is added to the end of the
        output fields section to indicate the end of the output fields.
        """
        parts = []
        parts.append(
            "All interactions will be structured in the following way, with the appropriate values filled in."
        )

        def format_signature_fields_for_instructions(fields: Dict[str, FieldInfo]):
            return self.format_field_with_value(
                fields_with_values={
                    FieldInfoWithName(
                        name=field_name, info=field_info
                    ): translate_field_type(field_name, field_info)
                    for field_name, field_info in fields.items()
                },
            )

        parts.append(format_signature_fields_for_instructions(signature.input_fields))
        parts.append(format_signature_fields_for_instructions(signature.output_fields))
        parts.append("[[ ## completed ## ]]\n")
        return "\n\n".join(parts).strip()

    def format_task_description(self, signature: Type[Signature]) -> str:
        instructions = textwrap.dedent(signature.instructions)
        objective = ("\n" + " " * 8).join([""] + instructions.splitlines())
        return f"In adhering to this structure, your objective is: {objective}"

    def format_user_message_content(
        self,
        signature: Type[Signature],
        inputs: dict[str, Any],
        prefix: str = "",
        suffix: str = "",
        main_request: bool = False,
    ) -> str:
        messages = [prefix]
        for k, v in signature.input_fields.items():
            if k in inputs:
                value = inputs.get(k)
                formatted_field_value = format_field_value(field_info=v, value=value)
                messages.append(f"[[ ## {k} ## ]]\n{formatted_field_value}")

        if main_request:
            output_requirements = self.user_message_output_requirements(signature)
            if output_requirements is not None:
                messages.append(output_requirements)

        messages.append(suffix)
        return "\n\n".join(messages).strip()

    def user_message_output_requirements(self, signature: Type[Signature]) -> str:
        """Returns a simplified format reminder for the language model."""

        def type_info(v):
            if v.annotation is not str:
                return f" (must be formatted as a valid Python {get_annotation_name(v.annotation)})"
            else:
                return ""

        message = (
            "Respond with the corresponding output fields, starting with the field "
        )
        message += ", then ".join(
            f"`[[ ## {f} ## ]]`{type_info(v)}"
            for f, v in signature.output_fields.items()
        )
        message += ", and then ending with the marker for `[[ ## completed ## ]]`."
        return message

    def format_assistant_message_content(
        self,
        signature: Type[Signature],
        outputs: dict[str, Any],
        missing_field_message=None,
    ) -> str:
        return self.format_field_with_value(
            {
                FieldInfoWithName(name=k, info=v): outputs.get(k, missing_field_message)
                for k, v in signature.output_fields.items()
            },
        )

    def parse(self, signature: Type[Signature], completion: str) -> dict[str, Any]:
        """
        Custom parse method that uses the fixed parse_value function.
        """
        sections = [(None, [])]

        for line in completion.splitlines():
            match = field_header_pattern.match(line.strip())
            if match:
                # If the header pattern is found, split the rest of the line as content
                header = match.group(1)
                remaining_content = line[match.end() :].strip()
                sections.append(
                    (header, [remaining_content] if remaining_content else [])
                )
            else:
                sections[-1][1].append(line)

        sections = [(k, "\n".join(v).strip()) for k, v in sections]

        fields = {}
        for k, v in sections:
            if (k not in fields) and (k in signature.output_fields):
                try:
                    # Use our custom parse_value function instead of the default one
                    fields[k] = custom_parse_value(
                        v, signature.output_fields[k].annotation
                    )
                except Exception as e:
                    raise ValueError(
                        f"Error parsing field {k}: {e}.\n\n\t\tOn attempting to parse the value\n```\n{v}\n```"
                    )
        if fields.keys() != signature.output_fields.keys():
            raise ValueError(
                f"Expected {signature.output_fields.keys()} but got {fields.keys()}"
            )

        return fields

    def format_field_with_value(
        self, fields_with_values: Dict[FieldInfoWithName, Any]
    ) -> str:
        """
        Formats the values of the specified fields according to the field's DSPy type (input or output),
        annotation (e.g. str, int, etc.), and the type of the value itself. Joins the formatted values
        into a single string, which is is a multiline string if there are multiple fields.
        """
        output = []
        for field, field_value in fields_with_values.items():
            formatted_field_value = format_field_value(
                field_info=field.info, value=field_value
            )
            output.append(f"[[ ## {field.name} ## ]]\n{formatted_field_value}")

        return "\n\n".join(output).strip()

    def format_finetune_data(
        self,
        signature: Type[Signature],
        demos: list[dict[str, Any]],
        inputs: dict[str, Any],
        outputs: dict[str, Any],
    ) -> dict[str, list[Any]]:
        """
        Format the call data into finetuning data according to the OpenAI API specifications.
        """
        system_user_messages = (
            self.format(  # returns a list of dicts with the keys "role" and "content"
                signature=signature, demos=demos, inputs=inputs
            )
        )
        assistant_message_content = (
            self.format_assistant_message_content(  # returns a string, without the role
                signature=signature, outputs=outputs
            )
        )
        assistant_message = {"role": "assistant", "content": assistant_message_content}
        messages = system_user_messages + [assistant_message]
        return {"messages": messages}
