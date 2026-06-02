"""Streamlit Web UI for Data Diff Tool.

Provides a step-by-step wizard: upload Excel → configure sources → preview tasks → run → view report.
"""

import logging
import os
import tempfile
from contextlib import contextmanager

import streamlit as st
import yaml

from data_diff_tool.config.excel_parser import ExcelParser
from data_diff_tool.config.models import (
    InventoryTask,
    SkippedTask,
    TaskResult,
    VerificationTask,
)
from data_diff_tool.db.connection import DWSConfig, DWSConnection
from data_diff_tool.db.sources import SourceConfig
from data_diff_tool.verifier.data import DataChecker
from data_diff_tool.verifier.struct import StructChecker
from data_diff_tool.report.generator import ReportGenerator

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Data Diff Tool",
    page_icon="🔍",
    layout="wide",
)


# ── Session state helpers ──────────────────────────────────────────

def init_session_state():
    defaults = {
        "step": 1,
        "excel_file": None,
        "tasks": None,
        "source_cfg": None,
        "fallback_pk": "",
        "fallback_filter": "",
        "results": None,
        "report_path": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def reset_all():
    for k in ["step", "excel_file", "tasks", "source_cfg", "results", "report_path"]:
        st.session_state[k] = None if k != "step" else 1


# ── Sidebar: Data Source Configuration ─────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.header("数据源配置")

        cfg_mode = st.radio(
            "配置方式",
            ["文本编辑", "上传 YAML 文件"],
            horizontal=True,
            label_visibility="collapsed",
        )

        yaml_text = ""

        if cfg_mode == "文本编辑":
            yaml_text = st.text_area(
                "dws_sources.yaml",
                height=280,
                placeholder="""sources:
  edw:
    host: 10.0.1.100
    port: 8000
    database: edw
    user: admin
    password: secret""",
            )
        else:
            uploaded = st.file_uploader("上传 YAML 配置文件", type=["yaml", "yml"])
            if uploaded:
                yaml_text = uploaded.getvalue().decode("utf-8")

        # Parse and validate
        source_cfg: SourceConfig | None = None
        if yaml_text.strip():
            try:
                data = yaml.safe_load(yaml_text)
                if not isinstance(data, dict) or "sources" not in data:
                    st.error("YAML 需包含 `sources` 键")
                else:
                    # Write to temp file for SourceConfig
                    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False)
                    tmp.write(yaml_text)
                    tmp.close()
                    source_cfg = SourceConfig(tmp.name)
                    st.success(f"已加载 {len(source_cfg.source_names)} 个数据源")
                    for name in source_cfg.source_names:
                        src = source_cfg.get_source(name)
                        st.caption(f"`{name}` → {src.host}:{src.port}/{src.database or name}")
                    os.unlink(tmp.name)
            except yaml.YAMLError as e:
                st.error(f"YAML 解析失败: {e}")
            except Exception as e:
                st.error(f"配置错误: {e}")

        st.session_state["source_cfg"] = source_cfg

        st.divider()
        st.header("全局设置")
        st.session_state["fallback_pk"] = st.text_input(
            "Fallback 主键（逗号分隔）",
            value=st.session_state.get("fallback_pk", ""),
        )
        st.session_state["fallback_filter"] = st.text_input(
            "Fallback 过滤条件",
            value=st.session_state.get("fallback_filter", ""),
        )


# ── Step indicators ────────────────────────────────────────────────

STEP_LABELS = ["上传文件", "预览任务", "执行校验", "查看报告"]


def render_step_indicator(current: int):
    cols = st.columns(4)
    for i, label in enumerate(STEP_LABELS, 1):
        with cols[i - 1]:
            if i < current:
                st.markdown(f"<div style='text-align:center;color:#27ae60;font-weight:600'>✓ {label}</div>", unsafe_allow_html=True)
            elif i == current:
                st.markdown(f"<div style='text-align:center;color:#2c3e50;font-weight:700;font-size:16px'>● {label}</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align:center;color:#bbb'>{label}</div>", unsafe_allow_html=True)


# ── Step 1: Upload Excel ───────────────────────────────────────────

