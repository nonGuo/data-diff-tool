"""Tests for structure checker."""

import pytest
from unittest import mock

from data_diff_tool.config.models import Column, ColumnStructDiff, StructCheckResult
from data_diff_tool.db.metadata import MetadataQuery
from data_diff_tool.verifier.struct import (
    StructChecker,
    _parse_type,
    _is_type_compatible,
)


# ── Type parsing tests ────────────────────────────────────────────

class TestParseType:
    def test_varchar_with_length(self):
        base, params = _parse_type("varchar(100)")
        assert base == "varchar"
        assert params == [100]

    def test_numeric_with_precision(self):
        base, params = _parse_type("numeric(18,2)")
        assert base == "numeric"
        assert params == [18, 2]

    def test_simple_type(self):
        base, params = _parse_type("int8")
        assert base == "int8"
        assert params == []

    def test_nvarchar2(self):
        base, params = _parse_type("nvarchar2(50)")
        assert base == "nvarchar2"
        assert params == [50]


# ── Type compatibility tests ─────────────────────────────────────

class TestTypeCompatibility:
    def _col(self, name: str, data_type: str) -> Column:
        return Column(name=name, data_type=data_type)

    def test_same_type(self):
        assert _is_type_compatible(self._col("x", "varchar(100)"), self._col("x", "varchar(100)"))

    def test_varchar_expansion(self):
        assert _is_type_compatible(self._col("x", "varchar(32)"), self._col("x", "varchar(64)"))

    def test_varchar_to_larger_nvarchar2(self):
        assert _is_type_compatible(self._col("x", "varchar(100)"), self._col("x", "nvarchar2(200)"))

    def test_varchar_to_text(self):
        assert _is_type_compatible(self._col("x", "varchar(100)"), self._col("x", "text"))

    def test_int2_to_int4(self):
        assert _is_type_compatible(self._col("x", "int2"), self._col("x", "int4"))

    def test_int4_to_int8(self):
        assert _is_type_compatible(self._col("x", "int4"), self._col("x", "int8"))

    def test_int2_to_int8(self):
        assert _is_type_compatible(self._col("x", "int2"), self._col("x", "int8"))

    def test_int_downgrade_incompatible(self):
        assert not _is_type_compatible(self._col("x", "int8"), self._col("x", "int4"))

    def test_numeric_expansion(self):
        assert _is_type_compatible(self._col("x", "numeric(10,2)"), self._col("x", "numeric(18,4)"))

    def test_numeric_precision_shrink_incompatible(self):
        assert not _is_type_compatible(self._col("x", "numeric(18,4)"), self._col("x", "numeric(10,2)"))

    def test_varchar_shrink_incompatible(self):
        assert not _is_type_compatible(self._col("x", "varchar(100)"), self._col("x", "varchar(50)"))

    def test_type_change_incompatible(self):
        assert not _is_type_compatible(self._col("x", "varchar(100)"), self._col("x", "int8"))

    def test_none_old_col(self):
        assert not _is_type_compatible(None, self._col("x", "int8"))

    def test_none_new_col(self):
        assert not _is_type_compatible(self._col("x", "int8"), None)


# ── StructChecker integration tests ──────────────────────────────

class TestStructChecker:
    @pytest.fixture
    def checker(self):
        """Create a StructChecker with mocked metadata."""
        mock_meta = mock.MagicMock(spec=MetadataQuery)
        mock_meta.get_columns.side_effect = self._mock_columns
        return StructChecker(mock_meta)

    @staticmethod
    def _mock_columns(fqn: str) -> list[Column]:
        """Return mock column metadata based on FQN."""
        if "old_table" in fqn:
            return [
                Column(name="id", data_type="int8", nullable=False),
                Column(name="name", data_type="varchar(100)", nullable=True),
                Column(name="amount", data_type="numeric(10,2)", nullable=True),
                Column(name="status", data_type="varchar(10)", nullable=False),
            ]
        elif "new_table" in fqn:
            return [
                Column(name="id", data_type="int8", nullable=False),
                Column(name="name", data_type="varchar(200)", nullable=True),  # expanded
                Column(name="amount", data_type="numeric(18,4)", nullable=True),  # expanded
                # status missing → new column added
                Column(name="region", data_type="varchar(50)", nullable=True),  # new
            ]
        return []

    def test_column_existence_check(self, checker: StructChecker):
        result = checker.check("db.sdi.old_table", "db.sdi.new_table", ["id", "status"])
        id_diff = next(d for d in result.column_diffs if d.column == "id")
        assert id_diff.exists_in_old is True
        assert id_diff.exists_in_new is True
        assert id_diff.passed is True

        status_diff = next(d for d in result.column_diffs if d.column == "status")
        assert status_diff.exists_in_old is True
        assert status_diff.exists_in_new is False
        assert status_diff.passed is False

    def test_type_compatibility_report(self, checker: StructChecker):
        result = checker.check("db.sdi.old_table", "db.sdi.new_table", ["name", "amount"])
        name_diff = next(d for d in result.column_diffs if d.column == "name")
        assert name_diff.old_type == "varchar(100)"
        assert name_diff.new_type == "varchar(200)"
        assert name_diff.type_compatible is True

        amount_diff = next(d for d in result.column_diffs if d.column == "amount")
        assert amount_diff.old_type == "numeric(10,2)"
        assert amount_diff.new_type == "numeric(18,4)"
        assert amount_diff.type_compatible is True

    def test_overall_compatible_flag(self, checker: StructChecker):
        result = checker.check("db.sdi.old_table", "db.sdi.new_table", ["id"])
        assert result.compatible is True
        assert result.old_fqn == "db.sdi.old_table"
        assert result.new_fqn == "db.sdi.new_table"

    def test_empty_column_list(self, checker: StructChecker):
        result = checker.check("db.sdi.old_table", "db.sdi.new_table", [])
        assert result.column_diffs == []
        assert result.compatible is True  # vacuously true
