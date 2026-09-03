# CLAUDE.md — Reasonhound

Project-level instructions for Claude Code. These complement the user's global
`~/.claude/CLAUDE.md`; anything here is specific to Reasonhound.

## What this project is

Reasonhound is an **AI-assisted security scanner** that reasons like a senior
researcher. A developer runs it against **their own** web/API project. It reads
the code (static phase), optionally spins the app up in Docker to verify
hypotheses (dynamic phase), and writes per-finding Markdown reports into a
`Reasonhound/` folder in the project root. The reasoning engine is **BYOK** —
the user brings their own model (Anthropic / OpenAI / Gemini / Ollama); the tool
ships no model or key.

The engine is **multi-agent**: a single orchestrator (`lead-strategist`) plans
the scan and dispatches a library of ~35 specialized subagents, each with its
own narrow toolkit. These are Reasonhound's *own* internal agents (Python,
driven by the selected provider) — **not** Claude Code sub-agents — so the design
runs on any BYOK provider. The terminal is the UI: a guided startup wizard, then
a live Textual monitor that shows which agent is doing what and lets the user
pause / kill agents. Full architecture: [`docs/DESIGN.md`](docs/DESIGN.md).

> Status: pre-alpha. `pyproject.toml` + CLI skeleton exist (`src/reasonhound/`);
> the scan pipeline modules are empty stubs.

## Stack

- **Language:** Python 3.11+ (src layout: `src/reasonhound/`; venv via `uv`)
- **CLI wizard:** `typer` + `questionary`
- **Live TUI:** `textual` (multi-pane monitor; `--plain` fallback for CI)
- **Providers:** BYOK, four day-one adapters (Anthropic / OpenAI / Gemini /
  Ollama) written directly against each HTTP API with `httpx` — no vendor SDKs
- **Static engine:** hybrid `tree-sitter` (structure/sinks) + LLM (meaning)
- **HTTP probing:** `httpx`
- **Config:** `pydantic` + TOML (`.reasonhound.toml`; no secrets)
- **Containers:** Docker (optional, dynamic phase only) via the local Docker CLI,
  run in an isolated egress-locked network
- **Browser (frontend phase):** `playwright` headless (optional extra)
- **Packaging:** `pyproject.toml` (hatchling), optional extras
  (`[dynamic]`, `[frontend]`, `[all]`), published to PyPI via GitHub Actions;
  recommended install is `pipx`
- **Lint/format:** `ruff`
- **Tests:** `pytest`

## Module boundaries

Each module has one purpose and a clear interface. Keep them independently
testable.

| Module | Responsibility |
| --- | --- |
| `cli` | Startup wizard (preflight, brain select, auth gate, scope + plan preview), flags |
| `tui` | Textual live monitor, keybindings, `--plain` fallback |
| `providers/` | BYOK `LLMProvider` — one `httpx` adapter per provider, streaming + tool-use |
| `orchestrator` | `lead-strategist`: plan the scan, dispatch subagents, own budget / dedup / status |
| `agents/` | The ~35-agent subagent library, grouped by phase; each agent binds its own toolkit |
| `tools/` | Tool implementations exposed to agents (fs, ast, probe, docker, browser, redact, egress) |
| `static` | Hybrid tree-sitter + LLM: parse, trace tainted data flow, emit hypotheses |
| `dynamic` | Phase 2: Docker bring-up (egress-locked) **or attach to a running localhost target** (`--target`) + harmless probing |
| `verify` | Red/Blue/Arbiter double-voting + reproducible PoC capture |
| `security` | Secret redaction, prompt-injection defense, egress guard, audit log |
| `report` | Writes the `Reasonhound/` folder (INDEX + per-finding Markdown + audit.log), smart merge |
| `config` | `.reasonhound.toml` schema and persistence (no secrets) |

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
- **Egress redaction (always on):** `egress-redactor` masks secrets / tokens /
  PII (regex + entropy) before *anything* is sent to a provider. This base layer
  cannot be disabled.
- **Prompt-injection defense (defense-in-depth):** scanned code is untrusted
  input to the reasoning LLM. Enforce all three: (1) data-fencing — file content
  is wrapped as untrusted data, never instructions; (2) tool-restricted agents —
  each agent may only call its allowlisted tools, so there is no
  file → network exfiltration path; (3) strict JSON schema — agents return
  validated schemas, not free-form text or commands.
- The dynamic phase is **safe-by-default** and **egress-locked**: harmless
  verification payloads only, target in an isolated Docker network with egress
  closed; `escape-watchdog` kills the scan on any out-of-scope request.
  Destructive/aggressive exploitation *and* any stealth / evasion (WAF-bypass)
  testing are opt-in (`--aggressive`), gated behind an explicit confirmation, and
  written to `Reasonhound/audit.log`. Never a general-purpose evasion capability.
- Every run requires an explicit **authorized-use** confirmation before scanning;
  it is re-asked each run and never persisted. Only non-secret preferences are
  written to `.reasonhound.toml`.
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
