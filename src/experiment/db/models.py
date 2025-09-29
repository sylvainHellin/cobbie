from typing import Optional
import datetime

from sqlalchemy import Column, ForeignKey, Index, Integer, REAL, TIMESTAMP, Text
from sqlmodel import Field, Relationship, SQLModel

class Experiment(SQLModel, table=True):
    __table_args__ = (
        Index('ix_experiment_name', 'mlflow_name'),
    )

    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))
    mlflow_name: Optional[str] = Field(default=None, sa_column=Column('mlflow_name', Text))
    mlflow_id: Optional[str] = Field(default=None, sa_column=Column('mlflow_id', Text))


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
    runs: list['Runs'] = Relationship(back_populates='question')


class Runs(SQLModel, table=True):
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))
    question_id: Optional[int] = Field(default=None, sa_column=Column('question_id', ForeignKey('dataset.id')))
    llm: Optional[str] = Field(default=None, sa_column=Column('llm', Text))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    timestamp: Optional[datetime.datetime] = Field(default=None, sa_column=Column('timestamp', TIMESTAMP))

    question: Optional['Dataset'] = Relationship(back_populates='runs')
    logs: list['Logs'] = Relationship(back_populates='run')


class Logs(SQLModel, table=True):
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))
    run_id: Optional[int] = Field(default=None, sa_column=Column('run_id', ForeignKey('runs.id')))
    agent_name: Optional[str] = Field(default=None, sa_column=Column('agent_name', Text))
    step_number: Optional[int] = Field(default=None, sa_column=Column('step_number', Integer))
    timestamp: Optional[datetime.datetime] = Field(default=None, sa_column=Column('timestamp', TIMESTAMP))
    model_output: Optional[str] = Field(default=None, sa_column=Column('model_output', Text))
    action_input_code: Optional[str] = Field(default=None, sa_column=Column('action_input_code', Text))
    action_output: Optional[str] = Field(default=None, sa_column=Column('action_output', Text))
    observations: Optional[str] = Field(default=None, sa_column=Column('observations', Text))
    error: Optional[str] = Field(default=None, sa_column=Column('error', Text))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))

    run: Optional['Runs'] = Relationship(back_populates='logs')
