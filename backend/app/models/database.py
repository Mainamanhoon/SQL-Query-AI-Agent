"""Schema and query result contracts."""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, Field

CellValue = Union[str, int, float, None]


class ForeignKey(BaseModel):
    """A declared relationship from one table to another."""

    column: str
    referenced_table: str
    referenced_column: str


class QueryCostEstimate(BaseModel):
    """Deterministic SQLite query-plan summary, not a measured benchmark."""

    planner_steps: int = Field(ge=0)
    full_scan_tables: List[str] = Field(default_factory=list)
    index_uses: List[str] = Field(default_factory=list)
    summary: str = Field(min_length=1, max_length=1000)


class TableSchema(BaseModel):
    """Columns and relationships extracted from SQLite metadata."""

    name: str
    ddl: str
    columns: Dict[str, str]
    primary_keys: List[str] = Field(default_factory=list)
    foreign_keys: List[ForeignKey] = Field(default_factory=list)


class DatabaseSchema(BaseModel):
    """The available application schema, excluding SQLite internals."""

    tables: Dict[str, TableSchema]
    ddl: str


class QueryResults(BaseModel):
    """Bounded results with positional rows, preserving duplicate column labels."""

    columns: List[str] = Field(default_factory=list)
    rows: List[List[CellValue]] = Field(default_factory=list)
    truncated: bool = False
    elapsed_ms: float = 0
    row_limit: Optional[int] = None
    cost_estimate: Optional[QueryCostEstimate] = None
