/* A hunt, replayed: `reasonhound scan ./shop-api` on a small FastAPI shop, in
   `--plain` rendering so it fits a page. The wizard's five steps, then the pack
   at work, then the verdicts. A frame either appends a line or, when it names an
   `id` that already exists, replaces that line — that is how an agent's status
   line changes while it works. The banner above the output is static. */
import { version } from './commands';

export type Tone =
    | 'ok'
    | 'warn'
    | 'bad'
    | 'dim'
    | 'accent'
    | 'plain'
    | 'red'
    | 'blue'
    | 'stamp-bad'
    | 'stamp-warn'
    | 'stamp-dim';

export interface Span {
    text: string;
    tone?: Tone;
}

export interface Frame {
    /** Milliseconds to wait before this frame lands. */
    wait: number;
    /** Lines with the same id replace each other. */
    id?: string;
    /** `type` frames are typed character by character. */
    type?: boolean;
    /** Where a case note beside the run may point: `name` opens its span of lines,
     *  `name-end` closes it (`data-note-for` on the note). */
    anchor?: string;
    spans: Span[];
}

/**
 * The banner: REASONHOUND in the TUI's block letters (`█` for the letters,
 * `╗╔═╝║╚` for their shadow). The page draws the cells as an SVG rather than as
 * text, because block and box-drawing glyphs leave gaps between lines in a
 * browser font.
 */
export const WORDMARK_BLOCK = '█';
export const wordmark: readonly string[] = [
    '██████╗ ███████╗ █████╗ ███████╗ ██████╗ ███╗   ██╗██╗  ██╗ ██████╗ ██╗   ██╗███╗   ██╗██████╗ ',
    '██╔══██╗██╔════╝██╔══██╗██╔════╝██╔═══██╗████╗  ██║██║  ██║██╔═══██╗██║   ██║████╗  ██║██╔══██╗',
    '██████╔╝█████╗  ███████║███████╗██║   ██║██╔██╗ ██║███████║██║   ██║██║   ██║██╔██╗ ██║██║  ██║',
    '██╔══██╗██╔══╝  ██╔══██║╚════██║██║   ██║██║╚██╗██║██╔══██║██║   ██║██║   ██║██║╚██╗██║██║  ██║',
    '██║  ██║███████╗██║  ██║███████║╚██████╔╝██║ ╚████║██║  ██║╚██████╔╝╚██████╔╝██║ ╚████║██████╔╝',
    '╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝ ╚═════╝ ╚═╝  ╚═══╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚═╝  ╚═══╝╚═════╝ ',
];
export const WORDMARK_COLUMNS = Math.max(...wordmark.map((line) => line.length));
/** The TUI's five gradient bands, left to right: amber into ember. */
export const WORDMARK_BANDS = ['#f5b301', '#f09a05', '#e67a07', '#d05a09', '#b53a0a'] as const;
/** The shadow glyphs and the rule under the banner. */
export const WORDMARK_SHADOW = '#6e2605';

/** The two text lines beside or under the mark, as the TUI shows them at start. */
export const banner = {
    version: `reasonhound v${version}`,
    context: 'anthropic · claude-opus-5 · dynamic',
    hint: 'follows the scent, not the checklist.',
    commands: '[p]ause  [k]ill  [f]indings  [q]uit',
} as const;

const step = (n: number, name: string, detail: Span[]): Span[] => [
    { text: `[${n}] `, tone: 'dim' },
    { text: name.padEnd(14) },
    ...detail,
];

const agent = (branch: string, name: string, doing: string, tone: Tone = 'plain'): Span[] => [
    { text: branch, tone: 'dim' },
    { text: name.padEnd(20), tone: 'accent' },
    { text: doing, tone },
];

