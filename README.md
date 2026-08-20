# Reasonhound

> AI-assisted security scanner that reasons like a senior researcher — it forms hypotheses, tests them, and when it comes up empty it *rethinks* and tries a different angle, instead of running a fixed checklist.

<p align="center">
  <em>Point it at your own web/API project. It reads the code, optionally spins the app up, hunts for vulnerabilities — including logic and zero-day-class issues — and writes a Markdown report to your project root.</em>
</p>

<p align="center">
  <strong>Status:</strong> 🚧 Pre-alpha — documentation & design only. No code yet.
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

```
$ reasonhound scan

? Which AI should do the reasoning?   › Anthropic (Claude) / OpenAI / Google Gemini / Ollama (local)
? How should I scan?                  › Code only (static)  /  Bring the app up end-to-end (dynamic)

⚙  Deep scan running…  [senior reasoning loop]
✔  Report written → ./REASONHOUND-FINDINGS.md
```

Two phases, run in order:

| Phase | What it does |
| --- | --- |
| **1 · Static** | Reads the source, maps frameworks, endpoints and input points, traces data flow, and produces vulnerability hypotheses. |
| **2 · Dynamic** *(optional)* | Brings the target app up in **Docker** (or locally if Docker is absent) and confirms hypotheses with **harmless** probes — never destructive payloads by default. |

Findings are collected, ranked by severity, and written to `REASONHOUND-FINDINGS.md` in your project root.

## Bring Your Own Key (BYOK)

Reasonhound ships **no model and no API key**. On first run it asks which provider you want and reads your key from the environment:

| Provider | Environment variable |
| --- | --- |
| Anthropic (Claude) | `ANTHROPIC_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Google Gemini | `GEMINI_API_KEY` |
| Ollama (local, no key) | — |

Your key stays on your machine, is read only from the environment, and is **never logged or written to disk**.

## Install (planned)

```bash
pip install reasonhound
```

Cross-platform by design — pure Python, developed on macOS, runs on **macOS, Windows, and Linux**. Docker is optional and only used for the dynamic phase.

## Usage (planned)

```bash
# Interactive: asks provider + scan mode
reasonhound scan

# Non-interactive
reasonhound scan ./my-app --provider anthropic --mode static
reasonhound scan ./my-app --provider ollama  --mode dynamic --budget 40

# Safe by default; aggressive exploitation is opt-in and gated behind confirmation
reasonhound scan ./my-app --mode dynamic --aggressive
```

## ⚠️ Authorized use only

Reasonhound is a **defensive** tool for testing systems **you own or are explicitly authorized to test**. Scanning or attacking systems without permission is illegal in most jurisdictions.

- The **dynamic** phase defaults to **safe verification** — it proves a hypothesis without destroying data (e.g. a timing difference, not `DROP TABLE`).
- **Aggressive** exploitation (`--aggressive`) is opt-in, gated behind explicit confirmation, and meant for disposable/backed-up environments.
- You are responsible for how you use this tool. See [`SECURITY.md`](SECURITY.md).

## Roadmap

- [ ] CLI skeleton & interactive prompts
- [ ] BYOK provider abstraction (Anthropic / OpenAI / Gemini / Ollama)
- [ ] `recon`: framework & endpoint discovery
- [ ] `static`: data-flow hypothesis engine
- [ ] `brain`: senior reasoning loop (tool-use agent)
- [ ] `dynamic`: Docker bring-up + safe probing
- [ ] `report`: Markdown findings writer
- [ ] Deliberately-vulnerable sample app for end-to-end tests

## Contributing

Contributions are welcome once the code skeleton lands. See [`CONTRIBUTING.md`](CONTRIBUTING.md) and our [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## License

[MIT](LICENSE) © Yigit Erdogan
