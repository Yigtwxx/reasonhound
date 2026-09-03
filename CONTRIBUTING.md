# Contributing to Reasonhound

Thanks for your interest! Reasonhound is in **pre-alpha** — the CLI skeleton
exists, but the scan pipeline (`recon`, `static`, `brain`, `dynamic`, `report`)
is still to be built. Early feedback on the design is very welcome.

## Ways to help right now

- Review the [design document](docs/DESIGN.md) and open an issue with feedback.
- Suggest vulnerability classes or reasoning strategies the `brain` loop should
  cover.
- Propose additional BYOK providers.

## Development setup

```bash
git clone https://github.com/Yigtwxx/reasonhound.git
cd Reasonhound
uv venv --python 3.11            # or: python3.11 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
uv pip install -e ".[dev]"       # or: pip install -e ".[dev]"

ruff check . && ruff format --check . && pytest
```

## Ground rules

- **Language:** all code, identifiers, and comments in **English**.
- **Cross-platform:** must work on macOS, Windows, and Linux. Use `pathlib`.
- **Security:** never hard-code or log secrets. Keys come from the environment.
- **Style:** format and lint with `ruff` (`ruff check` + `ruff format`).
- **Tests:** add/keep `pytest` coverage; keep the suite green.
- **Type hints:** required on all public functions.

## Commit messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short summary>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`. Keep the subject
under 72 characters and use the imperative mood ("add", not "added").

## Pull requests

1. Fork and branch from `main`.
2. Make focused changes with tests.
3. Ensure `ruff` and `pytest` pass.
4. Open a PR describing **what** changed and **why**.

By contributing you agree your work is licensed under the project's
[MIT License](LICENSE).
