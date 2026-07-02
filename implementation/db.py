from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class ValidationError(ValueError):
    """Raised when a database request cannot be safely executed."""


COMPARISON_OPERATORS = {
    "eq": "=",
    "=": "=",
    "==": "=",
    "ne": "!=",
    "!=": "!=",
    "<>": "!=",
    "gt": ">",
    ">": ">",
    "gte": ">=",
    ">=": ">=",
    "lt": "<",
    "<": "<",
    "lte": "<=",
    "<=": "<=",
    "like": "LIKE",
}

NULL_OPERATORS = {"is_null", "null", "not_null", "is_not_null"}
LIST_OPERATORS = {"in", "not_in"}
AGGREGATE_METRICS = {"count", "avg", "sum", "min", "max"}
NUMERIC_TYPE_MARKERS = ("INT", "REAL", "NUM", "DEC", "DOUB", "FLOA")


def quote_identifier(identifier: str) -> str:
    """Quote a previously validated SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def _is_non_string_sequence(value: Any) -> bool:
    return isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))


class SQLiteAdapter:
    """Small validation-first SQLite data access layer for the MCP tools."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def list_tables(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return [row["name"] for row in rows]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        self._ensure_table(table)
        with self.connect() as conn:
            columns = conn.execute(
                f"PRAGMA table_info({quote_identifier(table)})"
            ).fetchall()
            foreign_keys = conn.execute(
                f"PRAGMA foreign_key_list({quote_identifier(table)})"
            ).fetchall()

        return {
            "table": table,
            "columns": [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "nullable": not bool(row["notnull"]),
                    "default": row["dflt_value"],
                    "primary_key": bool(row["pk"]),
                }
                for row in columns
            ],
            "foreign_keys": [
                {
                    "column": row["from"],
                    "references_table": row["table"],
                    "references_column": row["to"],
                    "on_update": row["on_update"],
                    "on_delete": row["on_delete"],
                }
                for row in foreign_keys
            ],
        }

    def database_schema(self) -> dict[str, Any]:
        return {
            "database": str(self.db_path),
            "tables": [self.get_table_schema(table) for table in self.list_tables()],
        }

    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: Any = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        self._ensure_table(table)
        selected_columns = self._normalize_selected_columns(table, columns)
        limit = self._validate_limit(limit)
        offset = self._validate_offset(offset)
        where_sql, params = self._build_where_clause(table, filters)

        columns_sql = (
            "*"
            if selected_columns is None
            else ", ".join(quote_identifier(column) for column in selected_columns)
        )
        sql = f"SELECT {columns_sql} FROM {quote_identifier(table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if order_by:
            self._ensure_column(table, order_by)
            direction = "DESC" if descending else "ASC"
            sql += f" ORDER BY {quote_identifier(order_by)} {direction}"
        sql += " LIMIT ? OFFSET ?"

        with self.connect() as conn:
            rows = conn.execute(sql, [*params, limit, offset]).fetchall()

        return {
            "table": table,
            "columns": selected_columns or "all",
            "limit": limit,
            "offset": offset,
            "row_count": len(rows),
            "rows": [dict(row) for row in rows],
        }

    def insert(self, table: str, values: Mapping[str, Any]) -> dict[str, Any]:
        self._ensure_table(table)
        if not isinstance(values, Mapping) or not values:
            raise ValidationError("Insert values must be a non-empty object.")

        columns = list(values.keys())
        for column in columns:
            if not isinstance(column, str):
                raise ValidationError("Insert column names must be strings.")
            self._ensure_column(table, column)

        column_sql = ", ".join(quote_identifier(column) for column in columns)
        placeholders = ", ".join("?" for _ in columns)
        sql = (
            f"INSERT INTO {quote_identifier(table)} ({column_sql}) "
            f"VALUES ({placeholders})"
        )

        try:
            with self.connect() as conn:
                cursor = conn.execute(sql, [values[column] for column in columns])
                inserted_id = cursor.lastrowid
                inserted_row = self._fetch_inserted_row(conn, table, inserted_id)
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"Insert failed: {exc}") from exc

        return {
            "table": table,
            "inserted_id": inserted_id,
            "row": inserted_row or dict(values),
        }

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: Any = None,
        group_by: str | list[str] | None = None,
    ) -> dict[str, Any]:
        self._ensure_table(table)
        metric = self._validate_metric(metric)
        group_columns = self._normalize_group_by(table, group_by)
        aggregate_column = self._validate_aggregate_column(table, metric, column)
        where_sql, params = self._build_where_clause(table, filters)

        if metric == "count" and aggregate_column is None:
            metric_sql = "COUNT(*)"
        else:
            metric_sql = f"{metric.upper()}({quote_identifier(aggregate_column)})"

        select_parts = [quote_identifier(column) for column in group_columns]
        select_parts.append(f"{metric_sql} AS value")

        sql = f"SELECT {', '.join(select_parts)} FROM {quote_identifier(table)}"
        if where_sql:
            sql += f" WHERE {where_sql}"
        if group_columns:
            group_sql = ", ".join(quote_identifier(column) for column in group_columns)
            sql += f" GROUP BY {group_sql} ORDER BY {group_sql}"

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return {
            "table": table,
            "metric": metric,
            "column": aggregate_column or "*",
            "group_by": group_columns,
            "rows": [dict(row) for row in rows],
        }

    def _ensure_table(self, table: str) -> None:
        if not isinstance(table, str) or not table:
            raise ValidationError("Table name must be a non-empty string.")
        tables = self.list_tables()
        if table not in tables:
            available = ", ".join(tables) or "none"
            raise ValidationError(
                f"Unknown table '{table}'. Available tables: {available}."
            )

    def _columns_by_name(self, table: str) -> dict[str, dict[str, Any]]:
        schema = self.get_table_schema(table)
        return {column["name"]: column for column in schema["columns"]}

    def _ensure_column(self, table: str, column: str) -> None:
        if not isinstance(column, str) or not column:
            raise ValidationError("Column name must be a non-empty string.")
        columns = self._columns_by_name(table)
        if column not in columns:
            available = ", ".join(columns)
            raise ValidationError(
                f"Unknown column '{column}' for table '{table}'. "
                f"Available columns: {available}."
            )

    def _normalize_selected_columns(
        self, table: str, columns: list[str] | str | None
    ) -> list[str] | None:
        if columns is None:
            return None
        if isinstance(columns, str):
            columns = [columns]
        if not _is_non_string_sequence(columns) or not columns:
            raise ValidationError("Search columns must be a non-empty list of names.")

        normalized = list(columns)
        for column in normalized:
            self._ensure_column(table, column)
        return normalized

    def _normalize_group_by(
        self, table: str, group_by: str | list[str] | None
    ) -> list[str]:
        if group_by is None:
            return []
        if isinstance(group_by, str):
            group_columns = [group_by]
        elif _is_non_string_sequence(group_by) and group_by:
            group_columns = list(group_by)
        else:
            raise ValidationError("group_by must be a column name or non-empty list.")

        for column in group_columns:
            self._ensure_column(table, column)
        return group_columns

    def _validate_metric(self, metric: str) -> str:
        if not isinstance(metric, str):
            raise ValidationError("Aggregate metric must be a string.")
        normalized = metric.lower()
        if normalized not in AGGREGATE_METRICS:
            allowed = ", ".join(sorted(AGGREGATE_METRICS))
            raise ValidationError(
                f"Unsupported aggregate metric '{metric}'. Allowed metrics: {allowed}."
            )
        return normalized

    def _validate_aggregate_column(
        self, table: str, metric: str, column: str | None
    ) -> str | None:
        if metric == "count" and column in (None, "*"):
            return None
        if not column or column == "*":
            raise ValidationError(f"Aggregate metric '{metric}' requires a column.")

        self._ensure_column(table, column)
        if metric in {"avg", "sum"} and not self._is_numeric_column(table, column):
            raise ValidationError(
                f"Aggregate metric '{metric}' requires a numeric column; "
                f"'{column}' is not numeric."
            )
        return column

    def _is_numeric_column(self, table: str, column: str) -> bool:
        column_type = self._columns_by_name(table)[column]["type"].upper()
        return any(marker in column_type for marker in NUMERIC_TYPE_MARKERS)

    def _validate_limit(self, limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise ValidationError("limit must be an integer.")
        if limit < 1 or limit > 100:
            raise ValidationError("limit must be between 1 and 100.")
        return limit

    def _validate_offset(self, offset: int) -> int:
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise ValidationError("offset must be an integer.")
        if offset < 0:
            raise ValidationError("offset must be zero or greater.")
        return offset

    def _build_where_clause(self, table: str, filters: Any) -> tuple[str, list[Any]]:
        normalized_filters = self._normalize_filters(filters)
        clauses: list[str] = []
        params: list[Any] = []

        for item in normalized_filters:
            column = item["column"]
            operator = item["operator"]
            value = item.get("value")
            self._ensure_column(table, column)
            column_sql = quote_identifier(column)

            if operator in NULL_OPERATORS:
                if operator in {"is_null", "null"}:
                    clauses.append(f"{column_sql} IS NULL")
                else:
                    clauses.append(f"{column_sql} IS NOT NULL")
                continue

            if operator in LIST_OPERATORS:
                if not _is_non_string_sequence(value) or not value:
                    raise ValidationError(
                        f"Operator '{operator}' requires a non-empty list value."
                    )
                placeholders = ", ".join("?" for _ in value)
                sql_operator = "IN" if operator == "in" else "NOT IN"
                clauses.append(f"{column_sql} {sql_operator} ({placeholders})")
                params.extend(value)
                continue

            sql_operator = COMPARISON_OPERATORS.get(operator)
            if sql_operator is None:
                allowed = sorted(
                    {*COMPARISON_OPERATORS, *NULL_OPERATORS, *LIST_OPERATORS}
                )
                raise ValidationError(
                    f"Unsupported filter operator '{operator}'. "
                    f"Allowed operators: {', '.join(allowed)}."
                )

            if value is None and sql_operator in {"=", "!="}:
                null_operator = "IS" if sql_operator == "=" else "IS NOT"
                clauses.append(f"{column_sql} {null_operator} NULL")
            else:
                clauses.append(f"{column_sql} {sql_operator} ?")
                params.append(value)

        return " AND ".join(clauses), params

    def _normalize_filters(self, filters: Any) -> list[dict[str, Any]]:
        if filters in (None, [], {}):
            return []

        if isinstance(filters, Mapping):
            if "column" in filters:
                return [self._normalize_filter_item(filters)]
            return [
                self._normalize_filter_item(
                    {"column": column, **self._condition_to_dict(condition)}
                )
                for column, condition in filters.items()
            ]

        if _is_non_string_sequence(filters):
            return [self._normalize_filter_item(item) for item in filters]

        raise ValidationError(
            "filters must be an object, a list of filter objects, or null."
        )

    def _condition_to_dict(self, condition: Any) -> dict[str, Any]:
        if isinstance(condition, Mapping):
            operator = condition.get("operator", condition.get("op", "eq"))
            if "value" in condition:
                value = condition["value"]
            elif "values" in condition:
                value = condition["values"]
            else:
                value = None
            return {"operator": operator, "value": value}
        return {"operator": "eq", "value": condition}

    def _normalize_filter_item(self, item: Any) -> dict[str, Any]:
        if not isinstance(item, Mapping):
            raise ValidationError("Each filter must be an object.")

        column = item.get("column", item.get("field"))
        if not isinstance(column, str) or not column:
            raise ValidationError("Each filter requires a non-empty column.")

        operator = item.get("operator", item.get("op", "eq"))
        if not isinstance(operator, str):
            raise ValidationError("Filter operator must be a string.")

        return {
            "column": column,
            "operator": operator.lower(),
            "value": item.get("value"),
        }

    def _fetch_inserted_row(
        self, conn: sqlite3.Connection, table: str, inserted_id: int | None
    ) -> dict[str, Any] | None:
        if inserted_id is None:
            return None
        primary_keys = [
            column["name"]
            for column in self.get_table_schema(table)["columns"]
            if column["primary_key"]
        ]
        if len(primary_keys) != 1:
            return None

        row = conn.execute(
            f"""
            SELECT *
            FROM {quote_identifier(table)}
            WHERE {quote_identifier(primary_keys[0])} = ?
            """,
            [inserted_id],
        ).fetchone()
        return dict(row) if row else None

