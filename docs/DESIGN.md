# Reasonhound — Design Document

Status: **pre-alpha (design only)** · Last updated: 2026-09-03

## 1. Goal

Give a developer a single terminal command that audits **their own** web/API
project for security vulnerabilities — including business-logic and
zero-day-class issues — by **reasoning like a senior researcher** rather than
running a fixed rule list. Output is a set of Markdown reports written into a
`Reasonhound/` folder in the project root.

Hard constraints:

- **No deployment, no domain, no paid server.** Everything runs in the terminal.
- **Cross-platform:** developed on macOS, must run on macOS / Windows / Linux.
- **BYOK:** the tool ships no model and no key; the user selects a provider.
- **Docker optional:** used only to isolate the target app during the dynamic
  phase; falls back to a local subprocess when Docker is absent.
- **Authorized use only:** the tool is defensive. It is meant to be run against a
  project you own or are explicitly authorized to test.

## 2. User experience

The terminal *is* the UI. A run has a guided wizard, then a live multi-pane
monitor built with **Textual** (cross-platform: macOS / Windows / Linux).

### 2.1 Startup wizard

```
$ reasonhound scan

[0] Preflight     git repo ✓   Docker ✓   ANTHROPIC_API_KEY ✓   framework: FastAPI
[1] Brain         › Anthropic (Claude) / OpenAI / Google Gemini / Ollama (local)   [key found ✓]
[2] Authorization ▢ I own this system or am explicitly authorized to test it   (required)
[3] Scope preview whole repo · ~142 files · redaction ON · est. budget ≤ $5.00 / run
[4] Plan preview  lead-strategist will run: recon(5) → static hunters(12) → verify(4) …  [enter to start]
```

- **[0] Preflight / doctor** — checks git repo, Docker presence, the API key in
  the environment, and detects the target framework. Fails fast on anything
  missing.
- **[1] Brain** — pick the provider + model. The key is read from the
  environment, never stored.
- **[2] Authorization gate** — an explicit, **required** confirmation. It is
  re-asked every run and is never persisted to config.
- **[3] Scope preview** — shows what will be scanned and roughly what it will
  send to the provider (files, redaction status, estimated budget cap).
- **[4] Plan preview** — the orchestrator (`lead-strategist`) produces its plan
  (which subagents, in what order) and the user approves before anything runs.
  Skippable with `--yes`.

First run persists non-secret choices to `.reasonhound.toml`.

### 2.2 Live monitor (Textual TUI)

Once started, the orchestrator begins working and dispatches subagents. The
terminal shows, in real time, which agent is doing what:

```
┌ Reasonhound ─ scanning ./my-app ──────────────── ⏱ 02:14 ─ $0.38 / $5.00 ┐
│ AGENTS  (7 active / 31 idle)         │ LIVE FINDINGS                      │
│ ▸ lead-strategist   planning next    │ ● CONFIRMED  SQLi   /api/search    │
│   ├ injection-hunter  tracing sink   │ ○ suspected  IDOR   /users/:id     │
│   ├ xss-analyst       reading views  │ ✗ rejected   XSS    (ORM escapes)  │
│   ├ data-flow-tracer  taint /login   │                                    │
│   └ red-verifier      probing…       │ 12 confirmed · 8 susp · 20 rej     │
├──────────────────────────────────────┴────────────────────────────────────┤
│ CURRENT  injection-hunter: "raw query in search_repo(); user q flows       │
│          unescaped → hypothesis: boolean-based SQLi"                        │
│ SECURITY egress: LOCKED ✓   redaction: ON ✓   probes: 14 (harmless)        │
├────────────────────────────────────────────────────────────────────────────┤
│ [p]ause  [k]ill agent  [K]ill all  [↵] drill-in  [a]pprove  [f]indings  [q] │
└────────────────────────────────────────────────────────────────────────────┘
```

Panes: **agent tree** (live status per agent), **findings feed** (as the arbiter
decides), **current reasoning** stream, **budget meter** (tokens / $), and a
**security indicator** (egress lock, redaction, harmless-probe count).

Keybindings:

| Key | Action |
| --- | --- |
| `p` | Pause / resume all agents |
| `k` | Kill the selected agent (the orchestrator re-dispatches its work) |
| `K` | Kill all — clean shutdown, still writes what was collected so far |
| `↵` | Drill into an agent: full reasoning trace *(v2)* |
| `a` | Approve a gated action when the pop-up appears |
| `f` | Jump to the findings feed |
| `q` | Quit (confirmed) |

When Textual cannot run (CI, dumb terminal), `--plain` / `--no-tty` streams
structured status lines instead.

## 3. Architecture

