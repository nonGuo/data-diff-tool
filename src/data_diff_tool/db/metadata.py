"""Metadata queries using pg_attribute system table.

Queries column metadata including name, data type, nullable flag, and comment
from DWS pg_catalog system tables.
"""

from __future__ import annotations

from data_diff_tool.config.models import Column
from data_diff_tool.db.connection import DWSConnection

QUERY_COLUMNS = """
SELECT
    a.attname AS column_name,
    format_type(a.atttypid, a.atttypmod) AS data_type,
    NOT a.attnotnull AS is_nullable,
    COALESCE(d.description, '') AS column_comment
FROM pg_attribute a
    JOIN pg_class c ON a.attrelid = c.oid
    JOIN pg_namespace n ON c.relnamespace = n.oid
    LEFT JOIN pg_description d ON d.objoid = c.oid AND d.objsubid = a.attnum
WHERE n.nspname = %(schema)s
    AND c.relname = %(table)s
    AND a.attnum > 0
    AND NOT a.attisdropped
ORDER BY a.attnum
"""

QUERY_TABLE_COMMENT = """
SELECT COALESCE(obj_description(c.oid, 'pg_class'), '')
FROM pg_class c
    JOIN pg_namespace n ON c.relnamespace = n.oid
WHERE n.nspname = %(schema)s
    AND c.relname = %(table)s
"""


class MetadataQuery:
    """Queries table and column metadata from DWS pg_catalog system tables."""

    def __init__(self, conn: DWSConnection) -> None:
        self.conn = conn

    def get_columns(self, table_fqn: str) -> list[Column]:
        """
        Get full column metadata for a table.

        Args:
            table_fqn: Fully qualified table name
                       in format 'db.schema.table' or 'schema.table'.

        Returns:
            List of Column objects sorted by attnum.
        """
        schema, table = self._parse_fqn(table_fqn)

        with self.conn.cursor() as cur:
            cur.execute(QUERY_COLUMNS, {"schema": schema, "table": table})
            rows = cur.fetchall()

        return [
            Column(
                name=row[0],
                data_type=row[1],
                nullable=bool(row[2]),
                comment=row[3] or "",
            )
            for row in rows
        ]

    def get_table_comment(self, table_fqn: str) -> str:
        """Get the table-level comment/description."""
        schema, table = self._parse_fqn(table_fqn)

        with self.conn.cursor() as cur:
            cur.execute(QUERY_TABLE_COMMENT, {"schema": schema, "table": table})
            row = cur.fetchone()

        return row[0] if row else ""

    @staticmethod
    def _parse_fqn(table_fqn: str) -> tuple[str, str]:
        """Parse a fully qualified table name into (schema, table)."""
        parts = table_fqn.split(".")
        if len(parts) >= 3:
            # db.schema.table
            return parts[-2], parts[-1]
        if len(parts) == 2:
            # schema.table
            return parts[0], parts[1]
        # bare table name → assume public schema
        return "public", table_fqn
