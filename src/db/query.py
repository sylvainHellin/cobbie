"""
Note: if making any changes in the DB directly, first run:
```zsh
sqlacodegen sqlite:///src/db/db.db --generator sqlmodels --outfile src/db/models.py
```
"""

from functools import wraps
from typing import Callable, List, Optional, TypeVar

from sqlalchemy.orm import selectinload
from sqlmodel import Session, col, select

from src.db import ENGINE
from src.db.models import (
    IfcBench,
    Ifcmodels,
)

T = TypeVar("T")


def with_session(func: Callable[..., T]) -> Callable[..., T]:
    """
    Decorator that automatically provides a database session as the first argument
    to the decorated function and handles session management.
    """

    @wraps(func)
    def wrapper(*args, **kwargs) -> T:
        with Session(ENGINE) as session:
            return func(session, *args, **kwargs)

    return wrapper


def get_dataset(
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    load_ifc_model: bool = False,
) -> List[IfcBench]:
    """
    Return the whole dataset as a List of Dataset

    Args:
        limit: Maximum number of records to return
        offset: Number of records to skip from the beginning
        load_ifc_model: Whether to eager load the IFC model relationship
    """

    with Session(ENGINE) as session:
        # base select statement
        statement = select(IfcBench).order_by(col(IfcBench.id).asc())

        # offset if provided
        if offset:
            statement = statement.offset(offset)

        # limit if limit provided
        if limit:
            statement = statement.limit(limit)

        # Eager loading of the relationship
        if load_ifc_model:
            statement = statement.options(selectinload(getattr(IfcBench, "ifc")))

        dataset = [row for row in session.exec(statement)]
        return dataset


def get_ifc_model(id: int) -> Optional[Ifcmodels]:
    """
    Get the IFC Model from the database from it's id, or None if non is found.
    """
    with Session(ENGINE) as session:
        ifc_model = session.get(Ifcmodels, id)
        return ifc_model


def get_ifc_models() -> List[Ifcmodels]:
    """
    Retrieve all IFC models from the Database
    """
    with Session(ENGINE) as session:
        results = session.exec(select(Ifcmodels))
        ifc_models = [model for model in results]
        return ifc_models
