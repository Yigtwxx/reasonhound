# Reasonhound

> AI-assisted security scanner that reasons like a senior researcher — it forms hypotheses, tests them, and when it comes up empty it *rethinks* and tries a different angle, instead of running a fixed checklist.

<p align="center">
  <em>Point it at your own web/API project. It reads the code, optionally spins the app up, hunts for vulnerabilities — including logic and zero-day-class issues — and writes a Markdown report to your project root.</em>
</p>

<p align="center">
  <strong>Status:</strong> 🚧 Pre-alpha — CLI skeleton only; the scan pipeline is not implemented yet.
</p>

---

## Why another scanner?

Most scanners walk a static rule list: match a pattern, flag it, move on. They never ask *why* a piece of code might be exploitable, and they can't chase a hunch across files.

**Reasonhound is different.** Its core is a reasoning loop that behaves like a human security researcher:

1. **Hypothesize** — "this endpoint builds a query from user input; could it be injectable?"
2. **Probe** — read the surrounding code, trace the data flow, and (optionally) send a harmless test request to the running app.
3. **Reflect** — if the hypothesis doesn't hold, write down *why* and pivot: "not here — the ORM escapes it; let me look at the raw-SQL export path instead."
4. **Repeat** — open a new angle, bounded by a token/round budget so it never spins forever.

Every finding ships with the reasoning behind it. It's not a black box.

## How it works

The terminal is the UI. A guided wizard sets up the run, then a live monitor
shows the scan as it happens:

```
$ reasonhound scan

[0] Preflight     git ✓  Docker ✓  ANTHROPIC_API_KEY ✓  framework: FastAPI
[1] Brain         › Anthropic (Claude) / OpenAI / Google Gemini / Ollama (local)
[2] Authorization ▢ I own this system or am explicitly authorized to test it   (required)
[3] Scope         whole repo · ~142 files · redaction ON · budget ≤ $5.00
[4] Plan          recon → static hunters → verify …   [enter to start]

┌ Reasonhound ─ scanning ./my-app ───────────── ⏱ 02:14 ─ $0.38 / $5.00 ┐
│ ▸ lead-strategist   planning next     │ ● CONFIRMED  SQLi  /api/search  │
│   ├ injection-hunter  tracing sink    │ ○ suspected  IDOR  /users/:id   │
│   └ red-verifier      probing…        │ 12 confirmed · 8 susp · 20 rej  │
│ SECURITY egress: LOCKED ✓  redaction: ON ✓  probes: 14 (harmless)      │
│ [p]ause  [k]ill agent  [K]ill all  [q]uit                              │
└────────────────────────────────────────────────────────────────────────┘
```

Under the hood, a single **orchestrator** plans the scan and dispatches a library
of **~35 specialized subagents** — each with its own narrow toolkit. Two phases
run in order:

| Phase | What it does |
| --- | --- |
| **1 · Static** | Recon + per-vuln-class hunters read the source with a hybrid tree-sitter + LLM engine, trace data flow, and produce hypotheses. A frontend/JS deep phase resolves source maps, inspects the dependency supply chain, and (optionally) detonates client code in a headless browser. |
| **2 · Dynamic** *(optional)* | Brings the target app up in an **isolated, egress-locked Docker network**, or **attaches to an app you already run on localhost** (`--target URL`, no Docker needed), and confirms hypotheses with **harmless** probes — never destructive payloads by default. |

Before a finding is trusted it goes through **double-voting**: one agent tries to
prove it, another tries to disprove it, and an arbiter assigns a status
(confirmed / suspected / rejected) with a confidence and CVSS score.

Findings are written into a **`Reasonhound/`** folder in your project root — one
Markdown file per finding, plus an `INDEX.md` and an `audit.log` of every probe
sent. Re-running **smart-merges**: existing findings are updated, new ones added,
and findings that no longer reproduce are marked resolved.

See [`docs/DESIGN.md`](docs/DESIGN.md) for the full architecture and the subagent
library.

## Bring Your Own Key (BYOK)

Reasonhound ships **no model and no API key**. On first run it asks which provider you want and reads your key from the environment:

| Provider | Environment variable |
| --- | --- |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GEMINI_API_KEY` |
| Ollama (local, no key) | — |

Your key stays on your machine, is read only from the environment, and is **never logged or written to disk**.

## Install

Not on PyPI yet. Install from source (Python 3.11+):

```bash
git clone https://github.com/Yigtwxx/reasonhound.git
cd Reasonhound
uv venv --python 3.11 && uv pip install -e ".[dev]"   # or: pip install -e ".[dev]"
reasonhound --help
```

Once released, `pipx` is the recommended way (isolated env, global `reasonhound`
command). Heavy dependencies are optional extras, so the base install stays light:

```bash
pipx install reasonhound                 # base: static phase + live TUI
pipx install "reasonhound[dynamic]"      # + Docker bring-up for Phase 2
pipx install "reasonhound[frontend]"     # + headless browser (DOM XSS, bundle analysis)
pipx install "reasonhound[all]"          # everything
```

The base CLI warns and points you at the right extra when a phase needs it.

Cross-platform by design — pure Python, developed on macOS, runs on **macOS, Windows, and Linux**. Docker is optional and only used for the dynamic phase.

## Usage

The CLI below works today; it validates flags, checks your key is present, asks you to
confirm you are authorized to test the target, and persists your non-secret choices to
`.reasonhound.toml`. The actual scan pipeline lands in the next milestones.

```bash
# Interactive: asks provider + scan mode, then the authorization confirmation
reasonhound scan

# Non-interactive (CI): --authorized replaces the prompt and is never persisted
reasonhound scan ./my-app --provider anthropic --mode static --authorized
reasonhound scan ./my-app --provider ollama  --mode dynamic --budget 40 --authorized

# Safe by default; aggressive exploitation is opt-in and always confirmed
# interactively (no flag, including --yes, can skip that prompt)
reasonhound scan ./my-app --mode dynamic --aggressive
```

## ⚠️ Authorized use only

Reasonhound is a **defensive** tool for testing systems **you own or are explicitly authorized to test**. Scanning or attacking systems without permission is illegal in most jurisdictions.

- The **dynamic** phase defaults to **safe verification** — it proves a hypothesis without destroying data (e.g. a timing difference, not `DROP TABLE`).
- **Aggressive** exploitation (`--aggressive`) is opt-in, gated behind explicit confirmation, and meant for disposable/backed-up environments.
- You are responsible for how you use this tool. See [`SECURITY.md`](SECURITY.md).

## Roadmap

- [x] CLI skeleton & interactive prompts
- [ ] BYOK provider abstraction — four `httpx` adapters (Anthropic / OpenAI / Gemini / Ollama)
- [ ] `security`: egress redaction + prompt-injection defense (data-fencing, tool allowlists)
- [ ] `orchestrator` + `agents/`: the subagent library (~35 agents, own toolkits)
- [ ] `static`: hybrid tree-sitter + LLM data-flow / hypothesis engine
- [ ] `verify`: double-voting (prove / disprove / arbitrate) + reproducible PoC
- [ ] `dynamic`: egress-locked Docker bring-up + safe probing
- [ ] Frontend/JS deep phase: source maps, supply-chain, headless-browser detonation
- [ ] `tui`: Textual live monitor (agent tree, findings feed, budget, kill-switch)
- [ ] `report`: `Reasonhound/` folder writer (per-finding Markdown, smart merge)
- [ ] Deliberately-vulnerable sample app for end-to-end tests

## Contributing

Contributions are welcome once the code skeleton lands. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and our [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE) © Yigit Erdogan
