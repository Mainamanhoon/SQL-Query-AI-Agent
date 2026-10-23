"""Trusted, read-only schema discovery, separate from generated SQL execution."""

import sqlite3
from pathlib import Path
from typing import Dict

from app.models.database import DatabaseSchema, ForeignKey, TableSchema


def read_schema(database_path: Path) -> DatabaseSchema:
    """Read table DDL and relationship metadata using fixed internal queries.

    Args:
        database_path: Existing SQLite file to inspect.

    Returns:
        Application tables and their full CREATE TABLE statements.

    Side Effects:
        Opens and closes a read-only metadata connection. No user SQL is accepted.
    """
    connection = sqlite3.connect(f"{database_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        tables: Dict[str, TableSchema] = {}
        definitions = connection.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for table_name, ddl in definitions:
            quoted_name = '"' + table_name.replace('"', '""') + '"'
            columns = connection.execute(f"PRAGMA table_info({quoted_name})").fetchall()
            relationships = connection.execute(f"PRAGMA foreign_key_list({quoted_name})").fetchall()
            tables[table_name] = TableSchema(
                name=table_name,
                ddl=ddl,
                columns={column[1]: column[2] for column in columns},
                primary_keys=[column[1] for column in columns if column[5]],
                foreign_keys=[
                    ForeignKey(column=row[3], referenced_table=row[2], referenced_column=row[4])
                    for row in relationships
                ],
            )
        return DatabaseSchema(
            tables=tables, ddl="\n\n".join(table.ddl + ";" for table in tables.values())
        )
    finally:
        connection.close()
