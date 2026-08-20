# Security Policy

## Responsible & authorized use

Reasonhound is a **defensive security tool**. It is intended to help developers
find vulnerabilities in software **they own or are explicitly authorized to
test**.

Using this tool to scan, probe, or attack systems without the owner's explicit
permission is **illegal** in most jurisdictions and is **not** a supported use
case. By using Reasonhound you accept full responsibility for ensuring you have
authorization for every target you point it at.

### Built-in safeguards

- **Safe by default.** The dynamic phase uses *harmless verification* payloads
  that prove a hypothesis without destroying data (for example, observing a
  timing or error-response difference rather than executing `DROP TABLE`).
- **Aggressive mode is opt-in.** Real exploitation (`--aggressive`) is disabled
  by default, gated behind an explicit confirmation, and intended only for
  disposable or fully backed-up environments.
- **Isolation.** When Docker is available, the dynamic phase runs the target
  application inside a container so probing does not touch your host.
- **Authorized-use notice.** Every scan prints a reminder before it starts.

## Handling of secrets

- Reasonhound reads model API keys **only** from environment variables.
- Keys are **never** written to disk, logs, reports, or telemetry.
- The generated `REASONHOUND-FINDINGS.md` may contain sensitive details about
  your application. Treat it as confidential and keep it out of version control
  (it is already listed in `.gitignore`).

## Reporting a vulnerability in Reasonhound

If you discover a security issue in Reasonhound **itself**, please report it
privately rather than opening a public issue:

- Email: **yigiterdogan023@gmail.com**
- Or use GitHub's private **"Report a vulnerability"** feature under the
  Security tab.

Please include a description, reproduction steps, and impact. We aim to
acknowledge reports within a few days.

## Supported versions

Reasonhound is pre-alpha. Until a `1.0.0` release, only the latest commit on the
default branch is supported.
