/* Where the trail goes cold: the known limits, as the README states them. */
export interface Limit {
    title: string;
    body: string;
}

export const limits: readonly Limit[] = [
    {
        title: 'A language without a grammar gets a weaker nose.',
        body: 'Tree-sitter structure covers Python, JavaScript, TypeScript, Go, Java, PHP and Ruby. Anything else falls back to *regex heuristics*, and its findings say so.',
    },
    {
        title: 'Static alone stops at SUSPECTED.',
        body: 'Without Docker or a running app (--target), nothing is probed. The double vote still runs, but a finding that no request backed up is capped at *suspected*.',
    },
    {
        title: 'It will not log in for you.',
        body: 'Routes behind SSO or MFA need a session you provide in .reasonhound.toml. Without one, probes stop at the login page and the report *lists the routes it could not reach*.',
    },
    {
        title: 'A budget ends a hunt, not a codebase.',
        body: 'Twenty rounds on a large monorepo is a sample. The INDEX names the areas *no agent visited*, so an empty report on a partial hunt never reads as a clean bill.',
    },
    {
        title: 'Two runs can take two trails.',
        body: 'Model reasoning is not deterministic. Smart merge keeps confirmed findings stable across runs, but the order of the hunt and *some suspects* differ between them.',
    },
    {
        title: 'Docker, Ollama and browsers are separate installs.',
        body: 'The one pip install carries every phase, but not the Docker engine, an Ollama server or Playwright’s browsers. Preflight names *what is missing* and what it costs you.',
    },
];
