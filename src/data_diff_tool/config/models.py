"""Core data models for verification tasks."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Column:
    """Represents a database column with full metadata."""
    name: str
    data_type: str
    nullable: bool = True
    comment: str = ""


@dataclass
class ColumnStructDiff:
    """Per-column structure comparison result."""
    column: str
    old_type: str | None = None
    new_type: str | None = None
    old_nullable: bool = True
    new_nullable: bool = True
    type_compatible: bool = True
    nullable_compatible: bool = True
    exists_in_old: bool = True
    exists_in_new: bool = True

    @property
    def passed(self) -> bool:
        return (
            self.exists_in_old
            and self.exists_in_new
            and self.type_compatible
            and self.nullable_compatible
        )


@dataclass
class EntityMapping:
    """Represents an entity-level table mapping between old and new tables."""
    old_fqn: str
    new_fqn: str
    mapping_type: str  # "1:1", "1:N", "N:1", "1:0", "0:1"
    description: str = ""

    @property
    def composite_key(self) -> tuple[str, str]:
        """组合主键：(old_fqn, new_fqn)，用于关联属性级 mapping"""
        return (self.old_fqn, self.new_fqn)


@dataclass
class ColumnMapping:
    """Represents a column-level mapping between old and new columns."""
    old_fqn: str              # old_db.old_schema.old_table
    new_fqn: str              # new_db.new_schema.new_table
    old_col: Column
    new_col: Column
    change_type: str          # "1:1 完全一致", "1:1 字段类型变化", ...
    data_changed: bool = False

    @property
    def entity_key(self) -> tuple[str, str]:
        """关联到实体级 mapping 的组合主键"""
        return (self.old_fqn, self.new_fqn)

    @property
    def composite_key(self) -> tuple[str, str, str, str]:
        """属性级组合主键：(old_fqn, new_fqn, old_col, new_col)"""
        return (self.old_fqn, self.new_fqn, self.old_col.name, self.new_col.name)


@dataclass
class VerificationTask:
    """A runnable verification task for a 1:1 table pair."""
    entity: EntityMapping
    primary_keys: list[str] = field(default_factory=list)
    identical_columns: list[str] = field(default_factory=list)
    cast_columns: list[str] = field(default_factory=list)
    skipped_columns: list[str] = field(default_factory=list)
    filter_cond: str | None = None


@dataclass
class SkippedTask:
    """A task that cannot be auto-verified (1:N, N:1)."""
    entity: EntityMapping
    reason: str


@dataclass
class InventoryTask:
    """A task that only needs to be recorded (1:0, 0:1)."""
    entity: EntityMapping


@dataclass
class StructCheckResult:
    """Table-level structure check result."""
    old_fqn: str
    new_fqn: str
    compatible: bool
    column_diffs: list[ColumnStructDiff] = field(default_factory=list)


@dataclass
class DataCheckResult:
    total_count: int
    old_only_count: int
    new_only_count: int
    column_results: list[ColumnCheckResult] = field(default_factory=list)


@dataclass
class ColumnCheckResult:
    column: str
    diff_count: int
    diff_rate: float
    passed: bool


@dataclass
class TaskResult:
    task: VerificationTask | SkippedTask | InventoryTask
    struct_check: StructCheckResult | None = None
    data_check: DataCheckResult | None = None
    status: str = "pending"
    elapsed_ms: int = 0
