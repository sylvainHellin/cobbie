from typing import Optional
import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey, Integer, REAL, Text, text
from sqlmodel import Field, Relationship, SQLModel

class Experiment(SQLModel, table=True):
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    name: Optional[str] = Field(default=None, sa_column=Column('name', Text))

    run: list['Run'] = Relationship(back_populates='experiment')


class Ifcmodels(SQLModel, table=True):
    project_name: str = Field(sa_column=Column('project_name', Text, nullable=False))
    model_name: str = Field(sa_column=Column('model_name', Text, nullable=False))
    model_path: str = Field(sa_column=Column('model_path', Text, nullable=False))
    model_description: str = Field(sa_column=Column('model_description', Text, nullable=False))
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))

    dataset: list['Dataset'] = Relationship(back_populates='ifc')


class Dataset(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint('category BETWEEN 1 AND 4'),
    )

    question: str = Field(sa_column=Column('question', Text, nullable=False))
    ground_truth: str = Field(sa_column=Column('ground_truth', Text, nullable=False))
    ifc_id: int = Field(sa_column=Column('ifc_id', ForeignKey('ifcmodels.id'), nullable=False))
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))
    category: Optional[int] = Field(default=None, sa_column=Column('category', Integer))

    ifc: Optional['Ifcmodels'] = Relationship(back_populates='dataset')
    trace: list['Trace'] = Relationship(back_populates='question')


class Run(SQLModel, table=True):
    experiment_id: str = Field(sa_column=Column('experiment_id', ForeignKey('experiment.id'), nullable=False))
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    name: Optional[str] = Field(default=None, sa_column=Column('name', Text))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))
    cost: Optional[float] = Field(default=None, sa_column=Column('cost', REAL))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    url: Optional[str] = Field(default=None, sa_column=Column('url', Text))
    llm: Optional[str] = Field(default=None, sa_column=Column('llm', Text))
    accuracy: Optional[float] = Field(default=None, sa_column=Column('accuracy', REAL))
    timestamp: Optional[datetime.datetime] = Field(default=None, sa_column=Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')))
    nb_traces: Optional[int] = Field(default=None, sa_column=Column('nb_traces', Integer))

    experiment: Optional['Experiment'] = Relationship(back_populates='run')
    trace: list['Trace'] = Relationship(back_populates='run')


class Trace(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint('accuracy BETWEEN 0 AND 1'),
    )

    run_id: str = Field(sa_column=Column('run_id', ForeignKey('run.id'), nullable=False))
    question_id: int = Field(sa_column=Column('question_id', ForeignKey('dataset.id'), nullable=False))
    tools: str = Field(sa_column=Column('tools', Text, nullable=False))
    status: str = Field(sa_column=Column('status', Enum('OK', 'ERROR'), nullable=False))
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    answer: Optional[str] = Field(default=None, sa_column=Column('answer', Text))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))
    cost: Optional[float] = Field(default=None, sa_column=Column('cost', REAL))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    url: Optional[str] = Field(default=None, sa_column=Column('url', Text))
    llm: Optional[str] = Field(default=None, sa_column=Column('llm', Text))
    nb_spans: Optional[int] = Field(default=None, sa_column=Column('nb_spans', Integer))
    accuracy: Optional[float] = Field(default=None, sa_column=Column('accuracy', REAL))
    timestamp: Optional[datetime.datetime] = Field(default=None, sa_column=Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')))

    question: Optional['Dataset'] = Relationship(back_populates='trace')
    run: Optional['Run'] = Relationship(back_populates='trace')
    span: list['Span'] = Relationship(back_populates='trace')


class Span(SQLModel, table=True):
    trace_id: str = Field(sa_column=Column('trace_id', ForeignKey('trace.id'), nullable=False))
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    start_time: Optional[float] = Field(default=None, sa_column=Column('start_time', REAL))
    end_time: Optional[float] = Field(default=None, sa_column=Column('end_time', REAL))
    type: Optional[str] = Field(default=None, sa_column=Column('type', Text))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))
    cost: Optional[float] = Field(default=None, sa_column=Column('cost', REAL))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    llm: Optional[str] = Field(default=None, sa_column=Column('llm', Text))
    input_data: Optional[str] = Field(default=None, sa_column=Column('input_data', Text))
    output_data: Optional[str] = Field(default=None, sa_column=Column('output_data', Text))

    trace: Optional['Trace'] = Relationship(back_populates='span')
