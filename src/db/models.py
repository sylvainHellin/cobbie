from typing import Optional

from sqlalchemy import CheckConstraint, Column, ForeignKey, Integer, Text
from sqlmodel import Field, Relationship, SQLModel

class Ifcmodels(SQLModel, table=True):
    project_name: str = Field(sa_column=Column('project_name', Text, nullable=False))
    model_name: str = Field(sa_column=Column('model_name', Text, nullable=False))
    model_path: str = Field(sa_column=Column('model_path', Text, nullable=False))
    model_description: str = Field(sa_column=Column('model_description', Text, nullable=False))
    id: int = Field(sa_column=Column('id', Integer, primary_key=True))

    ifc_bench: list['IfcBench'] = Relationship(back_populates='ifc')


class IfcBench(SQLModel, table=True):
    __tablename__ = 'ifc_bench' # type: ignore
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
