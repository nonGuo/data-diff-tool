"""Table structure checker (Module A).

Compares column metadata between old and new tables:
- Column existence
- Type compatibility (varchar expansion, int promotion, numeric precision growth)
- Nullable changes
"""

from __future__ import annotations

import re

from data_diff_tool.config.models import (
    Column,
    ColumnStructDiff,
    StructCheckResult,
)
from data_diff_tool.db.metadata import MetadataQuery


class StructChecker:
    """Checks table structure compatibility between old and new tables."""

    def __init__(self, metadata: MetadataQuery) -> None:
        self.metadata = metadata

    def check(self, old_fqn: str, new_fqn: str, columns: list[str]) -> StructCheckResult:
        """
        Compare column types between old and new tables.

        Args:
            old_fqn: Fully qualified name of the old table.
            new_fqn: Fully qualified name of the new table.
            columns: List of column names to check.

        Returns:
            StructCheckResult with per-column diffs and overall compatibility.
        """
        old_cols = {c.name: c for c in self.metadata.get_columns(old_fqn)}
        new_cols = {c.name: c for c in self.metadata.get_columns(new_fqn)}

        diffs: list[ColumnStructDiff] = []
        for col_name in columns:
            old_col = old_cols.get(col_name)
            new_col = new_cols.get(col_name)

            diff = ColumnStructDiff(
                column=col_name,
                old_type=old_col.data_type if old_col else None,
                new_type=new_col.data_type if new_col else None,
                old_nullable=old_col.nullable if old_col else True,
                new_nullable=new_col.nullable if new_col else True,
                exists_in_old=old_col is not None,
                exists_in_new=new_col is not None,
                type_compatible=_is_type_compatible(old_col, new_col),
                nullable_compatible=_is_nullable_compatible(old_col, new_col),
            )
            diffs.append(diff)

        compatible = all(d.passed for d in diffs)

        return StructCheckResult(
            old_fqn=old_fqn,
            new_fqn=new_fqn,
            compatible=compatible,
            column_diffs=diffs,
        )


# ── Type compatibility logic ──────────────────────────────────────

def _parse_type(t: str) -> tuple[str, list[int]]:
    """Extract base type and numeric parameters from a type string.

    Examples:
        'varchar(32)'  → ('varchar', [32])
        'numeric(18,2)' → ('numeric', [18, 2])
        'int8'         → ('int8', [])
    """
    match = re.match(r"^(\w+)(?:\(([^)]+)\))?$", t)
    if not match:
        return t, []
    base = match.group(1)
    params_str = match.group(2)
    params = [int(p.strip()) for p in params_str.split(",")] if params_str else []
    return base, params


STRING_TYPES = {"varchar", "character", "nvarchar2", "text", "bpchar"}
INT_SIZES = {"int2": 2, "int4": 4, "int8": 8, "smallint": 2, "integer": 4, "bigint": 8}


def _is_type_compatible(old_col: Column | None, new_col: Column | None) -> bool:
    """Check if old_col's type can be safely cast to new_col's type."""
    if old_col is None or new_col is None:
        return False

    if old_col.data_type == new_col.data_type:
        return True

    old_base, old_params = _parse_type(old_col.data_type)
    new_base, new_params = _parse_type(new_col.data_type)

    # varchar(N) → varchar(M) where M >= N, or varchar → text
    if old_base in STRING_TYPES and new_base in STRING_TYPES:
        if old_base == "text" or new_base == "text":
            return True  # text is the most permissive string type
        if old_params and new_params:
            return new_params[0] >= old_params[0]
        return True  # no length constraint means unbounded → compatible

    # int promotion: int2 → int4 → int8
    if old_base in INT_SIZES and new_base in INT_SIZES:
        return INT_SIZES[new_base] >= INT_SIZES[old_base]

    # numeric(P,S) → numeric(P',S') where P'>=P, S'>=S
    if old_base in ("numeric", "decimal") and new_base in ("numeric", "decimal"):
        if len(old_params) == 2 and len(new_params) == 2:
            return new_params[0] >= old_params[0] and new_params[1] >= old_params[1]
        return True  # unbounded numeric is compatible

    return False


def _is_nullable_compatible(old_col: Column | None, new_col: Column | None) -> bool:
    """Check if nullable change is acceptable.

    Rules:
    - nullable → nullable: OK
    - nullable → not nullable: OK (old data already has values or NULL is not an issue for comparison)
    - not nullable → nullable: OK (looser constraint)
    - For this tool, nullable changes are always acceptable since we're only
      comparing data, not enforcing schema constraints.
    """
    return True
