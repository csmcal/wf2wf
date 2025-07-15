from __future__ import annotations

"""wf2wf.report – Markdown report generation for conversions.

This module provides functionality to generate human-readable reports
documenting workflow conversions, including:

• Source and target workflow information
• Conversion actions performed
• Information losses and their handling
• Generated artifacts and next steps
• Optional HTML rendering

The reports are designed to be informative for both technical users
and workflow authors who need to understand what changed during conversion.
"""

from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Union
import textwrap
import contextvars
import json

__all__ = [
    "generate",
    "start_collection",
    "record_action",
    "record_loss",
]


def _md_table(rows: List[List[str]]) -> str:
    """Return GitHub-flavoured markdown table from *rows* (including header row)."""
    if not rows:
        return ""
    col_count = len(rows[0])
    widths = [max(len(r[i]) for r in rows) for i in range(col_count)]
    lines = []
    header, *body = rows

    def _fmt(row):
        return "| " + " | ".join(cell.ljust(w) for cell, w in zip(row, widths)) + " |"

    lines.append(_fmt(header))
    lines.append("| " + " | ".join("-" * w for w in widths) + " |")
    lines += [_fmt(r) for r in body]
    return "\n".join(lines)


def generate(
    md_path: Path,
    *,
    src_path: Path,
    dst_path: Path,
    wf_before: "Any" = None,  # noqa: ANN401 – keep import-free
    wf_after: "Any" = None,
    losses: Optional[List[Dict[str, Any]]] = None,
    actions: Optional[List[str]] = None,
    artefacts: Optional[List[Path]] = None,
    next_steps: Optional[List[str]] = None,
    extra_notes: str = "",
    html_path: Union[Path, bool, None] = None,
) -> Path:
    """Write a conversion report to *md_path* and return it.

    Parameters
    ----------
    md_path
        Where to write the report.
    src_path / dst_path
        User-visible paths for provenance section.
    wf_before / wf_after
        Optional Workflow objects for statistics (task count etc.).
    losses
        Parsed loss entries (list of dicts) – may be empty.
    actions
        Free-form bullet list of noteworthy actions.
    artefacts
        List of paths to generated artefacts.
    next_steps
        List of next steps to be taken.
    extra_notes
        Additional Markdown appended at the end.
    html_path
        Optional path to generate HTML version of the report.
    """

    losses = losses or []
    actions = actions or []
    artefacts = artefacts or []
    next_steps = next_steps or []

    now = datetime.now(timezone.utc).isoformat()

    md_content = f"# wf2wf Conversion Report\n\nGenerated: {now}\n"

    summary_lines = [
        f"**Source**: `{src_path}`",
        f"**Target**: `{dst_path}`",
    ]
    if wf_before and getattr(wf_before, "name", None):
        summary_lines.append(
            f"**Workflow**: {wf_before.name} (v{getattr(wf_before,'version','?')})"
        )
    md_content += "\n".join(summary_lines) + "\n\n---\n\n"

    # Actions section
    if actions:
        md_content += (
            "## Actions Performed\n\n" + "\n".join(f"* {a}" for a in actions) + "\n\n"
        )

    # Losses
    if losses:
        md_content += "## Information Loss\n\n"
        rows = [["Path", "Field", "Reason"]]
        for e in losses:
            rows.append(
                [e.get("json_pointer", "?"), e.get("field", ""), e.get("reason", "")]
            )
        md_content += _md_table(rows) + "\n\n"
    else:
        md_content += "## Information Loss\n\n_None_\n\n"

    # Stats
    if wf_after is not None:
        md_content += "## Workflow Statistics\n\n"
        md_content += textwrap.dedent(f"""
        * Tasks: {len(wf_after.tasks)}
        * Edges: {len(wf_after.edges)}
        """)
        md_content += "\n"

    # Configuration Analysis
    if wf_after is not None:
        md_content += "## Configuration Analysis\n\n"
        
        # Analyze resource specifications
        tasks_without_memory = []
        tasks_without_disk = []
        tasks_without_containers = []
        tasks_without_retry = []
        auto_transfer_files = []
        
        for task in wf_after.tasks.values():
            if hasattr(task, 'mem_mb') and task.mem_mb.get_value_for('shared_filesystem') == 0:
                tasks_without_memory.append(task.id)
            if hasattr(task, 'disk_mb') and task.disk_mb.get_value_for('shared_filesystem') == 0:
                tasks_without_disk.append(task.id)
            # Get environment-specific values for shared_filesystem environment
            container = task.container.get_value_for('shared_filesystem')
            conda = task.conda.get_value_for('shared_filesystem')
            if not container and not conda:
                tasks_without_containers.append(task.id)
            if task.retry_count.get_value_for('shared_filesystem') == 0:
                tasks_without_retry.append(task.id)
            
            # Check file transfer modes
            for param in task.inputs + task.outputs:
                if hasattr(param, 'transfer_mode') and param.transfer_mode == "auto":
                    auto_transfer_files.append(f"{task.id}.{param.id}")
        
        config_issues = []
        if tasks_without_memory:
            config_issues.append(f"**Memory**: {len(tasks_without_memory)} tasks without explicit memory requirements")
        if tasks_without_disk:
            config_issues.append(f"**Disk**: {len(tasks_without_disk)} tasks without explicit disk requirements")
        if tasks_without_containers:
            config_issues.append(f"**Containers**: {len(tasks_without_containers)} tasks without container/conda specifications")
        if tasks_without_retry:
            config_issues.append(f"**Error Handling**: {len(tasks_without_retry)} tasks without retry specifications")
        if auto_transfer_files:
            config_issues.append(f"**File Transfer**: {len(auto_transfer_files)} files with auto-detected transfer modes")
        
        if config_issues:
            md_content += "### Potential Issues for Distributed Computing\n\n"
            for issue in config_issues:
                md_content += f"* {issue}\n"
            md_content += "\n"
            
            md_content += textwrap.dedent("""
            **Recommendations:**
            * Add explicit resource requirements for all tasks
            * Specify container images or conda environments for environment isolation
            * Configure retry policies for fault tolerance
            * Review file transfer modes for distributed execution
            """)
        else:
            md_content += "### Configuration Status\n\n✅ All tasks have appropriate configurations for distributed computing.\n\n"

    # Artefacts
    if artefacts:
        md_content += "## Generated Artefacts\n\n"
        rows = [["File", "Size (bytes)"]]
        for p in artefacts:
            try:
                size = str(p.stat().st_size)
            except FileNotFoundError:
                size = "-"
            rows.append([p.name, size])
        md_content += _md_table(rows) + "\n\n"

    if extra_notes:
        md_content += "## Notes\n\n" + extra_notes + "\n"

    # Next steps (call-to-action)
    if next_steps:
        md_content += (
            "## Next Steps\n\n" + "\n".join(f"* {step}" for step in next_steps) + "\n"
        )

    # Inline diff – show when IR mutated
    if wf_before is not None and wf_after is not None and wf_before != wf_after:
        try:
            import dataclasses
            import json
            import difflib

            before_json = json.dumps(
                dataclasses.asdict(wf_before), sort_keys=True, indent=2
            )
            after_json = json.dumps(
                dataclasses.asdict(wf_after), sort_keys=True, indent=2
            )

            diff_lines = list(
                difflib.unified_diff(
                    before_json.splitlines(),
                    after_json.splitlines(),
                    fromfile="before",
                    tofile="after",
                    lineterm="",
                )
            )

            max_lines = 400
            if len(diff_lines) > max_lines:
                diff_lines = diff_lines[:max_lines] + ["... (truncated)"]

            md_content += (
                "\n## IR Diff (truncated)\n\n```diff\n"
                + "\n".join(diff_lines)
                + "\n```\n"
            )
        except Exception:
            pass

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content)

    # Optionally render HTML (requires python-markdown)
    if html_path is not None:
        # Determine output path
        if isinstance(html_path, bool):
            html_out = md_path.with_suffix(".html")
        else:
            html_out = Path(html_path)

        try:
            import markdown as _md_lib  # type: ignore

            html_content = _md_lib.markdown(
                md_content, extensions=["tables", "fenced_code"]
            )
        except ImportError:
            import html as _html

            html_body = _html.escape(md_content)
            html_content = f"<pre>{html_body}</pre>"

        html_out.parent.mkdir(parents=True, exist_ok=True)
        html_out.write_text(html_content)

    return md_path


# ------------------------------------------------------------------
# Hook API
# ------------------------------------------------------------------


class _ReportContext:
    """Per-conversion collector for actions & artefacts."""

    def __init__(self):
        self.actions: list[str] = []
        self.artefacts: list[Path] = []

    # fluent helpers
    def add_action(self, msg: str):
        self.actions.append(msg)

    def add_artefact(self, p: Path):
        self.artefacts.append(p)


_ctx_var: contextvars.ContextVar[Optional[_ReportContext]] = contextvars.ContextVar(
    "wf2wf_report_ctx", default=None
)


def start_collection() -> None:
    """Begin a new report-collection context."""
    _ctx_var.set(_ReportContext())


def end_collection() -> tuple[list[str], list[Path]]:
    """Finish collection and return (actions, artefacts)."""
    ctx = _ctx_var.get()
    _ctx_var.set(None)
    if ctx is None:
        return [], []
    return ctx.actions, ctx.artefacts


def add_action(msg: str):
    ctx = _ctx_var.get()
    if ctx is not None:
        ctx.add_action(msg)


def add_artefact(p: Path):
    ctx = _ctx_var.get()
    if ctx is not None:
        ctx.add_artefact(Path(p))
