"""Typer application: the ``reasonhound`` entry point and the ``scan`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from reasonhound import __version__
from reasonhound.cli import prompts
from reasonhound.config import (
    DEFAULT_BUDGET,
    REPORT_DIRNAME,
    ConfigError,
    Provider,
    ScanConfig,
    ScanMode,
    api_key_present,
    load_config,
    save_config,
)
from reasonhound.providers import default_model

AUTHORIZED_USE_NOTICE = (
    "Authorized use only: scan systems you own or are explicitly permitted to test."
)
AUTHORIZATION_QUESTION = "I own this system or am explicitly authorized to test it. Confirm?"
AGGRESSIVE_QUESTION = (
    "Aggressive mode runs real exploitation payloads. Only use it against a "
    "disposable or fully backed-up environment. Continue?"
)

app = typer.Typer(
    name="reasonhound",
    help="AI-assisted security scanner that reasons like a senior researcher.",
    # A bare `reasonhound` opens the interactive flow instead of printing help.
    invoke_without_command=True,
    add_completion=False,
    rich_markup_mode=None,
)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"reasonhound {__version__}")
        raise typer.Exit()


@app.callback()
def root(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-V",
            help="Show the version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Reasonhound command-line interface.

    Run with no command in a terminal to scan the current directory
    interactively; ``reasonhound scan`` takes the same flow with flags.
    """
    if ctx.invoked_subcommand is not None:
        return
    if not prompts.is_interactive():
        # Scripts and CI get the help text: there is nobody to answer questions.
        typer.echo(ctx.get_help())
        raise typer.Exit()
    typer.secho(f"Reasonhound {__version__}", bold=True)
    scan(path=Path.cwd())


def _fail(message: str, code: int = 1) -> typer.Exit:
    typer.secho(f"error: {message}", fg=typer.colors.RED, err=True)
    return typer.Exit(code)


@app.command()
def scan(
    path: Annotated[
        Path,
        typer.Argument(
            help="Project root to scan.",
            exists=True,
            file_okay=False,
            dir_okay=True,
            resolve_path=True,
        ),
    ] = Path(),
    provider: Annotated[
        Provider | None,
        typer.Option(
            "--provider", "-p", help="Reasoning provider (asked interactively if omitted)."
        ),
    ] = None,
    mode: Annotated[
        ScanMode | None,
        typer.Option("--mode", "-m", help="Scan depth (asked interactively if omitted)."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Provider model id (defaults per provider)."),
    ] = None,
    budget: Annotated[
        int | None,
        typer.Option("--budget", "-b", min=1, help="Max reasoning rounds per hypothesis."),
    ] = None,
    aggressive: Annotated[
        bool,
        typer.Option(
            "--aggressive",
            help="Enable real exploitation PoCs (dynamic mode only, confirmation-gated).",
        ),
    ] = False,
    authorized: Annotated[
        bool,
        typer.Option(
            "--authorized",
            help=(
                "Affirm that you own or are explicitly authorized to test the target. "
                "Replaces the interactive authorization prompt; required when not "
                "running in a terminal. Never persisted."
            ),
        ),
    ] = False,
    yes: Annotated[
        bool,
        typer.Option(
            "--yes",
            "-y",
            help=(
                "Skip the plan-preview approval. Never skips the authorization or "
                "--aggressive confirmations."
            ),
        ),
    ] = False,
) -> None:
    """Scan a project for security vulnerabilities."""
    del yes  # plan preview lands with the orchestrator; the flag is accepted today
    try:
        saved = load_config(path)
    except ConfigError as exc:
        raise _fail(str(exc)) from exc

    provider = _resolve_provider(provider, saved)
    mode = _resolve_mode(mode, saved)
    model = _resolve_model(model, saved, provider)
    if budget is None:
        budget = saved.budget if saved else DEFAULT_BUDGET

    if aggressive and mode is not ScanMode.DYNAMIC:
        raise _fail("--aggressive requires --mode dynamic.", code=2)

    if not api_key_present(provider):
        raise _fail(
            f"{provider.label} needs an API key. Set the {provider.env_var} environment "
            "variable and retry."
        )

    typer.secho(AUTHORIZED_USE_NOTICE, fg=typer.colors.YELLOW)
    _require_authorization(authorized)
    if aggressive:
        _confirm_aggressive()

    # Merge onto the saved config so fields no flag touches (concurrency,
    # cost_cap_usd, exclude) survive the run instead of resetting to defaults.
    base = saved if saved is not None else ScanConfig(provider=provider)
    config = base.model_copy(
        update={"provider": provider, "mode": mode, "model": model, "budget": budget}
    )
    save_config(path, config)

    typer.echo(f"Target:   {path}")
    typer.echo(f"Provider: {provider.label}")
    typer.echo(f"Model:    {model}")
    typer.echo(f"Mode:     {mode.label}")
    typer.echo(f"Budget:   {budget} rounds")
    if aggressive:
        typer.secho("Aggressive exploitation: ENABLED", fg=typer.colors.RED)

    # The recon -> static -> brain -> dynamic -> report pipeline lands in later milestones.
    typer.secho(
        f"Scan pipeline is not implemented yet; no {REPORT_DIRNAME}/ folder was written.",
        fg=typer.colors.YELLOW,
    )


def _require_authorization(authorized: bool) -> None:
    """Authorization gate: explicit, required, re-asked every run, never persisted."""
    if authorized:
        return
    if not prompts.is_interactive():
        raise _fail(
            "--authorized is required when not running in a terminal: pass it to "
            "affirm you own or are explicitly authorized to test the target.",
            code=2,
        )
    if not typer.confirm(AUTHORIZATION_QUESTION, default=False):
        typer.echo("Aborted.")
        raise typer.Exit(1)


def _confirm_aggressive() -> None:
    """Real-exploitation gate: always an interactive confirmation, no flag bypass."""
    if not prompts.is_interactive():
        raise _fail(
            "--aggressive must be confirmed in an interactive terminal; it cannot be "
            "enabled non-interactively.",
            code=2,
        )
    if not typer.confirm(AGGRESSIVE_QUESTION, default=False):
        typer.echo("Aborted.")
        raise typer.Exit(1)


def _resolve_provider(provider: Provider | None, saved: ScanConfig | None) -> Provider:
    """Flag wins; otherwise ask in a terminal, or fall back to the saved value."""
    if provider is not None:
        return provider
    if prompts.is_interactive():
        return prompts.ask_provider(default=saved.provider if saved else None)
    if saved is not None:
        return saved.provider
    raise _fail("--provider is required when not running in a terminal.", code=2)


def _resolve_mode(mode: ScanMode | None, saved: ScanConfig | None) -> ScanMode:
    """Flag wins; otherwise ask in a terminal, or fall back to the saved value."""
    if mode is not None:
        return mode
    if prompts.is_interactive():
        return prompts.ask_mode(default=saved.mode if saved else None)
    if saved is not None:
        return saved.mode
    raise _fail("--mode is required when not running in a terminal.", code=2)


def _resolve_model(model: str | None, saved: ScanConfig | None, provider: Provider) -> str:
    """Flag wins; then a saved model, but only one saved for *this* provider.

    Without the provider guard, a project that once ran with Anthropic would send
    a Claude model id to OpenAI on the next run and get a confusing 404.
    """
    if model is not None:
        return model
    if saved is not None and saved.model and saved.provider is provider:
        return saved.model
    return default_model(provider)


def main() -> None:
    """Console-script entry point."""
    app()
