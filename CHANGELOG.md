# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- The agent runtime. `tools/` offers read-only, root-sandboxed `fs_read`,
  `fs_grep`, `fs_glob` and a tree-sitter `ast_parse` outline; every output is
  data-fenced, and each agent gets a `Toolbox` built from its fixed allowlist, so
  a call outside it is refused and reported (`ToolDenied`). Tool schemas are
  reduced to a subset every provider accepts (no `$ref`, `Optional` as `nullable`).
- `agents/`: `AgentSpec` + `run_agent`, a bounded hypothesize / investigate /
  judge / pivot loop that finishes only through a `submit_result` tool whose
  arguments must validate against the agent's strict output model; rejected
  submissions are fed back for a fix. `HunterReport` / `HypothesisDraft` are the
  first contracts; the runtime assigns ids and attribution.
- `orchestrator`: `lead-strategist` plans with the model, drops agents that are
  not in the catalog (falling back to "run every agent once" when nothing usable
  is left), dispatches runs on a thread pool, and dedupes hypotheses.
- `budget`: a thread-safe ledger that prices every completion and stops the scan
  at `cost_cap_usd`; unknown models are priced high so the cap never silently
  switches off. `control`: kill one agent, kill all, pause / resume (Ctrl-C maps
  to kill-all). `events`: a typed event bus for the upcoming TUI.
- Stops are cooperative and always return what was collected (`PARTIAL` with a
  reason) instead of discarding the run.
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

- Release automation: pushing a `vX.Y.Z` tag tests on Linux / macOS / Windows,
  checks the tag against the package version, and publishes to PyPI through
  Trusted Publishing (OIDC, no stored token). Actions are pinned to commit SHAs.

### Changed
- One install now includes every phase: `docker`, `playwright` and `lancedb`
  moved into the base dependencies and the `[dynamic]` / `[frontend]` / `[all]`
  extras are gone. `pipx install reasonhound` is the whole tool.
- Running `reasonhound` with no command in a terminal starts the interactive
  scan of the current directory; without a terminal it still prints help.
- The Ollama default model is now `qwen3.5:9b` (6.7 GB of memory at 32K
  context). In live tool-calling scans it found every planted bug with the
  correct `file:line` and graded severity; `gpt-oss:20b` found them but left the
  location empty, and `llama3.1:8b` never submitted a result. With more memory,
  `--model qwen3.6:35b-a3b` (23 GB) is the stronger local choice.

### Fixed
- The Ollama adapter now sends `num_ctx` (default 32768). Without it Ollama used
  its small default window and silently cut the front of long agent
  conversations, system prompt and data-fencing rule first.
- `save_config` now drops unset fields; TOML has no null and `tomli_w` raises on
  a `None` value.
- Ollama's default model carries an explicit tag; a bare name returns a 404
  unless `:latest` happens to be pulled. A
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
