from __future__ import annotations

"""wf2wf.report – simple Markdown conversion report generator (Phase 12.1)"""

from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import textwrap
import json
import contextvars

__all__ = ["generate"]


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
    losses: List[Dict[str, Any]] | None = None,
    actions: List[str] | None = None,
    artefacts: List[Path] | None = None,
    next_steps: list[str] | None = None,
    extra_notes: str = "",
    html_path: Path | bool | None = None,
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
        summary_lines.append(f"**Workflow**: {wf_before.name} (v{getattr(wf_before,'version','?')})")
    md_content += "\n".join(summary_lines) + "\n\n---\n\n"

    # Actions section
    if actions:
        md_content += "## Actions Performed\n\n" + "\n".join(f"* {a}" for a in actions) + "\n\n"

    # Losses
    if losses:
        md_content += "## Information Loss\n\n"
        rows = [["Path", "Field", "Reason"]]
        for e in losses:
            rows.append([e.get("json_pointer", "?"), e.get("field", ""), e.get("reason", "")])
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
        md_content += "## Next Steps\n\n" + "\n".join(f"* {step}" for step in next_steps) + "\n"

    # Inline diff – show when IR mutated
    if wf_before is not None and wf_after is not None and wf_before != wf_after:
        try:
            import dataclasses, json, difflib

            before_json = json.dumps(dataclasses.asdict(wf_before), sort_keys=True, indent=2)
            after_json = json.dumps(dataclasses.asdict(wf_after), sort_keys=True, indent=2)

            diff_lines = list(difflib.unified_diff(
                before_json.splitlines(),
                after_json.splitlines(),
                fromfile="before", tofile="after", lineterm=""
            ))

            max_lines = 400
            if len(diff_lines) > max_lines:
                diff_lines = diff_lines[:max_lines] + ["... (truncated)"]

            md_content += "\n## IR Diff (truncated)\n\n```diff\n" + "\n".join(diff_lines) + "\n```\n"
        except Exception:
            pass

    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(md_content)

    # Optionally render HTML (requires python-markdown)
    if html_path is not None:
        # Determine output path
        if isinstance(html_path, bool):
            html_out = md_path.with_suffix('.html')
        else:
            html_out = Path(html_path)

        try:
            import markdown as _md_lib  # type: ignore

            html_content = _md_lib.markdown(md_content, extensions=["tables", "fenced_code"])
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


_ctx_var: contextvars.ContextVar[Optional[_ReportContext]] = contextvars.ContextVar("wf2wf_report_ctx", default=None)


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