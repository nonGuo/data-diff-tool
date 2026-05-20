"""Tests for data checker."""

from unittest import mock

import pytest

from data_diff_tool.config.models import EntityMapping, VerificationTask
from data_diff_tool.db.connection import DWSConnection
from data_diff_tool.verifier.data import DataChecker


@pytest.fixture
def mock_conn():
    """Create a mock DWSConnection."""
    return mock.MagicMock(spec=DWSConnection)


def _task(**kwargs) -> VerificationTask:
    """Create a VerificationTask with sensible defaults."""
    entity = kwargs.get("entity", EntityMapping(
        old_fqn="db.sdi.old_table",
        new_fqn="db.sdi.new_table",
        mapping_type="1:1",
    ))
    return VerificationTask(entity=entity, **{
        "primary_keys": kwargs.get("primary_keys", ["id"]),
        "identical_columns": kwargs.get("identical_columns", ["name", "amount"]),
        "cast_columns": kwargs.get("cast_columns", []),
        "filter_cond": kwargs.get("filter_cond"),
    })


class TestGenerateSQL:
    def test_generate_sql_basic(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task()
        sql = checker.generate_sql(task)

        assert "FULL JOIN db.sdi.new_table b" in sql
        assert "FROM db.sdi.old_table a" in sql
        assert "ON a.id = b.id" in sql

    def test_generate_sql_with_filter(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(filter_cond="dt = '2026-03-01'")
        sql = checker.generate_sql(task)

        assert "WHERE dt = '2026-03-01'" in sql

    def test_generate_sql_default_filter(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(filter_cond=None)
        sql = checker.generate_sql(task)

        assert "WHERE 1=1" in sql

    def test_generate_sql_with_cast_columns(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(cast_columns=["old_col"])
        sql = checker.generate_sql(task)

        assert "CAST(a.old_col AS VARCHAR)" in sql
        assert "CAST(b.old_col AS VARCHAR)" in sql

    def test_generate_sql_with_composite_pk(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(primary_keys=["col_a", "col_b"])
        sql = checker.generate_sql(task)

        assert "ON a.col_a = b.col_a AND a.col_b = b.col_b" in sql

    def test_generate_sql_no_primary_keys_raises(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(primary_keys=[])
        with pytest.raises(ValueError, match="No primary keys configured"):
            checker.generate_sql(task)

    def test_generate_sql_no_columns_placeholder(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(identical_columns=[], cast_columns=[])
        sql = checker.generate_sql(task)

        assert "1 AS placeholder" in sql


class TestExecuteSQL:
    def test_execute_parses_results(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task(identical_columns=["name", "amount"])

        # Mock cursor context
        mock_cursor = mock.MagicMock()
        mock_cursor.description = [
            ("total_count",),
            ("new_only_count",),
            ("old_only_count",),
            ("name_diff_cnt",),
            ("amount_diff_cnt",),
        ]
        mock_cursor.fetchone.return_value = (1000, 5, 3, 0, 12)
        mock_conn.cursor.return_value.__enter__ = mock.MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = mock.MagicMock(return_value=False)

        result = checker.execute(task)

        assert result.total_count == 1000
        assert result.old_only_count == 3
        assert result.new_only_count == 5
        assert len(result.column_results) == 2

        name_result = next(c for c in result.column_results if c.column == "name")
        assert name_result.diff_count == 0
        assert name_result.passed is True

        amount_result = next(c for c in result.column_results if c.column == "amount")
        assert amount_result.diff_count == 12
        assert amount_result.diff_rate == pytest.approx(1.2)
        assert amount_result.passed is False

    def test_execute_no_rows_raises_error(self, mock_conn):
        checker = DataChecker(mock_conn)
        task = _task()

        mock_cursor = mock.MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = mock.MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = mock.MagicMock(return_value=False)

        with pytest.raises(RuntimeError, match="Query returned no rows"):
            checker.execute(task)
