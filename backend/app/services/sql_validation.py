"""SQLGlot validation independent of model output and database execution."""

from typing import Optional, Set, Tuple

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError
from sqlglot.optimizer.qualify import qualify
from sqlglot.optimizer.scope import Scope, traverse_scope

from app.models.database import DatabaseSchema
from app.services.sql_policy import READ_ONLY_SQL_FUNCTIONS


class SQLValidationError(ValueError):
    """A query violates the supported read-only SQL contract."""


SUPPORTED_DIALECTS = {"sqlite": "sqlite", "postgresql": "postgres", "mysql": "mysql"}


class SQLValidator:
    """Validate statement shape, identifiers, and declared join relationships."""

    def __init__(self, schema: DatabaseSchema) -> None:
        """Build normalized lookup tables from trusted schema metadata.

        Args:
            schema: Schema extracted from the configured SQLite database.
        """
        self.schema = schema
        self.tables = {name.casefold(): table for name, table in schema.tables.items()}
        self.relationships: Set[frozenset[Tuple[str, str]]] = set()
        for table in schema.tables.values():
            for foreign_key in table.foreign_keys:
                self.relationships.add(
                    frozenset(
                        {
                            (table.name.casefold(), foreign_key.column.casefold()),
                            (
                                foreign_key.referenced_table.casefold(),
                                foreign_key.referenced_column.casefold(),
                            ),
                        }
                    )
                )

    def validate(self, sql: str, dialect: str = "sqlite") -> str:
        """Validate one SELECT and return safe SQLite SQL for execution.

        Args:
            sql: Untrusted generated or user-supplied SQL text.
            dialect: Input SQL dialect. PostgreSQL and MySQL are transpiled to SQLite
                after their source AST passes the same read-only/schema checks.

        Returns:
            Canonical SQLite SQL; no database operations are performed.

        Raises:
            SQLValidationError: Parsing, policy, identifier, or join checks fail.
        """
        if not sql.strip() or len(sql) > 12000:
            raise SQLValidationError("Supply a nonempty SELECT of at most 12000 characters.")
        read_dialect = SUPPORTED_DIALECTS.get(dialect.casefold())
        if read_dialect is None:
            supported = ", ".join(SUPPORTED_DIALECTS)
            raise SQLValidationError(f"Unsupported SQL dialect. Choose one of: {supported}.")
        try:
            statements = sqlglot.parse(sql, read=read_dialect)
            if len(statements) != 1 or not isinstance(statements[0], exp.Select):
                raise SQLValidationError("Exactly one statement with a SELECT root is required.")
            expression = statements[0]
            self._check_expression_policy(expression)
            self._check_sources(expression)
            qualified = qualify(
                expression.copy(),
                dialect=read_dialect,
                schema={name: table.columns for name, table in self.schema.tables.items()},
                validate_qualify_columns=True,
                allow_partial_qualification=False,
            )
            self._check_columns(qualified)
            self._check_joins(qualified)
            canonical = qualified.sql(dialect=read_dialect, pretty=True)
            if read_dialect == "sqlite":
                return canonical
            translated = sqlglot.transpile(canonical, read=read_dialect, write="sqlite")
            if len(translated) != 1:
                raise SQLValidationError("Dialect translation must produce exactly one statement.")
            return self.validate(translated[0], dialect="sqlite")
        except SqlglotError as error:
            raise SQLValidationError(str(error)) from error

    def _check_expression_policy(self, expression: exp.Select) -> None:
        """Reject nested writes, commands, external sources, and recursive queries.

        Args:
            expression: Parsed SELECT tree to inspect without mutation.
        """
        forbidden_types = (
            exp.DDL,
            exp.DML,
            exp.Command,
            exp.Into,
            exp.Lock,
            exp.Pragma,
            exp.Attach,
            exp.Detach,
            exp.Transaction,
            exp.Set,
            exp.Use,
        )
        for node in expression.walk():
            if isinstance(node, forbidden_types):
                raise SQLValidationError(f"Unsupported SQL operation: {node.key}.")
            if isinstance(node, exp.Func) and not isinstance(node, exp.Exists):
                function_name = (
                    node.name if isinstance(node, exp.Anonymous) else node.sql_name()
                ).casefold()
                if function_name not in READ_ONLY_SQL_FUNCTIONS:
                    raise SQLValidationError(f"Unsupported SQL function: {function_name}.")
            if isinstance(node, exp.With) and node.args.get("recursive"):
                raise SQLValidationError("Recursive queries are not supported.")
            if isinstance(node, exp.Table) and (
                node.db or node.catalog or not isinstance(node.this, exp.Identifier)
            ):
                raise SQLValidationError("Only local application tables are available.")

    def _check_sources(self, expression: exp.Expression) -> None:
        """Resolve physical tables without confusing CTE names with table names.

        Args:
            expression: Parsed tree whose scopes will be inspected.
        """
        for scope in traverse_scope(expression):
            for _, source in scope.selected_sources.values():
                if isinstance(source, exp.Table) and source.name.casefold() not in self.tables:
                    raise SQLValidationError(f"Unknown table: {source.name}.")

    def _check_columns(self, expression: exp.Expression) -> None:
        """Verify qualified base columns against the actual schema dictionary.

        Args:
            expression: Qualified tree with resolved table aliases and output columns.
        """
        for scope in traverse_scope(expression):
            for column in scope.columns:
                source = scope.sources.get(column.table)
                if isinstance(source, exp.Table):
                    available = self.tables[source.name.casefold()].columns
                    if column.name.casefold() not in {name.casefold() for name in available}:
                        raise SQLValidationError(f"Unknown column: {column.sql()}.")

    def _resolve_column(self, scope: Scope, column: exp.Column) -> Optional[Tuple[str, str]]:
        """Trace a column through projection-only derived tables to its physical source.

        Args:
            scope: Scope in which the column is referenced.
            column: Qualified column to resolve.

        Returns:
            Physical table/column pair, or None for computed or unresolved values.
        """
        source = scope.sources.get(column.table)
        if isinstance(source, exp.Table):
            return source.name.casefold(), column.name.casefold()
        if isinstance(source, Scope):
            for projection in source.expression.selects:
                if projection.alias_or_name.casefold() == column.name.casefold():
                    value = projection.this if isinstance(projection, exp.Alias) else projection
                    if isinstance(value, exp.Column):
                        return self._resolve_column(source, value)
        return None

    def _check_joins(self, expression: exp.Expression) -> None:
        """Require each join to connect its source through a declared relationship.

        Args:
            expression: Qualified SELECT tree to inspect without mutation.

        Raises:
            SQLValidationError: A join lacks a supported relationship predicate.
        """
        for scope in traverse_scope(expression):
            from_clause = scope.expression.args.get("from_")
            prior_aliases = {from_clause.this.alias_or_name} if from_clause else set()
            for join in scope.expression.args.get("joins", []):
                joined_alias = join.this.alias_or_name
                predicate = join.args.get("on")
                connected = False
                # Only positive equality conjuncts establish a relationship.
                if predicate is not None:
                    conjuncts = (
                        predicate.flatten() if isinstance(predicate, exp.And) else [predicate]
                    )
                    for equality in conjuncts:
                        equality = equality.unnest()
                        if not isinstance(equality, exp.EQ):
                            continue
                        left, right = equality.left, equality.right
                        if not isinstance(left, exp.Column) or not isinstance(right, exp.Column):
                            continue
                        connects_sources = (
                            left.table == joined_alias and right.table in prior_aliases
                        ) or (right.table == joined_alias and left.table in prior_aliases)
                        pair = frozenset(
                            filter(
                                None,
                                [
                                    self._resolve_column(scope, left),
                                    self._resolve_column(scope, right),
                                ],
                            )
                        )
                        if connects_sources and pair in self.relationships:
                            connected = True
                if not connected:
                    raise SQLValidationError(
                        "Join must use a declared foreign-key relationship with an ON equality."
                    )
                prior_aliases.add(joined_alias)
