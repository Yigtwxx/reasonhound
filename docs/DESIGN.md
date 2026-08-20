# Reasonhound — Design Document

Status: **pre-alpha (design only)** · Last updated: 2026-08-20

## 1. Goal

Give a developer a single terminal command that audits **their own** web/API
project for security vulnerabilities — including business-logic and
zero-day-class issues — by **reasoning like a senior researcher** rather than
running a fixed rule list. Output is a Markdown report in the project root.

Hard constraints:

- **No deployment, no domain, no paid server.** Everything runs in the terminal.
- **Cross-platform:** developed on macOS, must run on macOS / Windows / Linux.
- **BYOK:** the tool ships no model and no key; the user selects a provider.
- **Docker optional:** used only to isolate the target app during the dynamic
  phase; falls back to a local subprocess when Docker is absent.

## 2. User experience

```
$ reasonhound scan

? Which AI should do the reasoning?   › Anthropic (Claude) / OpenAI / Google Gemini / Ollama (local)
? How should I scan?                  › Code only (static)  /  Bring the app up end-to-end (dynamic)

⚙  Deep scan running…  [senior reasoning loop]
✔  Report written → ./REASONHOUND-FINDINGS.md
```

- First run persists choices to `.reasonhound.toml`; the API key is read from the
  environment, never stored.
- A one-line **authorized-use** notice prints before any scanning begins.

## 3. Architecture

Two phases run in sequence (static → dynamic). A shared reasoning loop drives
both.

```
scan
 └─> recon      (map: frameworks, endpoints, input points)
       └─> static    (Phase 1: read code, trace data flow -> hypotheses[])
             └─> brain    (reason: try, reflect, pivot — budgeted)
                   └─> dynamic  (Phase 2, optional: Docker bring-up + safe probes)
                         └─> report  (write REASONHOUND-FINDINGS.md)
```

### Modules

| Module | Responsibility | Key interface (sketch) |
| --- | --- | --- |
| `cli` | Interactive prompts, `scan` command, flags | `scan(path, provider, mode, budget, aggressive)` |
| `providers/` | BYOK abstraction, one adapter per provider | `LLMProvider.complete(messages, tools)` |
| `recon` | Detect frameworks, enumerate endpoints & inputs | `recon.map(path) -> AppMap` |
| `static` | Read code, trace tainted data flow, emit hypotheses | `static.analyze(AppMap) -> list[Hypothesis]` |
| `brain` | Reasoning loop; owns the tool-use agent and budget | `brain.investigate(Hypothesis) -> Finding | None` |
| `dynamic` | Bring app up (Docker/local), send safe probes | `dynamic.verify(Hypothesis) -> Evidence` |
| `report` | Render findings to Markdown | `report.write(list[Finding], root)` |

## 4. The reasoning loop (`brain`) — the differentiator

A fixed-rule scanner cannot chase a hunch. `brain` gives the selected LLM a set
of **tools** and lets it think:

Tools exposed to the model:

- `read_file(path, range)` — read source
- `grep(pattern)` — search the codebase
- `trace_dataflow(symbol)` — follow a value from source to sink
- `send_probe(request)` — dynamic phase only; harmless HTTP probe

Loop:

1. **Hypothesize** from a candidate produced by `static`.
2. **Investigate** using the tools.
3. **Judge**: confirmed → record a `Finding` with evidence + rationale;
   inconclusive → the model writes *why* and proposes a new angle.
4. **Pivot** into a fresh hypothesis. Bounded by a **round/token budget** so it
   always terminates.

Every `Finding` carries the model's reasoning trail, so results are auditable.

## 5. Vulnerability coverage

- **Known classes (fast path):** OWASP Top 10 — injection, broken auth, SSRF,
  XSS, insecure deserialization, etc.
- **Unknown / logic classes (reasoning path):** IDOR, auth bypass, race
  conditions, mass-assignment, and other business-logic flaws that require
  understanding intent. Zero-day-class discovery is a **best-effort** goal, not a
  guarantee.

## 6. Dynamic phase & safety

- Prefer **Docker**: build/run the target in a container, probe over the
  network, tear it down. Falls back to a local subprocess if Docker is missing.
- **Safe verification by default:** payloads prove exploitability without
  destroying data (timing deltas, error-shape differences, reflected markers).
- **`--aggressive`:** real exploitation PoCs; opt-in, confirmation-gated,
  disposable environments only.

## 7. Cross-platform

Pure Python 3.11+, `pathlib` throughout, no OS-specific shell assumptions.
Docker interactions go through the Docker CLI, which is uniform across OSes.
(No ML/torch dependency, so the CUDA → MPS → CPU device rule does not apply.)

## 8. Packaging & distribution

- `pyproject.toml`, published to **PyPI** as `reasonhound`.
- Release automated via **GitHub Actions** on tag push.
- Install: `pip install reasonhound`. No server, no domain, no deploy.

## 9. Testing

- `pytest` with mocked providers for `static`/`brain`.
- A deliberately-vulnerable sample app under `tests/fixtures/` as the
  end-to-end target for the dynamic phase.
- `ruff check` + `ruff format --check` clean in CI.

## 10. Open questions / future

- Config schema for per-project scan profiles.
- Caching of reasoning traces to resume long scans.
- Optional SARIF output for CI integrations.
