from __future__ import annotations

"""wf2wf.prompt – lightweight interactive confirmation helper (Phase 12.2).

Uses click.confirm when click is available; falls back to built-in input().
Honours environment variable **WF2WF_NO_PROMPT=1** to force head-less mode
(e.g. CI).  The helper returns a boolean and caches affirmative "always"
answers for the process lifetime so users can choose "always" to skip further
prompts in the same execution.
"""

from typing import Dict, Union
import os

__all__ = ["ask"]

# Cache of question → bool so repeated prompts can be skipped when user chose
# "always" (y-a / n-a).  We only need per-process memory – no persistence.
_cache: Dict[str, bool] = {}

# Whether prompts are enabled for this run (set by CLI). Defaults to False.
_interactive: bool = False


def set_interactive(flag: bool) -> None:
    """Enable/disable prompting globally for this process."""
    global _interactive  # noqa: PLW0603 – module-level mutable state
    _interactive = flag


def interactive() -> bool:
    """Return current interactive mode (env var may override)."""
    if _no_prompt():
        return False
    return _interactive


def _no_prompt() -> bool:
    return os.getenv("WF2WF_NO_PROMPT", "0") in ("1", "true", "yes", "on")


def ask(question: str, *, default: Union[bool, None] = None) -> bool:
    """Ask *question* on the terminal, return bool.

    • When *default* is None the user **must** answer explicitly.
    • If the same *question* has been answered with the special choice
      "always" the cached answer is returned automatically on subsequent calls.
    """

    # Head-less or non-interactive – return default or False
    if not interactive():
        return bool(default)

    if question in _cache:
        return _cache[question]

    try:
        import click

        # Build prompt text – emulate git-style choices
        prompt_txt = question.strip() + " (y)es/(n)o/(a)lways/(q)uit: "
        while True:
            ans = click.prompt(
                prompt_txt,
                type=str,
                default=("y" if default else "n") if default is not None else None,
            )
            ans = ans.lower().strip()
            if ans in ("y", "yes"):
                return True
            if ans in ("n", "no"):
                return False
            if ans in ("a", "always"):
                _cache[question] = True
                return True
            if ans in ("q", "quit", "abort"):
                raise click.Abort()
            click.echo("Please enter y, n, a, or q.")
    except ImportError:
        # Fallback minimal prompt
        prompt_txt = question.strip() + " [y/N]: "
        ans = input(prompt_txt)
        return ans.lower().startswith("y")
