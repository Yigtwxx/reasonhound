"""Tests for the ``reasonhound`` CLI."""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from reasonhound import __version__
from reasonhound.cli import prompts
from reasonhound.cli.app import AUTHORIZED_USE_NOTICE, app
from reasonhound.config import Provider, ScanMode, config_path, load_config


@pytest.fixture
def interactive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend stdin/stdout are a terminal so confirmation prompts are asked."""
    monkeypatch.setattr(prompts, "is_interactive", lambda: True)


def test_version(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


def test_no_args_shows_help(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    assert "scan" in result.output


def test_scan_static_ollama(runner: CliRunner, project: Path, no_api_keys: None) -> None:
    result = runner.invoke(
        app, ["scan", str(project), "--provider", "ollama", "--mode", "static", "--authorized"]
    )

    assert result.exit_code == 0, result.output
    assert AUTHORIZED_USE_NOTICE in result.output
    assert "not implemented yet" in result.output
    saved = load_config(project)
    assert saved is not None
    assert saved.provider is Provider.OLLAMA
    assert saved.mode is ScanMode.STATIC
    assert saved.budget == 20
    # The authorization affirmation is per-run and must never be persisted.
    assert "authoriz" not in config_path(project).read_text().lower()


def test_scan_requires_api_key(runner: CliRunner, project: Path, no_api_keys: None) -> None:
    result = runner.invoke(
        app, ["scan", str(project), "-p", "anthropic", "-m", "static", "--authorized"]
    )

    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output
    assert load_config(project) is None


def test_scan_with_api_key(
    runner: CliRunner, project: Path, no_api_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret")
    result = runner.invoke(
        app, ["scan", str(project), "-p", "openai", "-m", "dynamic", "-b", "5", "--authorized"]
    )

    assert result.exit_code == 0, result.output
    assert "sk-test-secret" not in result.output
    saved = load_config(project)
    assert saved is not None and saved.budget == 5 and saved.mode is ScanMode.DYNAMIC


def test_saved_config_provides_defaults(
    runner: CliRunner, project: Path, no_api_keys: None
) -> None:
    runner.invoke(
        app, ["scan", str(project), "-p", "ollama", "-m", "dynamic", "-b", "3", "--authorized"]
    )

    # Second run only passes provider/mode; budget must come from the saved config.
    result = runner.invoke(
        app, ["scan", str(project), "-p", "ollama", "-m", "dynamic", "--authorized"]
    )
    assert result.exit_code == 0
    assert "3 rounds" in result.output


def test_non_interactive_requires_flags(
    runner: CliRunner, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: False)
    result = runner.invoke(app, ["scan", str(project)])

    assert result.exit_code == 2
    assert "--provider is required" in result.output


def test_interactive_prompts_are_used(
    runner: CliRunner,
    project: Path,
    no_api_keys: None,
    interactive: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(prompts, "ask_provider", lambda default=None: Provider.OLLAMA)
    monkeypatch.setattr(prompts, "ask_mode", lambda default=None: ScanMode.STATIC)

    result = runner.invoke(app, ["scan", str(project)], input="y\n")
    assert result.exit_code == 0, result.output
    assert "Ollama" in result.output


# --- authorization gate ---------------------------------------------------------


def test_authorization_required_non_interactive(
    runner: CliRunner, project: Path, no_api_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: False)
    result = runner.invoke(app, ["scan", str(project), "-p", "ollama", "-m", "static"])

    assert result.exit_code == 2
    assert "--authorized is required" in result.output
    assert load_config(project) is None


def test_authorization_prompt_declined(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    result = runner.invoke(app, ["scan", str(project), "-p", "ollama", "-m", "static"], input="n\n")

    assert result.exit_code == 1
    assert "Aborted" in result.output
    assert load_config(project) is None


def test_authorization_prompt_accepted(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    result = runner.invoke(app, ["scan", str(project), "-p", "ollama", "-m", "static"], input="y\n")

    assert result.exit_code == 0, result.output
    assert "authorized to test it" in result.output
    assert load_config(project) is not None


def test_authorization_is_reasked_every_run(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    args = ["scan", str(project), "-p", "ollama", "-m", "static"]
    assert runner.invoke(app, args, input="y\n").exit_code == 0
    # Saved config exists now, but the gate still blocks a second run.
    assert runner.invoke(app, args, input="n\n").exit_code == 1


# --- aggressive gate ------------------------------------------------------------


def test_aggressive_requires_dynamic(runner: CliRunner, project: Path, no_api_keys: None) -> None:
    result = runner.invoke(
        app, ["scan", str(project), "-p", "ollama", "-m", "static", "--aggressive", "--authorized"]
    )
    assert result.exit_code == 2
    assert "requires --mode dynamic" in result.output


def test_aggressive_confirmation_declined(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    result = runner.invoke(
        app,
        ["scan", str(project), "-p", "ollama", "-m", "dynamic", "--aggressive", "--authorized"],
        input="n\n",
    )
    assert result.exit_code == 1
    assert "Aborted" in result.output
    assert load_config(project) is None


def test_aggressive_confirmation_accepted(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    result = runner.invoke(
        app,
        ["scan", str(project), "-p", "ollama", "-m", "dynamic", "--aggressive", "--authorized"],
        input="y\n",
    )
    assert result.exit_code == 0, result.output
    assert "Aggressive exploitation: ENABLED" in result.output


def test_yes_does_not_skip_aggressive_confirmation(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    result = runner.invoke(
        app,
        [
            "scan",
            str(project),
            "-p",
            "ollama",
            "-m",
            "dynamic",
            "--aggressive",
            "--authorized",
            "-y",
        ],
        input="n\n",
    )
    assert result.exit_code == 1
    assert "Aborted" in result.output


def test_aggressive_fails_closed_non_interactive(
    runner: CliRunner, project: Path, no_api_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: False)
    result = runner.invoke(
        app,
        [
            "scan",
            str(project),
            "-p",
            "ollama",
            "-m",
            "dynamic",
            "--aggressive",
            "--authorized",
            "-y",
        ],
    )
    assert result.exit_code == 2
    assert "interactive terminal" in result.output
    assert load_config(project) is None


def test_aggressive_prompt_comes_after_api_key_check(
    runner: CliRunner, project: Path, no_api_keys: None, interactive: None
) -> None:
    result = runner.invoke(
        app,
        ["scan", str(project), "-p", "anthropic", "-m", "dynamic", "--aggressive", "--authorized"],
    )
    assert result.exit_code == 1
    assert "ANTHROPIC_API_KEY" in result.output
    assert "Continue?" not in result.output


# --- misc -----------------------------------------------------------------------


def test_scan_rejects_missing_path(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["scan", str(tmp_path / "nope"), "-p", "ollama", "-m", "static", "--authorized"]
    )
    assert result.exit_code != 0


def test_invalid_config_is_reported(runner: CliRunner, project: Path, no_api_keys: None) -> None:
    (project / ".reasonhound.toml").write_text("this is [not toml")
    result = runner.invoke(
        app, ["scan", str(project), "-p", "ollama", "-m", "static", "--authorized"]
    )
    assert result.exit_code == 1
    assert "Invalid config" in result.output


# --- saved config is merged, not clobbered ----------------------------------------


def test_scan_preserves_unrelated_saved_fields(
    runner: CliRunner, project: Path, no_api_keys: None
) -> None:
    from reasonhound.config import ScanConfig, save_config

    save_config(
        project,
        ScanConfig(
            provider=Provider.OLLAMA,
            mode=ScanMode.DYNAMIC,
            budget=7,
            concurrency=8,
            cost_cap_usd=2.5,
            exclude=["node_modules", "coverage"],
        ),
    )
    result = runner.invoke(
        app, ["scan", str(project), "-p", "ollama", "-m", "static", "--authorized"]
    )

    assert result.exit_code == 0, result.output
    saved = load_config(project)
    assert saved is not None
    assert saved.mode is ScanMode.STATIC  # the flag wins
    assert saved.budget == 7  # untouched fields survive
    assert saved.concurrency == 8
    assert saved.cost_cap_usd == 2.5
    assert saved.exclude == ["node_modules", "coverage"]


def test_non_interactive_uses_saved_provider_and_mode(
    runner: CliRunner, project: Path, no_api_keys: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(prompts, "is_interactive", lambda: False)
    first = runner.invoke(
        app, ["scan", str(project), "-p", "ollama", "-m", "dynamic", "--authorized"]
    )
    assert first.exit_code == 0, first.output

    result = runner.invoke(app, ["scan", str(project), "--authorized"])
    assert result.exit_code == 0, result.output
    assert "Ollama" in result.output
    assert "dynamic" in result.output.lower()
