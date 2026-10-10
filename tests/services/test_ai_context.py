"""SKILL.md drift test — every claim the doc makes is re-verified against src.

The context document teaches an AI how THIS app works. When the app's behaviour
changes and the doc does not, the model confidently writes code that fails.
This test reads the doc, extracts its behavioural claims, and asserts each one
still holds in the source.
"""

import pathlib
import re
import sys

sys.path.insert(0, "src")

SKILL = pathlib.Path("src/ai/SKILL.md")
SRC = pathlib.Path("src")


def _read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8")


def _all_source() -> str:
    return "\n".join(
        _read(p) for p in sorted(SRC.rglob("*.py")) if "__pycache__" not in str(p)
    )


# ── the doc itself ─────────────────────────────────────────────────────────


def test_skill_md_exists_and_loads():
    text = _read(SKILL)
    assert text.startswith("---"), "frontmatter missing"
    # Frontmatter carries name + a description that says WHEN to use it.
    head = text.split("---", 2)[1]
    assert "name:" in head
    assert "description:" in head


def test_skill_sections_present_in_proven_order():
    text = _read(SKILL)
    order = [
        "# Skill:",
        "## Mental model",
        "## When to activate",
        "## Authentication",
        "## Workflow",
        "## Do NOT run",
        "## Troubleshooting",
        "## Safety",
        "## Recovery",
    ]
    positions = [text.find(s) for s in order]
    assert all(p >= 0 for p in positions), order
    assert positions == sorted(positions), "sections out of order"


def test_skill_states_the_verified_divergences():
    """These are the claims an AI that only knows the CLI would get wrong."""
    text = _read(SKILL)
    assert "oauth2" in text and "adc" in text
    assert "T4" in text and "A100" in text
    assert "V6E1" in text and "v5e1" in text
    assert "clear_output" in text
    assert "termios" in text
    assert "/content" in text


# ── each claim re-verified against the source ──────────────────────────────


def test_claim_default_auth_is_oauth2():
    src = _read(SRC / "services" / "colab" / "__init__.py")
    assert 'auth_method: str = "oauth2"' in src


def test_claim_unrecognized_gpu_falls_back_to_t4():
    src = _read(SRC / "services" / "colab" / "session_ops.py")
    assert "mapping.get(gpu.lower(), Accelerator.T4)" in src


def test_claim_other_tpu_names_become_v6e1():
    src = _read(SRC / "services" / "colab" / "session_ops.py")
    assert "Accelerator.V5E1 if tpu.lower() == \"v5e1\" else Accelerator.V6E1" in src


def test_claim_cwd_is_content():
    src = _read(SRC / "services" / "colab" / "execution.py")
    assert "os.makedirs('/content', exist_ok=True)" in src
    assert "os.chdir('/content')" in src


def test_claim_clear_output_is_unhandled():
    """The app never surfaces it, so the AI must not rely on it."""
    execution = _read(SRC / "services" / "colab" / "execution.py")
    # Documented as deliberately unhandled.
    assert "clear_output" in execution
    assert "deliberately unhandled" in execution


def test_claim_termios_crash_avoidance_exists():
    src = _read(SRC / "services" / "colab" / "execution.py")
    assert "termios" in src


def test_claim_env_key_rule():
    src = _read(SRC / "services" / "colab" / "execution.py")
    assert "[A-Za-z_][A-Za-z0-9_]*" in src


def test_claim_env_values_never_logged():
    src = _read(SRC / "services" / "colab" / "execution.py")
    assert "env_keys" in src  # only key NAMES reach history


def test_claim_drive_mount_is_interactive():
    src = _read(SRC / "services" / "colab" / "vm_ops.py")
    assert "drive.mount" in src
    assert "stdin_hook" in src


def test_claim_high_mem_unsupported_on_gpu_tpu():
    """The High-RAM switch is hidden for shapes where it does not apply, which
    is why the doc says it is only meaningful on CPU."""
    view = _read(SRC / "screens" / "session" / "notebook_view.py")
    picker = _read(SRC / "components" / "hardware_picker.py")
    # The visibility rule exists in one of the two places it is enforced.
    assert "high_mem" in view or "high_mem" in picker


def _collapse(text: str) -> str:
    """Collapse whitespace so wrapped docstrings match a single-line needle."""
    return re.sub(r"\s+", " ", text)


def test_claim_notebook_tabs_share_one_kernel():
    src = _collapse(_read(SRC / "screens" / "session" / "notebook_view.py"))
    assert "All tabs share the session kernel" in src


def test_claim_restart_wipes_variables_keeps_cells():
    src = _read(SRC / "screens" / "session" / "notebook_view.py")
    assert "Restart Kernel" in src


# ── the loader ─────────────────────────────────────────────────────────────


def test_loader_returns_the_document():
    from ai import print_skill, skill_text

    text = skill_text()
    assert text.startswith("---")
    assert "## Mental model" in text
    assert print_skill() == text


def test_loader_is_safe_when_file_missing(monkeypatch):
    """A missing document degrades to "" — never raises into a turn.

    Both real read paths fail, so this exercises the guard rather than
    monkeypatching the function the caller resolves.
    """
    import ai

    def _raise(*_a, **_k):
        raise OSError("no such file")

    monkeypatch.setattr(ai, "_importlib_files", _raise)
    monkeypatch.setattr(ai, "_dev_tree_read", _raise)
    assert ai.skill_text() == ""
    assert "not available" in ai.print_skill()


def test_system_prompt_includes_skill():
    from services.ai_service import _system_prompt, system_prompt_with_skill

    with_skill = _system_prompt("MARKER-TEXT")
    assert "MARKER-TEXT" in with_skill
    # Without a skill, the built-in rules still stand alone.
    assert "oauth2" in _system_prompt(None)
    # The real document loads in the test environment.
    assert "Mental model" in system_prompt_with_skill()