export const frames: Frame[] = [
    {
        wait: 300,
        id: 'prompt',
        type: true,
        spans: [{ text: '$ ', tone: 'dim' }, { text: 'reasonhound scan ./shop-api' }],
    },
    {
        wait: 500,
        anchor: 'wizard',
        spans: step(0, 'Preflight', [
            { text: 'git ✓  docker ✓  ANTHROPIC_API_KEY ✓  ', tone: 'ok' },
            { text: 'FastAPI · 142 files', tone: 'plain' },
        ]),
    },
    {
        wait: 350,
        spans: step(1, 'Brain', [{ text: 'anthropic · claude-opus-5', tone: 'plain' }]),
    },
    {
        wait: 450,
        spans: step(2, 'Authorized', [
            { text: '✓ ', tone: 'ok' },
            { text: 'I own this system or am authorized to test it', tone: 'plain' },
        ]),
    },
    {
        wait: 350,
        spans: step(3, 'Scope', [
            { text: 'whole repo · redaction ON · budget 20 rounds · ≤ $5.00', tone: 'plain' },
        ]),
    },
    {
        wait: 350,
        anchor: 'wizard-end',
        spans: step(4, 'Plan', [
            { text: 'recon → hunters → verify → dynamic (egress-locked)', tone: 'plain' },
        ]),
    },
    { wait: 300, spans: [{ text: '─'.repeat(78), tone: 'dim' }] },
    {
        wait: 250,
        id: 'lead',
        anchor: 'pack',
        spans: agent('▸ ', 'lead-strategist', 'mapping the attack surface', 'plain'),
    },
    {
        wait: 250,
        id: 'a1',
        spans: agent('  ├ ', 'injection-hunter', 'waiting for recon', 'dim'),
    },
    {
        wait: 150,
        id: 'a2',
        spans: agent('  ├ ', 'auth-logic-breaker', 'waiting for recon', 'dim'),
    },
    {
        wait: 150,
        id: 'a3',
        anchor: 'pack-end',
        spans: agent('  └ ', 'red-verifier', 'idle', 'dim'),
    },
    {
        wait: 700,
        id: 'lead',
        anchor: 'pack',
        spans: agent('▸ ', 'lead-strategist', 'round 3/20 · 38 routes · 6 hypotheses'),
    },
    {
        wait: 350,
        id: 'a1',
        spans: agent('  ├ ', 'injection-hunter', 'tracing q → cursor.execute  users.py:48'),
    },
    {
        wait: 300,
        id: 'a2',
        spans: agent('  ├ ', 'auth-logic-breaker', 'reading middleware/auth.py'),
    },
    {
        wait: 900,
        id: 'a1',
        spans: agent('  ├ ', 'injection-hunter', '✗ users.py:48 does not hold', 'warn'),
    },
    {
        wait: 500,
        anchor: 'pivot',
        spans: [
            { text: '    ↳ reflect  ', tone: 'warn' },
            { text: 'ORM binds q (session.scalars) → pivot: raw SQL in export.py', tone: 'dim' },
        ],
    },
    {
        wait: 800,
        id: 'a1',
        spans: agent('  ├ ', 'injection-hunter', 'raw SQL: ORDER BY {sort}  export.py:112'),
    },
    {
        wait: 600,
        id: 'a3',
        anchor: 'pack-end',
        spans: agent('  └ ', 'red-verifier', 'probing GET /api/export?sort=…  (harmless)', 'plain'),
    },
    {
        wait: 900,
        id: 'lead',
        anchor: 'pack',
        spans: agent('▸ ', 'lead-strategist', 'round 9/20 · verifying 3 findings'),
    },
    { wait: 300, spans: [{ text: '─'.repeat(78), tone: 'dim' }] },
    {
        wait: 350,
        anchor: 'verdict',
        spans: [
            { text: '● ', tone: 'bad' },
            { text: ' CONFIRMED ', tone: 'stamp-bad' },
            { text: '  critical 9.1  SQLi   export.py:112     /api/export?sort=', tone: 'plain' },
        ],
    },
    {
        wait: 200,
        spans: [
            { text: '     red  ', tone: 'red' },
            { text: 'sort=(CASE WHEN 1=1 THEN pg_sleep(2) END) → +2.04 s, 5/5', tone: 'dim' },
        ],
    },
    {
        wait: 200,
        spans: [
            { text: '     blue ', tone: 'blue' },
            { text: 'no allowlist, no bind on the raw path; could not refute', tone: 'dim' },
        ],
    },
    {
        wait: 350,
        spans: [
            { text: '○ ', tone: 'warn' },
            { text: ' SUSPECTED ', tone: 'stamp-warn' },
            { text: '  high 7.5      IDOR   orders.py:61      /orders/{id}', tone: 'plain' },
        ],
    },
    {
        wait: 350,
        anchor: 'verdict-end',
        spans: [
            { text: '✗ ', tone: 'dim' },
            { text: ' REJECTED  ', tone: 'stamp-dim' },
            { text: '  medium        XSS    search.html:19    autoescape on', tone: 'dim' },
        ],
    },
    { wait: 300, spans: [{ text: '─'.repeat(78), tone: 'dim' }] },
    {
        wait: 250,
        anchor: 'security',
        spans: [
            { text: 'SECURITY ', tone: 'accent' },
            { text: 'egress LOCKED ✓  redaction ON ✓ (3 masked)  probes 14 harmless', tone: 'ok' },
        ],
    },
    {
        wait: 200,
        spans: [
            {
                text: '3 findings: 1 confirmed · 1 suspected · 1 rejected  → Reasonhound/INDEX.md',
                tone: 'plain',
            },
        ],
    },
    {
        wait: 150,
        anchor: 'security-end',
        spans: [{ text: '06:41 · $3.12 of $5.00 · 11 agents · exit 1', tone: 'dim' }],
    },
];
