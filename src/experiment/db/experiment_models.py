from typing import Optional
import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, REAL, Text, text
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
    question: str = Field(sa_column=Column('question', Text, nullable=False))
    ground_truth: str = Field(sa_column=Column('ground_truth', Text, nullable=False))
    ifc_id: int = Field(sa_column=Column('ifc_id', ForeignKey('ifcmodels.id'), nullable=False))
    id: Optional[int] = Field(default=None, sa_column=Column('id', Integer, primary_key=True))

    ifc: Optional['Ifcmodels'] = Relationship(back_populates='dataset')


class Run(SQLModel, table=True):
    experiment_id: str = Field(sa_column=Column('experiment_id', ForeignKey('experiment.id'), nullable=False))
    id: Optional[str] = Field(default=None, sa_column=Column('id', Text, primary_key=True))
    name: Optional[str] = Field(default=None, sa_column=Column('name', Text))
    input_tokens: Optional[int] = Field(default=None, sa_column=Column('input_tokens', Integer))
    output_tokens: Optional[int] = Field(default=None, sa_column=Column('output_tokens', Integer))
    cost: Optional[float] = Field(default=None, sa_column=Column('cost', REAL))
    duration: Optional[float] = Field(default=None, sa_column=Column('duration', REAL))
    url: Optional[str] = Field(default=None, sa_column=Column('url', Text))
    accuracy: Optional[float] = Field(default=None, sa_column=Column('accuracy', REAL))
    timestamp: Optional[datetime.datetime] = Field(default=None, sa_column=Column('timestamp', DateTime, server_default=text('CURRENT_TIMESTAMP')))
    nb_traces: Optional[int] = Field(default=None, sa_column=Column('nb_traces', Integer))

    experiment: Optional['Experiment'] = Relationship(back_populates='run')