Reasonhound is a **multi-agent** system. A single orchestrator plans the scan
and dispatches specialized subagents; it decides **how many** to run. Each
subagent has its **own dedicated toolkit** and a narrow focus. The subagents are
Reasonhound's *own* internal agent abstraction (Python, driven by the selected
provider) — **not** Claude Code sub-agents — so the same design runs on any BYOK
provider.

```
scan
 └─> lead-strategist (orchestrator: plan, dispatch, budget, dedup, status)
       ├─ recon agents        (map: frameworks, endpoints, input points, trust boundaries)
       ├─ static hunters      (Phase 1: per-vuln-class specialists → hypotheses)
       ├─ frontend/JS agents  (source maps, browser runtime, supply-chain, framework-aware)
       ├─ dynamic agents      (Phase 2, optional: Docker bring-up + harmless probes)
       ├─ verification agents (double-voting: prove / disprove / arbitrate / reproduce)
       └─ support agents      (redaction, injection-warden, scoring, report, budget, status)
```

### 3.1 Module boundaries

| Module | Responsibility |
| --- | --- |
| `cli` | Startup wizard (preflight, brain, auth gate, scope + plan preview), flags |
| `tui` | Textual live monitor, keybindings, `--plain` fallback |
| `providers/` | BYOK `LLMProvider` — one `httpx` adapter per provider, streaming + tool-use |
| `orchestrator` | `lead-strategist`: plan the scan, dispatch subagents, own budget / dedup / status |
| `agents/` | The subagent library, grouped by phase; each agent binds its own toolkit |
| `tools/` | Tool implementations exposed to agents (fs, ast, probe, docker, browser, redact, egress) |
| `static` | Hybrid tree-sitter + LLM: parse, trace tainted data flow, emit hypotheses |
| `dynamic` | Bring the app up (Docker/local, egress-locked) and send harmless probes |
| `verify` | Red/Blue/Arbiter double-voting + reproducible PoC capture |
| `security` | Secret redaction, prompt-injection defense, egress guard, audit log |
| `report` | Write the `Reasonhound/` folder (index + per-finding Markdown + audit log) |
| `config` | `.reasonhound.toml` schema and persistence (no secrets) |

## 4. The subagent library

35 subagents in 7 groups (enough for the first version; extendable later). The
orchestrator picks a subset per run. Each agent's **toolkit** is fixed and
minimal — an agent can only touch the tools listed for it.

### 4.0 Orchestration

| Agent | Role | Toolkit |
| --- | --- | --- |
| `lead-strategist` | Main agent: plans, decides which/how many subagents to run, owns budget + dedup + status | task-dispatch, budget-ledger, findings-store, status-board |

### 4.1 Recon

| Agent | Role | Toolkit |
| --- | --- | --- |
| `framework-fingerprinter` | Detect language / framework / versions | fs.read, fs.glob, deps.manifest |
| `attack-surface-mapper` | Enumerate endpoints, routes, input points | fs.grep, ast.parse, route-extract |
| `auth-surface-scout` | Locate auth / session / authz code paths | fs.grep, ast.parse |
| `data-flow-tracer` | Taint tracing: source → sink | ast.parse, dataflow.trace |
| `trust-boundary-cartographer` | Map where untrusted data crosses boundaries | ast.parse, fs.grep |

### 4.2 Static — per-vuln-class hunters

| Agent | Role | Toolkit |
| --- | --- | --- |
| `injection-hunter` | SQL / NoSQL / OS / LDAP injection | ast.parse, dataflow.trace, fs.grep |
| `xss-analyst` | Reflected / stored / DOM XSS | ast.parse, fs.grep |
| `ssrf-hunter` | Server-side request forgery | dataflow.trace, fs.grep |
| `deserialization-analyst` | Insecure deserialization | ast.parse, fs.grep |
| `path-traversal-hunter` | Path traversal / LFI / RFI | dataflow.trace |
| `ssti-hunter` | Server-side template injection | ast.parse, fs.grep |
| `auth-logic-breaker` | Broken authz, IDOR, privilege escalation | ast.parse, fs.grep |
| `business-logic-adversary` | Workflow bypass, price / quantity tampering (zero-day class) | ast.parse, dataflow.trace |
| `race-condition-theorist` | TOCTOU / race conditions | ast.parse |
| `crypto-misuse-auditor` | Weak crypto, JWT alg confusion, IV reuse | fs.grep, ast.parse |
| `misconfig-auditor` | Debug endpoints, permissive CORS, exposed config | fs.read, fs.grep |
| `file-upload-analyst` | Unrestricted upload, content-type bypass | ast.parse |

### 4.3 Frontend / JS (deep phase)

