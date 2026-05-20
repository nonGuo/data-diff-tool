"""Tests for HTML report generator."""

import os
import tempfile

from data_diff_tool.config.models import (
    ColumnCheckResult,
    ColumnStructDiff,
    DataCheckResult,
    EntityMapping,
    InventoryTask,
    SkippedTask,
    StructCheckResult,
    TaskResult,
    VerificationTask,
)
from data_diff_tool.report.generator import ReportGenerator


class TestGenerateHTMLReport:
    def test_generates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            path = gen.generate([])
            assert os.path.exists(path)
            assert path.endswith(".html")
            with open(path) as f:
                content = f.read()
            assert "<!DOCTYPE html>" in content
            assert "Data Diff Verification Report" in content

    def test_generates_summary_counts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="a", new_fqn="b", mapping_type="1:1")
            results = [
                TaskResult(task=VerificationTask(entity=entity), status="passed"),
                TaskResult(task=VerificationTask(entity=entity), status="failed"),
                TaskResult(task=SkippedTask(entity=entity, reason="test"), status="skipped"),
            ]
            path = gen.generate(results)
            with open(path) as f:
                content = f.read()
            assert "Total tasks: 3" in content
            assert '>1<' in content  # passed count

    def test_renders_verification_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(
                old_fqn="db.sdi.old_table",
                new_fqn="db.sdi.new_table",
                mapping_type="1:1",
            )
            task = VerificationTask(
                entity=entity,
                primary_keys=["id"],
                filter_cond="dt = '2026-01-01'",
            )
            result = TaskResult(task=task, status="passed")
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "db.sdi.old_table" in content
            assert "db.sdi.new_table" in content
            assert "id" in content
            assert "dt = '2026-01-01'" in content

    def test_renders_skipped_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="a", new_fqn="b", mapping_type="1:N")
            result = TaskResult(
                task=SkippedTask(entity=entity, reason="needs review"),
                status="skipped",
            )
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "SKIPPED" in content
            assert "needs review" in content

    def test_renders_inventory_task(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="db.t1", new_fqn="", mapping_type="1:0")
            result = TaskResult(task=InventoryTask(entity=entity), status="skipped")
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "db.t1" in content
            # 1:0: old exists, new is empty → shows "db.t1 ↔ (new)"
            assert "(new)" in content

        # Also test 0:1: new exists, old is empty
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="", new_fqn="db.t2", mapping_type="0:1")
            result = TaskResult(task=InventoryTask(entity=entity), status="skipped")
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "db.t2" in content
            assert "(removed)" in content

    def test_renders_struct_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="a", new_fqn="b", mapping_type="1:1")
            task = VerificationTask(entity=entity)
            struct = StructCheckResult(
                old_fqn="a", new_fqn="b", compatible=True,
                column_diffs=[
                    ColumnStructDiff(column="id", old_type="int8", new_type="int8"),
                ],
            )
            result = TaskResult(task=task, struct_check=struct, status="passed")
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "int8" in content
            assert "Compatible" in content

    def test_renders_data_check(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="a", new_fqn="b", mapping_type="1:1")
            task = VerificationTask(entity=entity)
            data = DataCheckResult(
                total_count=10000,
                old_only_count=5,
                new_only_count=3,
                column_results=[
                    ColumnCheckResult(column="name", diff_count=0, diff_rate=0.0, passed=True),
                    ColumnCheckResult(column="amount", diff_count=12, diff_rate=0.12, passed=False),
                ],
            )
            result = TaskResult(task=task, data_check=data, status="failed")
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "10,000" in content
            assert "name" in content
            assert "amount" in content
            assert "0.1200%" in content

    def test_renders_skipped_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            gen = ReportGenerator(output_dir=tmpdir)
            entity = EntityMapping(old_fqn="a", new_fqn="b", mapping_type="1:1")
            task = VerificationTask(
                entity=entity,
                identical_columns=["id"],
                skipped_columns=["status", "type"],
            )
            result = TaskResult(task=task, status="passed")
            path = gen.generate([result])
            with open(path) as f:
                content = f.read()
            assert "Skipped Columns" in content
            assert "status" in content
            assert "type" in content
