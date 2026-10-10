"""Run-File payload builder — the `colab run script.py` contract, locally.

Upstream's `colab_cli/commands/run.py` reads the file, strips the shebang, and
prepends a short prelude before sending the whole body as one ``execute_code``
call. This module reproduces that shape.

Deliberately NOT importing the upstream helpers: `colab_cli.commands.execution`
pulls in `colab_cli.console`, which imports POSIX-only ``termios`` and crashes
on Windows — the same reason `services/colab/execution.py` documents. The rules
below mirror upstream exactly.
"""

from __future__ import annotations


def _strip_shebang(body: str) -> str:
    """Drop a leading ``#!`` line so it is not sent as Python source."""
    if body.startswith("#!"):
        _, _, rest = body.partition("\n")
        return rest
    return body


def build_run_file_payload(source: str, argv: list[str] | None = None) -> str:
    """Build the code sent to the kernel to run a whole script.

    Sets ``sys.argv`` and ``__name__='__main__'`` so ``argparse`` and
    ``if __name__ == "__main__":`` guards behave as they do under
    ``python script.py``, and silences IPython's "To exit: use 'exit'…"
    warning, which is noise outside a REPL.

    The prelude is kept short so traceback line numbers stay close to the
    original file: line *N* of the script reports as roughly ``N + 4``.
    """
    argv = list(argv or [])
    argv_literal = f"[{', '.join(repr(a) for a in argv)}]"
    body = _strip_shebang(source or "")
    return (
        "import sys, warnings\n"
        f"sys.argv = {argv_literal}\n"
        "__name__ = '__main__'\n"
        'warnings.filterwarnings(\'ignore\', message="To exit: use")\n'
        f"{body}"
    )


def payload_line_offset() -> int:
    """How many prelude lines precede the user's code in the payload."""
    return 4