def render_step_1():
    st.subheader("上传 Mapping Excel 文件")
    st.caption("Excel 需包含「实体级mapping」「属性级mapping」两个页签，可选「抽样校验配置」页签。")

    uploaded = st.file_uploader(
        "选择 .xlsx 文件",
        type=["xlsx"],
        label_visibility="collapsed",
    )

    if uploaded:
        st.session_state["excel_file"] = uploaded.getvalue()
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            tmp.write(st.session_state["excel_file"])
            tmp.close()

            pk_list = [k.strip() for k in st.session_state["fallback_pk"].split(",") if k.strip()] if st.session_state.get("fallback_pk") else []
            fcond = st.session_state.get("fallback_filter") or None

            parser = ExcelParser(tmp.name)
            tasks = parser.parse(primary_keys=pk_list, filter_cond=fcond)

            st.session_state["tasks"] = tasks
            os.unlink(tmp.name)

            verify_count = sum(1 for t in tasks if isinstance(t, VerificationTask))
            skip_count = sum(1 for t in tasks if isinstance(t, SkippedTask))
            inv_count = sum(1 for t in tasks if isinstance(t, InventoryTask))

            st.success(f"解析成功！共 {len(tasks)} 个任务：{verify_count} 待校验，{skip_count} 跳过，{inv_count} 清单")
            st.session_state["step"] = 2
            st.rerun()

        except Exception as e:
            st.error(f"Excel 解析失败: {e}")
            if os.path.exists(tmp.name):
                os.unlink(tmp.name)


# ── Step 2: Preview Tasks ──────────────────────────────────────────

def render_step_2():
    st.subheader("预览任务列表")

    tasks = st.session_state["tasks"]
    if not tasks:
        st.warning("无任务，请返回 Step 1 重新上传")
        return

    # Filter
    filter_type = st.radio("筛选", ["全部", "待校验 (1:1)", "需人工审核", "仅清单"], horizontal=True)

    filtered = []
    for t in tasks:
        if filter_type == "全部":
            filtered.append(t)
        elif filter_type == "待校验 (1:1)" and isinstance(t, VerificationTask):
            filtered.append(t)
        elif filter_type == "需人工审核" and isinstance(t, SkippedTask):
            filtered.append(t)
        elif filter_type == "仅清单" and isinstance(t, InventoryTask):
            filtered.append(t)

    # Table
    rows = []
    for t in filtered:
        if isinstance(t, VerificationTask):
            cols = len(t.identical_columns) + len(t.cast_columns)
            rows.append({
                "旧表": t.entity.old_fqn,
                "新表": t.entity.new_fqn,
                "类型": t.entity.mapping_type,
                "主键": ", ".join(t.primary_keys) or "(未配置)",
                "过滤条件": t.filter_cond or "(无)",
                "校验列数": cols,
            })
        elif isinstance(t, SkippedTask):
            rows.append({
                "旧表": t.entity.old_fqn,
                "新表": t.entity.new_fqn,
                "类型": t.entity.mapping_type,
                "主键": "—",
                "过滤条件": "—",
                "校验列数": "—",
            })
        elif isinstance(t, InventoryTask):
            rows.append({
                "旧表": t.entity.old_fqn or "(已下线)",
                "新表": t.entity.new_fqn or "(新增)",
                "类型": t.entity.mapping_type,
                "主键": "—",
                "过滤条件": "—",
                "校验列数": "—",
            })

    st.dataframe(rows, use_container_width=True, hide_index=True)

    # Navigation
    col_back, col_next = st.columns(2)
    with col_back:
        if st.button("← 返回修改"):
            st.session_state["step"] = 1
            st.rerun()
    with col_next:
        verify_count = sum(1 for t in tasks if isinstance(t, VerificationTask))
        if verify_count == 0:
            st.info("没有可自动校验的 1:1 任务")
        else:
            if st.button("开始校验 →", type="primary"):
                if not st.session_state.get("source_cfg"):
                    st.warning("请先在侧边栏配置数据源")
                else:
                    st.session_state["step"] = 3
                    st.session_state["results"] = None
                    st.session_state["report_path"] = None
                    st.rerun()


# ── Step 3: Execute Verification ───────────────────────────────────

