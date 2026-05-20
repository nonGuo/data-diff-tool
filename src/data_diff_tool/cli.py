"""CLI entry point for data-diff tool."""

from __future__ import annotations

import logging
import time

import click

from data_diff_tool.config.excel_parser import ExcelParser
from data_diff_tool.config.models import (
    InventoryTask,
    SkippedTask,
    TaskResult,
    VerificationTask,
)
from data_diff_tool.db.connection import DWSConfig, DWSConnection
from data_diff_tool.db.metadata import MetadataQuery
from data_diff_tool.db.sources import SourceConfig
from data_diff_tool.verifier.struct import StructChecker
from data_diff_tool.verifier.data import DataChecker
from data_diff_tool.report.generator import ReportGenerator


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.version_option(version="0.1.0")
def main(verbose: bool) -> None:
    """Data warehouse migration verification tool."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def _extract_old_db(fqn: str) -> str:
    """Extract database name from a FQN like 'db.schema.table'."""
    return fqn.split(".")[0] if fqn else ""


def _run_single_task(
    task: VerificationTask | SkippedTask | InventoryTask,
    connections: dict[str, DWSConnection],
) -> TaskResult:
    """Execute a single verification task using the appropriate connection."""
    start = time.time()

    if isinstance(task, VerificationTask):
        db_name = _extract_old_db(task.entity.old_fqn)
        conn = connections.get(db_name)
        if not conn:
            result = TaskResult(task=task, status="failed", elapsed_ms=0)
            click.echo(f"  ❌ No connection configured for database '{db_name}'")
            return result

        metadata = MetadataQuery(conn)
        struct_checker = StructChecker(metadata)
        data_checker = DataChecker(conn)

        result = TaskResult(task=task)
        try:
            # Structure check
            all_columns = task.identical_columns + task.cast_columns
            struct_result = struct_checker.check(
                task.entity.old_fqn, task.entity.new_fqn, all_columns,
            )
            result.struct_check = struct_result
            compat_icon = "✅ Compatible" if struct_result.compatible else "❌ Incompatible"
            click.echo(f"  Structure: {compat_icon}")
            for diff in struct_result.column_diffs:
                icon = "✅" if diff.passed else "❌"
                click.echo(f"    {icon} {diff.column}: {diff.old_type or 'missing'} → {diff.new_type or 'missing'}")

            # Data check (only if structure is compatible and columns exist)
            if struct_result.compatible and all_columns:
                data_result = data_checker.execute(task)
                result.data_check = data_result
                result.status = "passed" if data_result.column_results and all(c.passed for c in data_result.column_results) else "failed"
                click.echo(f"  Data: {data_result.total_count:,} rows")
                for col in data_result.column_results:
                    icon = "✅" if col.passed else "❌"
                    click.echo(f"    {icon} {col.column}: {col.diff_count:,} diffs ({col.diff_rate:.4f}%)")
                click.echo(f"  Old-only rows: {data_result.old_only_count:,}, New-only rows: {data_result.new_only_count:,}")
            elif not all_columns:
                result.status = "skipped"
                click.echo("  Data: skipped (no columns to check)")
            else:
                result.status = "failed"
                click.echo("  Data: skipped (structure incompatible)")

        except ValueError as e:
            click.echo(f"  ❌ Config error: {e}")
            result.status = "failed"
        except Exception as e:
            click.echo(f"  ❌ Error: {e}")
            result.status = "failed"

        result.elapsed_ms = int((time.time() - start) * 1000)
        return result

    elif isinstance(task, (SkippedTask, InventoryTask)):
        return TaskResult(task=task, status="skipped", elapsed_ms=0)

    return TaskResult(task=task, status="skipped", elapsed_ms=0)


@main.command()
@click.option("--excel", "excel_path", required=True, help="Path to the mapping Excel file")
@click.option("--config", default=None, help="Path to DWS sources YAML config file")
@click.option("--dsn", default=None, help="Database DSN string (e.g. postgresql://user:pass@host:port/dbname)")
@click.option("--host", default=None, help="DWS host address")
@click.option("--port", default=None, type=int, help="DWS port")
@click.option("--database", default=None, help="DWS database name")
@click.option("--user", default=None, help="DWS username")
@click.option("--password", default=None, help="DWS password")
@click.option("--primary-keys", default=None, help="Global fallback: comma-separated primary key column names")
@click.option("--filter", "filter_cond", default=None, help="Global fallback: WHERE filter condition for data comparison")
@click.option("--output-dir", default="./reports", show_default=True, help="Output directory for reports")
def run(
    excel_path: str,
    config: str | None,
    dsn: str | None,
    host: str | None,
    port: int | None,
    database: str | None,
    user: str | None,
    password: str | None,
    primary_keys: str | None,
    filter_cond: str | None,
    output_dir: str,
) -> None:
    """Execute verification tasks against DWS."""
    # ── Step 1: Parse Excel ──────────────────────────────────────
    click.echo(f"Parsing Excel file: {excel_path}")
    parser = ExcelParser(excel_path)

    pk_list = [k.strip() for k in primary_keys.split(",")] if primary_keys else []
    tasks = parser.parse(primary_keys=pk_list, filter_cond=filter_cond)

    verify_tasks = [t for t in tasks if isinstance(t, VerificationTask)]
    skipped = [t for t in tasks if isinstance(t, SkippedTask)]
    inventory = [t for t in tasks if isinstance(t, InventoryTask)]

    click.echo(f"Tasks: {len(verify_tasks)} to verify, {len(skipped)} skipped, {len(inventory)} inventory")

    # ── Step 2: Establish connections ────────────────────────────
    connections: dict[str, DWSConnection] = {}  # keyed by old db name

    if verify_tasks and config:
        source_cfg = SourceConfig(config)
        # Collect unique old db names
        old_fqns = list({t.entity.old_fqn for t in verify_tasks if t.entity.old_fqn})
        sources = source_cfg.get_unique_sources(old_fqns)
        for db_name, source in sources.items():
            cfg = DWSConfig.from_source(source, dbname=db_name)
            click.echo(f"Connecting to [{db_name}]: {cfg.masked_repr()}")
            conn = DWSConnection(cfg)
            conn.connect()
            connections[db_name] = conn

    elif verify_tasks:
        # Fallback: CLI params / env vars (single connection for all tasks)
        cfg = DWSConfig.from_kwargs(dsn=dsn, host=host, port=port, dbname=database, user=user, password=password)
        click.echo(f"Connecting to DWS: {cfg.masked_repr()}")
        conn = DWSConnection(cfg)
        conn.connect()
        # Route all tasks to this single connection
        for task in verify_tasks:
            db_name = _extract_old_db(task.entity.old_fqn)
            connections[db_name] = conn

    # ── Step 3: Run verification ─────────────────────────────────
    results: list[TaskResult] = []

    for task in tasks:
        if isinstance(task, VerificationTask):
            click.echo(f"\n{'='*60}")
            click.echo(f"Checking: {task.entity.old_fqn} → {task.entity.new_fqn}")

        result = _run_single_task(task, connections)
        results.append(result)

    # ── Step 4: Generate report ──────────────────────────────────
    click.echo(f"\nGenerating reports to: {output_dir}")
    generator = ReportGenerator(output_dir=output_dir)
    report_path = generator.generate(results)
    click.echo(f"Report saved: {report_path}")

    # Cleanup
    for conn in connections.values():
        conn.close()

    # Summary
    click.echo(f"\n{'='*60}")
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    skipped_count = sum(1 for r in results if r.status == "skipped")
    click.echo(f"Summary: ✅ {passed} passed  |  ❌ {failed} failed  |  ⏭️ {skipped_count} skipped")
    click.echo("Done.")


@main.command()
@click.option("--excel", "excel_path", required=True, help="Path to the mapping Excel file")
@click.option("--primary-keys", default=None, help="Global fallback: comma-separated primary key column names")
@click.option("--filter", "filter_cond", default=None, help="Global fallback: WHERE filter condition for data comparison")
def dry_run(excel_path: str, primary_keys: str | None, filter_cond: str | None) -> None:
    """Parse Excel and print task list without connecting to DWS."""
    click.echo(f"Parsing Excel file: {excel_path}")
    parser = ExcelParser(excel_path)

    pk_list = [k.strip() for k in primary_keys.split(",")] if primary_keys else []
    tasks = parser.parse(primary_keys=pk_list, filter_cond=filter_cond)

    click.echo(f"\nFound {len(tasks)} task(s):\n")

    for i, task in enumerate(tasks, 1):
        if isinstance(task, VerificationTask):
            pk_info = f" pk={','.join(task.primary_keys)}" if task.primary_keys else " pk=(none)"
            filter_info = f" filter='{task.filter_cond}'" if task.filter_cond else ""
            click.echo(f"  {i}. {task.entity.old_fqn} → {task.entity.new_fqn}{pk_info}{filter_info}")
            if task.identical_columns:
                click.echo(f"     identical: {', '.join(task.identical_columns)}")
            if task.cast_columns:
                click.echo(f"     cast: {', '.join(task.cast_columns)}")
            if task.skipped_columns:
                click.echo(f"     skipped: {', '.join(task.skipped_columns)}")
        elif isinstance(task, SkippedTask):
            click.echo(f"  {i}. {task.entity.old_fqn} → {task.entity.new_fqn} ({task.entity.mapping_type}) [SKIPPED: {task.reason}]")
        elif isinstance(task, InventoryTask):
            label = task.entity.old_fqn or "(removed)"
            new_label = task.entity.new_fqn or "(none)"
            click.echo(f"  {i}. {label} → {new_label} ({task.entity.mapping_type}) [INVENTORY]")

    click.echo("\nDry run complete.")


if __name__ == "__main__":
    main()
