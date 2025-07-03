"""wf2wf.expression – tiny sandboxed JavaScript expression evaluator.

Only a subset of CWL's JavaScript expression language is needed for conditional
execution (`when`) and simple value transformations.  This module provides a
light-weight wrapper around *js2py* if available, otherwise falls back to a very
restricted *eval* substitute that rejects anything but literals and basic
operators.
"""

from __future__ import annotations

from typing import Any, Dict, Union, Optional
import ast
import signal
import contextlib
import importlib.util

# Check if js2py is available without importing it
_HAS_JS2PY = importlib.util.find_spec("js2py") is not None

__all__ = [
    "evaluate",
]


class ExpressionError(RuntimeError):
    """Raised when a workflow expression cannot be evaluated."""


class ExpressionTimeout(ExpressionError):
    """Raised when expression evaluation exceeds wall-time limit."""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_MAX_LEN = 10000  # hard limit on expression length


def _strip_wrappers(expr: str) -> str:
    """Remove CWL wrapper syntax $() or ${} if present."""
    expr = expr.strip()
    if (expr.startswith("$(") and expr.endswith(")")) or (
        expr.startswith("${") and expr.endswith("}")
    ):
        return expr[2:-1].strip()
    return expr


@contextlib.contextmanager
def _timeout(seconds: float):
    """Context manager raising ExpressionTimeout if block lasts > *seconds*."""

    if seconds <= 0:
        yield
        return

    # Windows doesn't have SIGALRM, so we skip timeout on Windows
    if not hasattr(signal, 'SIGALRM'):
        yield
        return

    def _handler(signum, frame):  # noqa: D401 – local handler
        raise ExpressionTimeout("expression evaluation timed out")

    old_handler = signal.signal(signal.SIGALRM, _handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)


# ---------------------------------------------------------------------------
# Public helper
# ---------------------------------------------------------------------------


def evaluate(
    expr: str, context: Optional[Dict[str, Any]] = None, *, timeout_s: float = 0.1
) -> Any:
    """Evaluate a CWL/JS expression with the provided *context*.

    If *js2py* is installed we run the snippet in a sandboxed JS VM.  Otherwise
    we fall back to a Python literal evaluator that can handle numbers,
    booleans, arithmetic and logic operators, attribute lookup on the provided
    *context* and nothing else.

    The goal is *safety* – we must not allow arbitrary file access or network
    calls from untrusted workflow content.
    """

    # Basic sanity checks & normalisation
    if len(expr) > _MAX_LEN:
        raise ExpressionError("expression too large")

    expr = _strip_wrappers(expr)

    context = context or {}

    if _HAS_JS2PY:
        try:
            import json
            import js2py  # re-import for mypy typing

            with _timeout(timeout_s):
                js_ctx = js2py.EvalJs({})
                js_ctx.execute(f"var $context = {json.dumps(context)};")
                js_ctx.execute("function _wf2wf_ctx() { return $context; }")
                return js_ctx.eval(expr)
        except ExpressionTimeout:
            raise
        except js2py.internals.simplex.JsException as exc:  # type: ignore[attr-defined]
            raise ExpressionError(str(exc)) from None

    # ------------------------------------------------------------------
    # Fallback: tiny safe subset evaluator using Python AST with timeout
    # ------------------------------------------------------------------
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:  # pragma: no cover
        raise ExpressionError(str(exc))

    allowed_nodes = (
        ast.Expression,
        ast.Constant,
        ast.BinOp,
        ast.UnaryOp,
        ast.BoolOp,
        ast.Compare,
        ast.Name,
        ast.Load,
        ast.And,
        ast.Or,
        ast.Not,
        ast.Add,
        ast.Sub,
        ast.Mult,
        ast.Div,
        ast.Mod,
        ast.Pow,
        ast.Eq,
        ast.NotEq,
        ast.Gt,
        ast.GtE,
        ast.Lt,
        ast.LtE,
        ast.Attribute,
        ast.Subscript,
        ast.Index,
        ast.List,
        ast.Tuple,
    )

    for node in ast.walk(tree):
        if not isinstance(node, allowed_nodes):
            raise ExpressionError(
                f"Disallowed expression element: {type(node).__name__}"
            )

    # Compile and evaluate with restricted namespace
    code = compile(tree, "<expr>", mode="eval")
    safe_globals: Dict[str, Any] = {"__builtins__": {}}

    with _timeout(timeout_s):
        return eval(code, safe_globals, context)
