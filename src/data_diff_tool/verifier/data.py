"""Data consistency checker (Module B).

Generates and executes dynamic FULL JOIN SQL to compare data between old and new tables.
Uses NULL-safe IS NOT DISTINCT FROM for comparison to handle NULL = NULL correctly.
"""

from __future__ import annotations

import logging

from data_diff_tool.config.models import DataCheckResult, ColumnCheckResult, VerificationTask
from data_diff_tool.db.connection import DWSConnection

logger = logging.getLogger(__name__)


class DataChecker:
    """Checks data consistency between old and new tables using FULL JOIN."""

    def __init__(self, conn: DWSConnection) -> None:
        self.conn = conn

    def generate_sql(self, task: VerificationTask) -> str:
        """Generate the dynamic verification SQL for a task."""
        if not task.primary_keys:
            raise ValueError(
                f"No primary keys configured for {task.entity.old_fqn} -> {task.entity.new_fqn}. "
                f"Specify primary keys in the sample configuration sheet or via --primary-keys."
            )

        pk_conditions = " AND ".join(f"a.{pk} = b.{pk}" for pk in task.primary_keys)

        # identical columns: strict NULL-safe comparison
        identical_checks = []
        for col in task.identical_columns:
            expr = (
                f"SUM(CASE WHEN NOT (a.{col} IS NOT DISTINCT FROM b.{col}) "
                f"THEN 1 ELSE 0 END) AS {col}_diff_cnt"
            )
            identical_checks.append(expr)

        # cast columns: compare after CAST to VARCHAR
        cast_checks = []
        for col in task.cast_columns:
            expr = (
                f"SUM(CASE WHEN NOT (CAST(a.{col} AS VARCHAR) IS NOT DISTINCT FROM CAST(b.{col} AS VARCHAR)) "
                f"THEN 1 ELSE 0 END) AS {col}_diff_cnt"
            )
            cast_checks.append(expr)

        all_column_checks = identical_checks + cast_checks
        checks_clause = ",\n    ".join(all_column_checks) if all_column_checks else "1 AS placeholder"

        filter_clause = task.filter_cond if task.filter_cond else "1=1"

        pk0 = task.primary_keys[0]

        sql = (
            f"SELECT\n"
            f"    COUNT(1) AS total_count,\n"
            f"    SUM(CASE WHEN a.{pk0} IS NULL THEN 1 ELSE 0 END) AS new_only_count,\n"
            f"    SUM(CASE WHEN b.{pk0} IS NULL THEN 1 ELSE 0 END) AS old_only_count,\n"
            f"    {checks_clause}\n"
            f"FROM {task.entity.old_fqn} a\n"
            f"FULL JOIN {task.entity.new_fqn} b\n"
            f"  ON {pk_conditions}\n"
            f"WHERE {filter_clause};"
        )

        logger.debug("Generated SQL for %s -> %s:\n%s", task.entity.old_fqn, task.entity.new_fqn, sql)
        return sql

    def execute(self, task: VerificationTask) -> DataCheckResult:
        """Execute the verification SQL and parse results."""
        sql = self.generate_sql(task)

        with self.conn.cursor() as cur:
            cur.execute(sql)
            row = cur.fetchone()

        if row is None:
            raise RuntimeError("Query returned no rows")

        col_names = [desc[0] for desc in cur.description] if cur.description else []

        # Parse column diff results
        column_results: list[ColumnCheckResult] = []
        total = row[0] or 0
        for col_name in task.identical_columns + task.cast_columns:
            diff_col = f"{col_name}_diff_cnt"
            if diff_col in col_names:
                idx = col_names.index(diff_col)
                diff_count = row[idx] or 0
                diff_rate = (diff_count / total * 100) if total > 0 else 0.0
                column_results.append(ColumnCheckResult(
                    column=col_name,
                    diff_count=diff_count,
                    diff_rate=diff_rate,
                    passed=diff_count == 0,
                ))

        return DataCheckResult(
            total_count=total,
            old_only_count=row[2] or 0,
            new_only_count=row[1] or 0,
            column_results=column_results,
        )
