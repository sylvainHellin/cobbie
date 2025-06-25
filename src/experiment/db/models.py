"""Database models and utility functions."""

import sqlite3
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


def datetime_encoder(dt: datetime) -> str:
    """
    Encode a python datetime object to an ISO 8601 formated string.
    """
    return dt.isoformat("-")


def datetime_decoder(s: bytes) -> datetime:
    """
    Decode an ISO 8601 formated bytestring into a python datetime object.
    """
    return datetime.fromisoformat(s.decode())


# Register the encoder and decoder into the db
sqlite3.register_adapter(datetime, datetime_encoder)
sqlite3.register_converter("timestamp", datetime_decoder)


class DatasetRow(BaseModel):
    id: Optional[int] = None
    question: Optional[str] = None
    answer: Optional[str] = None
    ifc_id: Optional[int] = None


class RunsRow(BaseModel):
    id: Optional[int] = None
    question_id: Optional[int] = None
    llm: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    duration: Optional[float] = None
    timestamp: Optional[datetime] = None


class IfcModelRow(BaseModel):
    id: Optional[int] = None
    project_name: Optional[str] = None
    model_name: Optional[str] = None
    model_path: Optional[str] = None
    model_description: Optional[str] = None


class LogRow(BaseModel):
    id: Optional[int] = None
    run_id: Optional[int] = None
    agent_name: Optional[str] = None
    step_number: Optional[int] = None
    timestamp: Optional[datetime] = None
    model_output: Optional[str] = None
    action_input_code: Optional[str] = None
    action_output: Optional[str] = None
    observations: Optional[str] = None
    error: Optional[str] = None
    duration: Optional[float] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None


class DateTimeEncoder:
    """Custom JSON encoder for datetime objects."""

    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)  # type: ignore