| Agent | Role | Toolkit |
| --- | --- | --- |
| `bundle-archaeologist` | Resolve source maps, unpack bundles, extract hidden endpoints / keys | sourcemap.unpack, fs.read, entropy.scan |
| `dom-xss-hunter` | Client-side JS sink / source analysis | ast.parse (js), fs.grep |
| `browser-detonator` | Headless-browser runtime: DOM XSS, postMessage, prototype pollution | browser.headless (egress-locked), http.probe |
| `supply-chain-inspector` | SCA: vulnerable deps, typosquats, malicious install scripts | deps.audit, lockfile.parse |
| `framework-specialist` | Next / React / Vue: server actions, hydration, `NEXT_PUBLIC_*` leaks | ast.parse, fs.grep |
| `client-secret-forager` | API keys / tokens / flags shipped to the client | fs.grep, entropy.scan, sourcemap.unpack |

### 4.4 Dynamic (Phase 2 — egress-locked)

| Agent | Role | Toolkit |
| --- | --- | --- |
| `env-conductor` | Bring the app up in an isolated Docker network **or attach to a running target** (`--target URL`), health-check | docker.up, docker.exec, net.egress_guard |
| `harmless-prober` | Safe verification payloads (timing, boolean, reflection) | http.probe (egress-locked) |
| `exploit-smith` | PoC + bypass/evasion tests — gated behind `--aggressive` + confirmation | http.probe, browser.headless, audit.log |
| `escape-watchdog` | Kill the scan if any out-of-scope request is attempted | net.egress_guard, kill.signal |

### 4.5 Verification (double-voting)

| Agent | Role | Toolkit |
| --- | --- | --- |
| `red-verifier` | Independently tries to **prove** the finding is real | fs.read, http.probe, ast.parse |
| `blue-refuter` | Independently tries to **disprove** it (false-positive killer) | fs.read, ast.parse |
| `arbiter` | Reconciles red vs blue → confirmed / suspected / rejected + confidence | findings-store |
| `reproducer` | Captures a minimal reproducible PoC (request / response) for confirmed findings | http.probe, capture |

### 4.6 Support / cross-cutting

| Agent | Role | Toolkit |
| --- | --- | --- |
| `egress-redactor` | Aggressive secret / PII redaction on everything before it leaves to a provider | redact, entropy.scan |
| `injection-warden` | Data-fences untrusted file content; watches for prompt-injection in scanned code | fence, anomaly.detect |
| `severity-scorer` | CVSS + confidence scoring, dedup | findings-store |
| `report-scribe` | Writes per-finding Markdown into `Reasonhound/` plus the index | report.write, fs.write |
| `budget-quartermaster` | Tracks tokens / $ per agent, enforces hard caps | budget-ledger |
| `status-broadcaster` | Drives the live TUI (who / where / how many) and handles user stop | status-board, ipc |

## 5. Reasoning & confidence — the differentiator

A fixed-rule scanner cannot chase a hunch. Reasonhound's edge is a
**hypothesize → investigate → reflect → pivot** loop *plus* an adversarial
verification stage.

### 5.1 Hypothesis loop (per hunter)

1. **Hypothesize** from a candidate produced by `static`.
2. **Investigate** using the agent's toolkit.
3. **Judge**: promising → emit a hypothesis; inconclusive → write *why* and pivot.
4. **Pivot** into a fresh angle. Bounded by a **round / token budget** so it
   always terminates.

### 5.2 Double-voting (how a finding becomes "confirmed")

Every hypothesis goes through two independent agents before it can be trusted:

- `red-verifier` argues it **is** exploitable.
- `blue-refuter` argues it **is not** (catches false positives).
- `arbiter` weighs both and assigns a status + confidence:
  - **confirmed** — survived refutation (and, when the dynamic phase runs, a
    harmless probe backed it up).
  - **suspected** — plausible but not proven.
  - **rejected** — refuted; kept in the trace with the reason.

Findings are scored on two axes: **severity (CVSS)** × **confidence**. Every
finding carries the full reasoning trail (red / blue / arbiter), so results are
auditable.

### 5.3 Static engine — hybrid

`static` is **tree-sitter + LLM**. tree-sitter deterministically extracts
structure and candidate sinks across languages (Python / JS / TS / Go / …); the
LLM interprets meaning and exploitability. Languages without a grammar fall back
to regex heuristics.

## 6. Providers (BYOK)

All four providers work from day one, behind one `LLMProvider` interface.
Adapters are written directly against each provider's HTTP API using **`httpx`**
(no heavy vendor SDKs), which keeps the base install light and gives us direct
control over streaming for the live TUI.

