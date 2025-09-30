from typing import Optional
import datetime

from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey, Index, Integer, REAL, Text, text
from sqlmodel import Field, Relationship, SQLModel

class Experiment(SQLModel, table=True):
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    name: Optional[str] = Field(default=None, sa_column=Column('name', Text))

    run: list['Run'] = Relationship(back_populates='experiment')
    traces: list['Traces'] = Relationship(back_populates='experiment')


class Ifcmodels(SQLModel, table=True):
    project_name: str = Field(sa_column=Column('project_name', Text, nullable=False))
    model_name: str = Field(sa_column=Column('model_name', Text, nullable=False))
    model_path: str = Field(sa_column=Column('model_path', Text, nullable=False))
    model_description: str = Field(sa_column=Column('model_description', Text, nullable=False))
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))

    dataset: list['Dataset'] = Relationship(back_populates='ifc')


class Dataset(SQLModel, table=True):
    question: str = Field(sa_column=Column('question', Text, nullable=False))
    ground_truth: str = Field(sa_column=Column('ground_truth', Text, nullable=False))
    ifc_id: int = Field(sa_column=Column('ifc_id', ForeignKey('ifcmodels.id'), nullable=False))
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))

    ifc: Optional['Ifcmodels'] = Relationship(back_populates='dataset')
    traces: list['Traces'] = Relationship(back_populates='question')


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
    traces: list['Traces'] = Relationship(back_populates='run')


class Traces(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint('accuracy BETWEEN 0 AND 1'),
        Index('idx_traces_experiment_id', 'experiment_id'),
        Index('idx_traces_question_id', 'question_id'),
        Index('idx_traces_run_id', 'run_id')
    )

    experiment_id: str = Field(sa_column=Column('experiment_id', ForeignKey('experiment.id'), nullable=False))
    run_id: str = Field(sa_column=Column('run_id', ForeignKey('run.id'), nullable=False))
    question_id: int = Field(sa_column=Column('question_id', ForeignKey('dataset.id'), nullable=False))
    tools: str = Field(sa_column=Column('tools', Text, nullable=False))
    state: str = Field(sa_column=Column('state', Enum('OK', 'ERROR'), nullable=False))
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    answer: Optional[str] = Field(default=None, sa_column=Column('answer', Text))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))
    cost: Optional[float] = Field(default=None, sa_column=Column('cost', REAL))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    url: Optional[str] = Field(default=None, sa_column=Column('url', Text))
    llm: Optional[str] = Field(default=None, sa_column=Column('llm', Text))
    accuracy: Optional[float] = Field(default=None, sa_column=Column('accuracy', REAL))
    timestamp: Optional[datetime.datetime] = Field(default=None, sa_column=Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')))

    experiment: Optional['Experiment'] = Relationship(back_populates='traces')
    question: Optional['Dataset'] = Relationship(back_populates='traces')
    run: Optional['Run'] = Relationship(back_populates='traces')
