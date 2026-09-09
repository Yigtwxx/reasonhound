# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- The four BYOK provider adapters, written directly against each HTTP API with
  `httpx` and no vendor SDKs: Anthropic (Messages), OpenAI (Chat Completions),
  Google Gemini (`generateContent`), and Ollama (`/api/chat`). All four support
  tool use and streaming behind the existing `LLMProvider` interface.
- A shared HTTP base that owns the client lifecycle, error mapping, and the
  **always-on egress redaction** — the request body is redacted in one place, so
  no adapter can forget it. Structural fields (tool-call ids and names, model
  ids, tool schemas) are exempt so redaction cannot corrupt the protocol.
- Retry with exponential backoff, jitter, and `Retry-After` support for rate
  limits, overload, and dropped connections. Streams retry only before the first
  byte; replaying a half-delivered stream would duplicate text.
- `create_provider()` reads the API key from the environment at call time and
  keeps it only in request headers; a missing key names the variable, never the
  value.
- Model selection: `ScanConfig.model`, a per-provider default, and a `--model`
  flag. A saved model is reused only for the provider it was saved with. Defaults
  are the current top-tier stable model per provider (verified 2026-09-09).

### Fixed
- `save_config` now drops unset fields; TOML has no null and `tomli_w` raises on
  a `None` value.
- Ollama's default model carries an explicit tag (`llama3.1:8b`); a bare
  `llama3.1` returns a 404 unless `:latest` happens to be pulled. A
  model-not-found error now names the `ollama pull` command that fixes it.

## [0.0.1] - 2026-09-03

### Changed
- Design reworked into a **multi-agent** architecture: an orchestrator
  (`lead-strategist`) that dispatches a library of ~35 specialized subagents,
  each with its own toolkit. See `docs/DESIGN.md`.
- Reasoning gains **double-voting** verification (prove / disprove / arbitrate)
  with severity × confidence scoring; the static engine is now **hybrid
  tree-sitter + LLM**.
- Providers: all four (Anthropic / OpenAI / Gemini / Ollama) targeted for day
  one via lightweight `httpx` adapters (no vendor SDKs).
- Added an always-on **security layer**: egress secret/PII redaction,
  prompt-injection defense (data-fencing, tool allowlists, strict schemas), an
  **egress-locked** dynamic phase, and gated stealth/evasion testing with an
  audit log.
- Terminal UX: a guided startup wizard plus a **Textual live monitor** (agent
  tree, findings feed, budget meter, kill-switch).
- Output moved from a single `REASONHOUND-FINDINGS.md` to a **`Reasonhound/`
  folder** (per-finding Markdown + `INDEX.md` + `audit.log`) with smart merge on
  re-runs.
- Packaging: heavy dependencies split into optional extras (`[dynamic]`,
  `[frontend]`, `[all]`); `pipx` is the recommended install.

### Added
- `pyproject.toml` (hatchling, src layout) with `ruff` and `pytest` configuration.
- CLI skeleton: `reasonhound scan` with `--provider`, `--mode`, `--budget`,
  `--aggressive` (dynamic-only, always confirmed interactively — `--yes` never
  skips it), `--authorized` (per-run authorization affirmation for
  non-interactive use, never persisted) and `--yes`; interactive provider/mode
  prompts when flags are omitted; `--version`.
- Per-project `.reasonhound.toml` persistence (no secrets); each run merges the
  flags it was given onto the saved file, so untouched fields (concurrency,
  cost cap, excludes) survive, and non-interactive runs fall back to the saved
  provider/mode.
- API-key presence check via environment variables; an explicit authorized-use
  confirmation gate that is re-asked on every run.
- `security` primitives: egress redactor (named rules incl. `SECRET_KEY`-style
  assignments, connection-URL credentials, Basic auth, plus an entropy pass),
  data-fencing with a sanitized `source` label, a structurally redacted
  `Reasonhound/audit.log`, and a fail-closed HTTP-only egress policy.
- Empty package stubs for `providers`, `recon`, `static`, `dynamic`, `brain`, `report`.
- Initial project documentation: README, design document, contribution guide,
  code of conduct, security policy, and license.
- Project scaffolding (`.gitignore`, issue/PR templates, `CLAUDE.md`).

_The scan pipeline itself is not implemented yet; only the CLI shell exists._

[Unreleased]: https://github.com/Yigtwxx/reasonhound/compare/v0.0.1...HEAD
[0.0.1]: https://github.com/Yigtwxx/reasonhound/releases/tag/v0.0.1