| Provider | Environment variable |
| --- | --- |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GEMINI_API_KEY` |
| Ollama (local, no key) | — |

Never send user code to a provider the user did not explicitly select.

## 7. Security model (hard constraints)

Reasonhound scans untrusted code and can talk to a running app, so it treats
both as hostile input.

- **Egress redaction (always on):** `egress-redactor` masks secrets / tokens /
  PII (regex + entropy) before *anything* is sent to a provider. This is a base
  layer and cannot be disabled.
- **Prompt-injection defense (defense-in-depth):** scanned code is, by
  definition, untrusted input to the reasoning LLM. Three layers together:
  1. **Data-fencing** — file content is always wrapped as untrusted data and
     never interpreted as instructions.
  2. **Tool-restricted agents** — each agent can only call its allowlisted
     tools; there is no file → network exfiltration path.
  3. **Strict JSON schema** — agents return validated schemas, not free-form
     text or commands.
- **Dynamic phase is egress-locked:** the target runs in an **isolated Docker
  network with egress closed**. Probes reach only the target; `escape-watchdog`
  kills the scan if an out-of-scope request is attempted. Docker-absent fallback
  restricts probes to localhost / the target port. The tool can also **attach to
  an app the developer is already running on localhost** (`--target URL`),
  skipping bring-up; `escape-watchdog` scopes probing to that origin, and because
  the target is a real local process it stays safe-by-default unless
  `--aggressive` is confirmed.
- **Safe by default:** probes prove exploitability without destroying data
  (timing deltas, error-shape differences, reflected markers).
- **Stealth / evasion is gated:** WAF / monitoring-bypass testing (the "does my
  defense catch this?" question) lives behind `--aggressive` + explicit
  confirmation, and every such action is written to the audit log. It is not a
  general-purpose evasion capability.
- **Keys from the environment only**, never logged, never written to disk.
- **Audit log:** every probe sent is recorded in `Reasonhound/audit.log` for
  accountability.

## 8. Rules of engagement (keeping the agents bounded)

- **Hard budget + timeout:** token / $ / wall-clock caps; on breach the scan
  stops and writes a partial report. Default cap ≤ $5 per run.
- **Round / depth limit:** a maximum number of probes per hypothesis, so no
  agent loops forever.
- **Concurrency:** ~4–6 subagents run in parallel, aware of provider rate
  limits.
- **Approval gates:** aggressive / destructive steps prompt in-TUI before
  running.
- **Kill-switch:** the user can pause, kill one agent, or kill all from the
  terminal at any time; a clean shutdown still writes what was collected.

## 9. Output — the `Reasonhound/` folder

Instead of one file, findings are written into a `Reasonhound/` folder at the
project root, one Markdown file per finding (skill-style):

```
Reasonhound/
├── INDEX.md                       # summary table, severity-sorted, links to each finding
├── findings/
│   ├── 001-critical-sqli-api-search.md
│   ├── 002-high-idor-users-id.md
│   └── …
└── audit.log                      # every probe sent (accountability)
```

Each finding file contains: title · status (confirmed / suspected / rejected) ·
severity + CVSS · confidence · location (`file:line`) · data-flow · PoC
(request / response) · remediation · the red / blue / arbiter reasoning · the
agent that found it · timestamp.

**Re-run behavior — smart merge:** on a repeat scan, an existing finding is
updated in place (status / timestamp), new findings are added, and findings that
no longer reproduce are marked **resolved**. History is preserved rather than
overwritten.

## 10. Cross-platform

Pure Python 3.11+, `pathlib` throughout, no OS-specific shell assumptions. The
Textual TUI, Docker CLI bridge, and `httpx` adapters are all uniform across
macOS / Windows / Linux. (No ML/torch dependency, so the CUDA → MPS → CPU device
rule does not apply.)

## 11. Packaging & distribution

- `pyproject.toml`, published to **PyPI** as `reasonhound`; release automated via
  **GitHub Actions** on tag push. No server, no domain, no deploy.
- Recommended install is **`pipx`** (isolated env, global `reasonhound`
  command). Heavy dependencies are split into **optional extras** so the base
  install stays light:

| Install | Gets you |
| --- | --- |
| `pipx install reasonhound` | base: static phase + TUI (typer, questionary, textual, httpx, tree-sitter, pydantic) |
| `pipx install "reasonhound[dynamic]"` | + Docker bring-up for Phase 2 |
| `pipx install "reasonhound[frontend]"` | + Playwright headless browser (`browser-detonator`, DOM XSS) |
| `pipx install "reasonhound[all]"` | everything |

The base CLI warns and points at the right extra when a phase needs it.

## 12. Testing

- `pytest` with mocked providers for `static` / agents / `verify`.
- A deliberately-vulnerable sample app under `tests/fixtures/` as the
  end-to-end target for the dynamic phase.
- `ruff check` + `ruff format --check` clean in CI.

## 13. Open questions / future

- Optional SARIF output + CI exit codes (deferred; Markdown is the day-one
  output).
- Baseline / suppression file (`.reasonhound-ignore`) for accepted findings.
- Diff / changed-files scan mode for PRs (whole-repo is the default).
- Per-role model assignment (currently the orchestrator picks; per-role BYOK is a
  future option).
- Growing the subagent library beyond the initial 35.
