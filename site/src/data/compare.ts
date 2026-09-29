/* The three ways to look for a vulnerability, side by side: a rule scanner
   (pattern-matching static analysis), a crawler (black-box dynamic scanning) and
   reasonhound. Each column is a kind of tool, not a named product, and the last
   rows say where the other two are the better choice. */

export interface Approach {
    id: 'rules' | 'crawler' | 'hound';
    name: string;
    kind: string;
}

export interface CompareRow {
    label: string;
    cells: Record<Approach['id'], string>;
    /** A row where the other tools win: set apart, not hidden. */
    fair?: boolean;
}

export const approaches: readonly Approach[] = [
    { id: 'rules', name: 'A rule scanner', kind: 'pattern-matching static analysis' },
    { id: 'crawler', name: 'A crawler', kind: 'black-box dynamic scanning' },
    { id: 'hound', name: 'reasonhound', kind: 'hypothesis, probe, verdict' },
];

export const rows: readonly CompareRow[] = [
    {
        label: 'Starts from',
        cells: {
            rules: 'a list of known patterns',
            crawler: 'a list of payloads and every input it can reach',
            hound: 'the code’s own data flow, and a guess about where it breaks',
        },
    },
    {
        label: 'When a lead goes nowhere',
        cells: {
            rules: 'no match, nothing said',
            crawler: 'the next payload',
            hound: 'writes down why, and pivots to the path next door',
        },
    },
    {
        label: 'Proof',
        cells: {
            rules: 'a line that matched',
            crawler: 'a response that looked wrong',
            hound: 'a harmless proof, re-run until it holds',
        },
    },
    {
        label: 'Before it reports',
        cells: {
            rules: 'nothing: triage is yours',
            crawler: 'nothing: triage is yours',
            hound: 'a second agent argues against it; an arbiter decides',
        },
    },
    {
        label: 'What you get',
        cells: {
            rules: 'a list of rule hits',
            crawler: 'a report of suspect requests',
            hound: 'one Markdown file per finding, with the reasoning, in your repo',
        },
    },
    {
        label: 'Better at',
        fair: true,
        cells: {
            rules: 'speed and breadth: every commit, in seconds',
            crawler: 'needs no source code at all',
            hound: 'logic flaws no rule has a name for',
        },
    },
    {
        label: 'Costs',
        fair: true,
        cells: {
            rules: 'seconds of CI',
            crawler: 'minutes to hours of traffic',
            hound: 'minutes, and your own model’s tokens',
        },
    },
];
