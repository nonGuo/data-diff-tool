"""HTML report generation using Jinja2 templates with inline CSS.

Generates a single self-contained HTML file that can be opened in any browser.
"""

from __future__ import annotations

import os
from datetime import datetime

from jinja2 import Template

from data_diff_tool.config.models import (
    DataCheckResult,
    InventoryTask,
    SkippedTask,
    StructCheckResult,
    TaskResult,
    VerificationTask,
)

_HTML_TEMPLATE = Template(r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Data Diff Report</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; background: #f5f7fa; color: #333; line-height: 1.6; padding: 24px; }
  .container { max-width: 1100px; margin: 0 auto; }
  h1 { font-size: 24px; color: #1a1a2e; margin-bottom: 4px; }
  h2 { font-size: 18px; color: #16213e; margin: 24px 0 12px; padding-bottom: 6px; border-bottom: 2px solid #e0e0e0; }
  h3 { font-size: 15px; color: #0f3460; margin: 16px 0 8px; font-weight: 600; }
  .meta { color: #888; font-size: 13px; margin-bottom: 20px; }
  .summary { display: flex; gap: 16px; margin-bottom: 24px; }
  .summary-card { flex: 1; background: #fff; border-radius: 8px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); text-align: center; }
  .summary-card .count { font-size: 32px; font-weight: 700; }
  .summary-card .label { font-size: 13px; color: #666; margin-top: 4px; }
  .card-passed .count { color: #27ae60; }
  .card-failed .count { color: #e74c3c; }
  .card-skipped .count { color: #95a5a6; }
  .card-total .count { color: #2c3e50; }

  table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 6px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); margin-bottom: 16px; }
  th { background: #f0f2f5; font-size: 13px; color: #555; text-align: left; padding: 10px 14px; font-weight: 600; white-space: nowrap; }
  td { padding: 10px 14px; font-size: 13px; border-top: 1px solid #eee; }
  tr:last-child td { border-bottom: none; }

  .task-section { background: #fff; border-radius: 8px; padding: 20px; margin-bottom: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
  .task-header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .task-title { font-size: 15px; font-weight: 600; color: #1a1a2e; }
  .task-meta { font-size: 12px; color: #888; }
  .task-meta span { margin-right: 16px; }
  .task-meta code { background: #f0f2f5; padding: 1px 5px; border-radius: 3px; font-size: 11px; }

  .badge { display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }
  .badge-pass { background: #d4edda; color: #155724; }
  .badge-fail { background: #f8d7da; color: #721c24; }
  .badge-skip { background: #e9ecef; color: #495057; }

  .row-pass td { background: #fafff8; }
  .row-fail td { background: #fff5f5; }
  .row-skip td { background: #fafafa; }

  .status-ok { color: #27ae60; font-weight: 600; }
  .status-err { color: #e74c3c; font-weight: 600; }

  .section-title { font-size: 14px; font-weight: 600; color: #333; margin-bottom: 10px; display: flex; align-items: center; gap: 8px; }

  .data-stats { display: flex; gap: 12px; margin-bottom: 12px; }
  .data-stat { background: #f8f9fa; border-radius: 6px; padding: 10px 16px; flex: 1; text-align: center; }
  .data-stat .val { font-size: 20px; font-weight: 700; color: #2c3e50; }
  .data-stat .lbl { font-size: 11px; color: #888; margin-top: 2px; }
  .data-stat.warn .val { color: #e67e22; }

  .skipped-table th { background: #fff3cd; }
</style>
</head>
<body>
<div class="container">

<h1>Data Diff Verification Report</h1>
<p class="meta">Generated at: {{ generated_at }} &nbsp;|&nbsp; Total tasks: {{ results|length }}</p>

<div class="summary">
  <div class="summary-card card-total"><div class="count">{{ results|length }}</div><div class="label">Total</div></div>
  <div class="summary-card card-passed"><div class="count">{{ passed_count }}</div><div class="label">Passed</div></div>
  <div class="summary-card card-failed"><div class="count">{{ failed_count }}</div><div class="label">Failed</div></div>
  <div class="summary-card card-skipped"><div class="count">{{ skipped_count }}</div><div class="label">Skipped</div></div>
</div>

<h2>Task Details</h2>
{% for result in results %}
{% if result.task.__class__.__name__ == 'VerificationTask' %}
<div class="task-section">
  <div class="task-header">
    <span class="task-title">{{ result.task.entity.old_fqn }} → {{ result.task.entity.new_fqn }}</span>
    {% if result.status == 'passed' %}
      <span class="badge badge-pass">PASS</span>
    {% elif result.status == 'failed' %}
      <span class="badge badge-fail">FAIL</span>
    {% else %}
      <span class="badge badge-skip">SKIPPED</span>
    {% endif %}
  </div>
  <div class="task-meta">
    <span>Type: <strong>{{ result.task.entity.mapping_type }}</strong></span>
    {% if result.task.primary_keys %}<span>PK: <code>{{ result.task.primary_keys | join(', ') }}</code></span>{% endif %}
    {% if result.task.filter_cond %}<span>Filter: <code>{{ result.task.filter_cond }}</code></span>{% endif %}
    {% if result.elapsed_ms %}<span>Elapsed: <code>{{ result.elapsed_ms }}ms</code></span>{% endif %}
  </div>

  {% if result.struct_check %}
  <h3>Structure Check</h3>
  {% if result.struct_check.compatible %}
    <div class="section-title"><span class="status-ok">✅ Compatible</span></div>
  {% else %}
    <div class="section-title"><span class="status-err">❌ Incompatible</span></div>
  {% endif %}
  <table>
    <thead><tr><th>Column</th><th>Old Type</th><th>New Type</th><th>Nullable</th><th>Status</th></tr></thead>
    <tbody>
    {% for d in result.struct_check.column_diffs %}
    <tr class="{% if d.passed %}row-pass{% else %}row-fail{% endif %}">
      <td><strong>{{ d.column }}</strong></td>
      <td>{{ d.old_type or '-' }}</td>
      <td>{{ d.new_type or '-' }}</td>
      <td>{{ 'Y' if d.new_nullable else 'N' }}</td>
      <td>
        {% if not d.exists_in_old %}
          <span class="status-err">Missing in old table</span>
        {% elif not d.exists_in_new %}
          <span class="status-err">Missing in new table</span>
        {% elif not d.type_compatible %}
          <span class="status-err">{{ d.old_type }} → {{ d.new_type }}</span>
        {% else %}
          <span class="status-ok">{{ d.old_type }} → {{ d.new_type }}</span>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if result.data_check %}
  <h3>Data Consistency Check</h3>
  <div class="data-stats">
    <div class="data-stat"><div class="val">{{ "{:,}".format(result.data_check.total_count) }}</div><div class="lbl">Total Rows</div></div>
    <div class="data-stat {% if result.data_check.old_only_count > 0 %}warn{% endif %}"><div class="val">{{ "{:,}".format(result.data_check.old_only_count) }}</div><div class="lbl">Old-Only</div></div>
    <div class="data-stat {% if result.data_check.new_only_count > 0 %}warn{% endif %}"><div class="val">{{ "{:,}".format(result.data_check.new_only_count) }}</div><div class="lbl">New-Only</div></div>
  </div>
  <table>
    <thead><tr><th>Column</th><th>Diff Count</th><th>Diff Rate</th><th>Status</th></tr></thead>
    <tbody>
    {% for col in result.data_check.column_results %}
    <tr class="{% if col.passed %}row-pass{% else %}row-fail{% endif %}">
      <td><strong>{{ col.column }}</strong></td>
      <td class="{% if col.diff_count > 0 %}status-err{% endif %}">{{ "{:,}".format(col.diff_count) }}</td>
      <td class="{% if col.diff_count > 0 %}status-err{% endif %}">{{ "%.4f"|format(col.diff_rate) }}%</td>
      <td>{% if col.passed %}<span class="status-ok">✅ PASS</span>{% else %}<span class="status-err">❌ FAIL</span>{% endif %}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}

  {% if result.task.skipped_columns %}
  <h3>Skipped Columns (Data Changed)</h3>
  <table>
    <thead><tr><th>Column</th><th>Reason</th></tr></thead>
    <tbody>
    {% for col in result.task.skipped_columns %}
    <tr class="row-skip"><td>{{ col }}</td><td>Data content changed — skipped comparison</td></tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}
</div>

{% elif result.task.__class__.__name__ == 'SkippedTask' %}
<div class="task-section">
  <div class="task-header">
    <span class="task-title">{{ result.task.entity.old_fqn }} → {{ result.task.entity.new_fqn }}</span>
    <span class="badge badge-skip">SKIPPED</span>
  </div>
  <div class="task-meta">
    <span>Type: <strong>{{ result.task.entity.mapping_type }}</strong></span>
    <span>Reason: {{ result.task.reason }}</span>
  </div>
</div>

{% elif result.task.__class__.__name__ == 'InventoryTask' %}
<div class="task-section">
  <div class="task-header">
    <span class="task-title">{{ result.task.entity.old_fqn or '(removed)' }} ↔ {{ result.task.entity.new_fqn or '(new)' }}</span>
    <span class="badge badge-skip">INVENTORY</span>
  </div>
  <div class="task-meta">
    <span>Type: <strong>{{ result.task.entity.mapping_type }}</strong></span>
  </div>
</div>
{% endif %}
{% endfor %}

{% if skipped_tasks %}
<h2>Tasks Requiring Manual Review</h2>
<table class="skipped-table">
  <thead><tr><th>Old Table</th><th>New Table</th><th>Type</th><th>Reason</th></tr></thead>
  <tbody>
  {% for r in skipped_tasks %}
  <tr class="row-skip">
    <td>{{ r.task.entity.old_fqn or '-' }}</td>
    <td>{{ r.task.entity.new_fqn or '-' }}</td>
    <td>{{ r.task.entity.mapping_type }}</td>
    <td>{{ r.task.reason }}</td>
  </tr>
  {% endfor %}
  </tbody>
</table>
{% endif %}

</div>
</body>
</html>
""")


class ReportGenerator:
    """Generates self-contained HTML reports for verification tasks."""

    def __init__(self, output_dir: str) -> None:
        self.output_dir = output_dir

    def generate(self, results: list[TaskResult]) -> str:
        """Generate the full HTML report and return the file path."""
        os.makedirs(self.output_dir, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"report_{timestamp}.html"
        filepath = os.path.join(self.output_dir, filename)

        passed_count = sum(1 for r in results if r.status == "passed")
        failed_count = sum(1 for r in results if r.status == "failed")
        skipped_count = sum(1 for r in results if r.status == "skipped")
        skipped_tasks = [r for r in results if isinstance(r.task, SkippedTask)]

        html = _HTML_TEMPLATE.render(
            results=results,
            generated_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            passed_count=passed_count,
            failed_count=failed_count,
            skipped_count=skipped_count,
            skipped_tasks=skipped_tasks,
        )

        with open(filepath, "w") as f:
            f.write(html)

        return filepath
