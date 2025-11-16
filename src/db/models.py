from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Text, text
from sqlmodel import Field, Relationship, SQLModel

class Ifcmodels(SQLModel, table=True):
    project_name: str = Field(sa_column=Column('project_name', Text, nullable=False))
    model_name: str = Field(sa_column=Column('model_name', Text, nullable=False))
    model_path: str = Field(sa_column=Column('model_path', Text, nullable=False))
    model_description: str = Field(sa_column=Column('model_description', Text, nullable=False))
    id: int = Field(sa_column=Column('id', Integer, primary_key=True))

    ifc_bench: list['IfcBench'] = Relationship(back_populates='ifc')


class ToolUsageStats(SQLModel, table=True):
    __tablename__ = 'tool_usage_stats'

    tool_name: Optional[str] = Field(default=None, sa_column=Column('tool_name', Text, primary_key=True))
    questions_when_included: Optional[int] = Field(default=None, sa_column=Column('questions_when_included', Integer, server_default=text('0')))
    questions_when_called: Optional[int] = Field(default=None, sa_column=Column('questions_when_called', Integer, server_default=text('0')))
    questions_correct_contribution: Optional[int] = Field(default=None, sa_column=Column('questions_correct_contribution', Integer, server_default=text('0')))
    questions_wrong_contribution: Optional[int] = Field(default=None, sa_column=Column('questions_wrong_contribution', Integer, server_default=text('0')))
    created_at_question: Optional[int] = Field(default=None, sa_column=Column('created_at_question', Integer, server_default=text('0')))
    last_question_processed: Optional[int] = Field(default=None, sa_column=Column('last_question_processed', Integer, server_default=text('0')))


class IfcBench(SQLModel, table=True):
    __tablename__ = 'ifc_bench'
    __table_args__ = (
        CheckConstraint('category BETWEEN 1 AND 4'),
    )

    question: str = Field(sa_column=Column('question', Text, nullable=False))
    ground_truth: str = Field(sa_column=Column('ground_truth', Text, nullable=False))
    ifc_id: int = Field(sa_column=Column('ifc_id', ForeignKey('ifcmodels.id'), nullable=False))
    id: int = Field(sa_column=Column('id', Integer, primary_key=True))
    category: Optional[int] = Field(default=None, sa_column=Column('category', Integer))
    cobbie: Optional[str] = Field(default=None, sa_column=Column('cobbie', Text))

    ifc: Optional['Ifcmodels'] = Relationship(back_populates='ifc_bench')
