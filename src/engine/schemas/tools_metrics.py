from pydantic import BaseModel
from typing import Self


class ToolsMetrics(BaseModel):
    nb_tools_created: float = 0
    nb_tools_updated: float = 0
    nb_tools_merged: float = 0
    cost: float = 0

    def update(self, metrics: Self) -> None:
        self.nb_tools_created += metrics.nb_tools_created
        self.nb_tools_updated += metrics.nb_tools_updated
        self.nb_tools_merged += metrics.nb_tools_merged
        self.cost += metrics.cost
