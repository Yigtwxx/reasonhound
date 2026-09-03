"""Interactive prompts (questionary) used when flags are not supplied."""

from __future__ import annotations

import sys

import questionary

from reasonhound.config import Provider, ScanMode


def is_interactive() -> bool:
    """True when both stdin and stdout are attached to a terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()


def ask_provider(default: Provider | None = None) -> Provider:
    """Ask which provider should do the reasoning."""
    choices = [questionary.Choice(title=p.label, value=p) for p in Provider]
    answer = questionary.select(
        "Which AI should do the reasoning?",
        choices=choices,
        default=default,
    ).ask()
    if answer is None:  # user pressed Ctrl-C
        raise KeyboardInterrupt
    return Provider(answer)


def ask_mode(default: ScanMode | None = None) -> ScanMode:
    """Ask whether to run a static-only or dynamic scan."""
    choices = [questionary.Choice(title=m.label, value=m) for m in ScanMode]
    answer = questionary.select(
        "How should I scan?",
        choices=choices,
        default=default,
    ).ask()
    if answer is None:
        raise KeyboardInterrupt
    return ScanMode(answer)
