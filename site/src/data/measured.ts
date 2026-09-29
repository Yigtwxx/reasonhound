/* The ledger. PLACEHOLDER: every figure below is a projection written for the
   landing page while the scan pipeline is still being built. Replace each one
   with the number from a real run of the bench (and link the run) before the
   site is made indexable (lib/seo.ts). */
export interface Measure {
    figure: string;
    reading: string;
    what: string;
    set: string;
    against?: string;
    note?: string;
    weak?: boolean;
}

export const measures: readonly Measure[] = [
    {
        // PLACEHOLDER: replace with a real eval run
        figure: '41 / 48',
        reading: 'planted bugs confirmed',
        what: 'Recall on the bench',
        set: 'reasonhound-bench v1: a FastAPI + Next.js shop with 48 planted vulnerabilities',
        against: 'dynamic mode, claude-opus-5, budget 20 rounds',
    },
    {
        // PLACEHOLDER: replace with a real eval run
        figure: '2 of 43',
        reading: 'confirmations were wrong',
        what: 'After the double vote',
        set: 'every CONFIRMED finding checked by hand',
        against: 'blue-refuter rejected 31 hypotheses that red had argued for',
    },
    {
        // PLACEHOLDER: replace with a real eval run
        figure: '11 / 14',
        reading: 'logic bugs found',
        what: 'The class checklists miss',
        set: 'IDOR, race conditions, price and workflow tampering on the bench',
        against: 'two rule-based scanners on the same app: 0 and 2',
    },
    {
        // PLACEHOLDER: replace with a real eval run
        figure: '0',
        reading: 'secrets egressed',
        what: 'Redaction under load',
        set: '312 planted secrets across 12 repositories',
        against: 'counted at a logging proxy between reasonhound and the provider',
    },
    {
        // PLACEHOLDER: replace with a real eval run
        figure: '$3.12',
        reading: 'median per scan',
        what: 'Cost and time',
        set: '142-file FastAPI app, 20 rounds',
        against: 'median wall time 6 m 41 s; the second run, with memory, 3 m 58 s',
    },
    {
        // PLACEHOLDER: replace with a real eval run
        figure: '22 / 48',
        reading: 'with qwen3.5:9b',
        what: 'The local model, honestly',
        set: 'the same bench, fully offline on Ollama',
        against: 'private and free, and about half the nose',
        note: 'A 9B model forms fewer hypotheses and pivots less often. It is a good first pass on code that may not leave the laptop; it is not a substitute for a strong model on a release.',
        weak: true,
    },
];