def render_step_3():
    st.subheader("执行校验")

    tasks = st.session_state["tasks"]
    source_cfg: SourceConfig | None = st.session_state.get("source_cfg")

    verify_tasks = [t for t in tasks if isinstance(t, VerificationTask)]
    other_tasks = [t for t in tasks if not isinstance(t, VerificationTask)]

    # Build connection map
    connections: dict[str, DWSConnection] = {}
    db_names = set()
    for t in verify_tasks:
        db_names.add(t.entity.old_fqn.split(".")[0] if t.entity.old_fqn else "")

    try:
        for db_name in db_names:
            if db_name:
                source = source_cfg.get_source(db_name)
                cfg = DWSConfig.from_source(source, dbname=source.database or db_name)
                conn = DWSConnection(cfg)
                conn.connect()
                connections[db_name] = conn
    except Exception as e:
        st.error(f"数据库连接失败: {e}")
        return

    # Run tasks
    progress_bar = st.progress(0)
    log_container = st.container()
    results: list[TaskResult] = []

    total = len(tasks)
    done = 0

    with log_container:
        for task in tasks:
            done += 1
            progress_bar.progress(done / total)

            if isinstance(task, VerificationTask):
                db_name = task.entity.old_fqn.split(".")[0]
                conn = connections.get(db_name)
                st.markdown(f"**校验** `{task.entity.old_fqn}` → `{task.entity.new_fqn}`")

                result = TaskResult(task=task)
                import time
                start = time.time()

                try:
                    metadata = None
                    if conn:
                        from data_diff_tool.db.metadata import MetadataQuery
                        metadata = MetadataQuery(conn)

                    if metadata:
                        struct_checker = StructChecker(metadata)
                        all_columns = task.identical_columns + task.cast_columns
                        struct_result = struct_checker.check(task.entity.old_fqn, task.entity.new_fqn, all_columns)
                        result.struct_check = struct_result

                        status_icon = "✅" if struct_result.compatible else "❌"
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;结构校验: {status_icon}")

                        if struct_result.compatible and all_columns:
                            data_checker = DataChecker(conn)
                            data_result = data_checker.execute(task)
                            result.data_check = data_result
                            result.status = "passed" if all(c.passed for c in data_result.column_results) else "failed"
                            status_icon = "✅" if result.status == "passed" else "❌"
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;数据校验: {status_icon} 共 {data_result.total_count:,} 行")
                        elif not all_columns:
                            result.status = "skipped"
                            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;数据校验: ⏭️ 跳过（无校验列）")
                        else:
                            result.status = "failed"
                            st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;数据校验: ⏭️ 跳过（结构不兼容）")
                    else:
                        result.status = "failed"
                        st.markdown("&nbsp;&nbsp;&nbsp;&nbsp;❌ 无可用数据库连接")

                except Exception as e:
                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;❌ 错误: `{e}`")
                    result.status = "failed"

                result.elapsed_ms = int((time.time() - start) * 1000)
                results.append(result)

            else:
                results.append(TaskResult(task=task, status="skipped", elapsed_ms=0))

    progress_bar.progress(1.0)

    # Summary
    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    skipped = sum(1 for r in results if r.status == "skipped")

    cols = st.columns(3)
    cols[0].metric("Passed", passed)
    cols[1].metric("Failed", failed)
    cols[2].metric("Skipped", skipped)

    # Store results and generate report
    st.session_state["results"] = results
    output_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "reports")
    generator = ReportGenerator(output_dir=output_dir)
    report_path = generator.generate(results)
    st.session_state["report_path"] = report_path

    # Close connections
    for conn in connections.values():
        conn.close()

    if st.button("查看报告 →", type="primary"):
        st.session_state["step"] = 4
        st.rerun()


# ── Step 4: View Report ────────────────────────────────────────────

def render_step_4():
    st.subheader("查看报告")

    report_path = st.session_state.get("report_path")
    if not report_path or not os.path.exists(report_path):
        st.error("报告文件未生成，请先执行校验")
        return

    # Download button
    with open(report_path, "rb") as f:
        st.download_button(
            label="下载 HTML 报告",
            data=f.read(),
            file_name=os.path.basename(report_path),
            mime="text/html",
        )

    st.divider()
    st.subheader("报告预览")
    with open(report_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    st.components.v1.html(html_content, height=900, scrolling=True)

    st.divider()
    if st.button("🔄 重新开始"):
        reset_all()
        st.rerun()


# ── Main ───────────────────────────────────────────────────────────

def main():
    init_session_state()
    render_sidebar()

    st.title("🔍 Data Diff Tool")
    render_step_indicator(st.session_state["step"])
    st.divider()

    step = st.session_state["step"]
    if step == 1:
        render_step_1()
    elif step == 2:
        render_step_2()
    elif step == 3:
        render_step_3()
    elif step == 4:
        render_step_4()


if __name__ == "__main__":
    main()
