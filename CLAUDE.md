# CLAUDE.md — Reasonhound

Project-level instructions for Claude Code. These complement the user's global
`~/.claude/CLAUDE.md`; anything here is specific to Reasonhound.

## What this project is

Reasonhound is an **AI-assisted security scanner** that reasons like a senior
researcher. A developer runs it against **their own** web/API project. It reads
the code (static phase), optionally spins the app up in Docker to verify
hypotheses (dynamic phase), and writes a Markdown findings report to the
project root. The reasoning engine is **BYOK** — the user brings their own model
(Anthropic / OpenAI / Gemini / Ollama); the tool ships no model or key.

> Status: pre-alpha. Docs & design only — no implementation code yet.

## Stack (planned)

- **Language:** Python 3.11+
- **CLI:** `typer` (or `click`)
- **Interactive prompts:** `questionary`
- **HTTP probing:** `httpx`
- **Config:** `pydantic` + TOML (`.reasonhound.toml`)
- **Containers:** Docker (optional, dynamic phase only) via the local Docker CLI
- **Packaging:** `pyproject.toml`, published to PyPI via GitHub Actions
- **Lint/format:** `ruff`
- **Tests:** `pytest`

## Module boundaries

Each module has one purpose and a clear interface. Keep them independently
testable.

| Module | Responsibility |
| --- | --- |
| `cli` | Interactive questions, `scan` command, flags |
| `providers/` | BYOK `LLMProvider` interface + one adapter per provider |
| `recon` | Framework detection, endpoint & input-point discovery |
| `static` | Phase 1: code reading, data-flow tracing → hypotheses (JSON) |
| `dynamic` | Phase 2: Docker bring-up + harmless probing |
| `brain` | Senior reasoning loop (tool-use agent, budgeted) |
| `report` | Writes `REASONHOUND-FINDINGS.md` |

## Language rules

- **All code, identifiers, and comments: English.**
- All public docs (README, this file, etc.): **English** (open-source, international audience).

## Cross-platform rule

Code must run on **macOS, Windows, and Linux**. Use `pathlib`, never hard-code
path separators or shell assumptions. Developed on macOS (Apple Silicon).

> Note: this is not an ML project, so the CUDA → MPS → CPU device rule does not
> apply here. If any local-embedding feature is ever added, follow that order.

## Security rules (hard constraints)

- **Never** hard-code or log secrets, tokens, or API keys. Read keys only from
  the environment (`ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`).
- The dynamic phase is **safe-by-default**: harmless verification payloads only.
  Destructive/aggressive exploitation is opt-in (`--aggressive`) and must be
  gated behind an explicit confirmation.
- Every run prints an **authorized-use** notice before scanning.
- Never send user code to any provider the user did not explicitly select.

## Verification (before declaring work done)

- `ruff check` and `ruff format --check` clean
- `pytest` green
- Cross-platform paths preserved (no OS-specific breakage)

## Workflow

Explore → plan → implement → verify. Write a plan when multiple files are
affected. Prefer existing agents/skills over reinventing. Use
`systematic-debugging` before proposing fixes.

## Git

Do not commit, push, or open PRs unless explicitly asked. Follow Conventional
Commits (`feat`, `fix`, `refactor`, `test`, `docs`, `chore`).
