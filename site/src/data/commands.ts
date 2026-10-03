/* The install line, the CI surface and the links, as the README shows them. */
export interface Command {
    cmd: string;
    comment: string;
}

export const install: readonly { label: string; cmd: string }[] = [
    { label: 'pipx', cmd: 'pipx install reasonhound' },
    { label: 'uv', cmd: 'uv tool install reasonhound' },
    { label: 'pip', cmd: 'pip install reasonhound' },
];

/* The wizard's five questions answered as flags: the same hunt behind a pipe. */
export const ciCommands: readonly Command[] = [
    {
        cmd: 'reasonhound scan . --provider anthropic --authorized -y',
        comment: "the wizard's answers, as flags",
    },
    {
        cmd: 'reasonhound scan . --plain --format sarif --fail-on high',
        comment: 'SARIF for code scanning; exit 1 on a confirmed high',
    },
    {
        cmd: 'reasonhound scan . --diff origin/main',
        comment: 'only what this branch touched',
    },
    {
        cmd: 'reasonhound scan . --target http://localhost:8000',
        comment: 'attach to an app you already run, no Docker',
    },
    { cmd: 'reasonhound scan . --no-memory', comment: 'a run that remembers nothing' },
];

export const exitCodes: readonly { code: 0 | 1 | 2; meaning: string }[] = [
    { code: 0, meaning: 'clean: nothing confirmed at or above the fail-on level' },
    { code: 1, meaning: 'a confirmed finding at or above the fail-on level (high by default)' },
    { code: 2, meaning: 'the scan itself failed, or stopped PARTIAL' },
];

/* The GitHub Actions job the README ships. */
export const workflow = `name: reasonhound
on: [pull_request]
jobs:
  hunt:
    runs-on: ubuntu-latest
    permissions: { security-events: write }
    steps:
      - uses: actions/checkout@v5
        with: { fetch-depth: 0 }
      - run: pipx install reasonhound
      - run: reasonhound scan . --plain --authorized -y
               --diff origin/\${{ github.base_ref }}
               --format sarif --fail-on high
        env:
          ANTHROPIC_API_KEY: \${{ secrets.ANTHROPIC_API_KEY }}
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: Reasonhound/reasonhound.sarif }`;

export const version = '0.5.0';
export const repo = 'https://github.com/Yigtwxx/reasonhound';
export const pypi = 'https://pypi.org/project/reasonhound/';

/* The sibling tools: same family, same page. */
export const siblings: readonly { name: string; href: string; tag: string }[] = [
    {
        name: 'proofpath',
        href: 'https://proofpath-yigtwx.vercel.app',
        tag: 'checks that a citation says what the claim says',
    },
    {
        name: 'spiyweb',
        href: 'https://spiyweb.vercel.app',
        tag: 'retrieval that spreads through a graph, not top-k',
    },
];
