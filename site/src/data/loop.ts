/* The four beats of the hunt, in the order the loop runs them. Each is a
   chapter on the page: the hound detail that stands for it, the agents that do
   the work, and a line from the demo run at that beat. */
import type { StampTone } from '../components/case/Stamp.astro';
import type { ImageId } from './images.generated';

export interface CaseNote {
    who?: 'red' | 'blue' | 'arbiter' | 'why' | 'next';
    text: string;
}

export interface CaseLine {
    status: string;
    tone: StampTone;
    severity?: string;
    cls: string;
    where: string;
    route?: string;
    notes?: readonly CaseNote[];
}

export interface Beat {
    n: 1 | 2 | 3 | 4;
    slug: string;
    verb: string;
    question: string;
    vignette: ImageId;
    vignetteNote: string;
    plate: ImageId;
    plateCaption: string;
    body: readonly string[];
    agents: readonly string[];
    example: CaseLine;
}

export const beats: readonly Beat[] = [
    {
        n: 1,
        slug: 'hypothesize',
        verb: 'Hypothesize',
        question: 'Where would I break this?',
        vignette: 'head',
        vignetteNote: 'The hound lifts its head before it lowers its nose.',
        plate: 'hollar',
        plateCaption: 'Wenceslaus Hollar, *Five hunting hounds*, 1647. Five noses, five theories.',
        body: [
            'Recon maps the ground first: the framework, every route, where user input enters, where the *trust boundaries* are. Then each hunter writes *hypotheses*, not pattern matches — "this endpoint builds a query from a request parameter; could it be injectable?"',
            'A hypothesis names its source, its sink and every file:line in between. Tree-sitter finds the *structure*; the model reads the *meaning* — the guard that looks like validation and is not.',
        ],
        agents: [
            'framework-fingerprinter',
            'attack-surface-mapper',
            'data-flow-tracer',
            'trust-boundary-cartographer',
        ],
        example: {
            status: 'hypothesis',
            tone: 'dim',
            cls: 'SQLi',
            where: 'users.py:48',
            route: 'GET /api/users?q=',
            notes: [{ who: 'why', text: 'request.q → f-string → cursor.execute, no bind seen' }],
        },
    },
    {
        n: 2,
        slug: 'probe',
        verb: 'Probe',
        question: 'Does it hold?',
        vignette: 'sniffer',
        vignetteNote: 'Nose down. It reads the code around the sink before it touches the app.',
        plate: 'stag-hunt',
        plateCaption:
            'Jan Collaert after Stradanus, *Stag hunt with hounds*, c. 1600. Every nose on a different trail.',
        body: [
            'The hunter follows the tainted value across files, reads every guard it passes, and asks whether each one *actually holds* for this input, on this path.',
            'With the dynamic phase on, the app comes up in an *egress-locked* Docker network — or is attached with --target — and the hypothesis gets one *harmless* request. A timing difference, not DROP TABLE.',
        ],
        agents: ['injection-hunter', 'auth-logic-breaker', 'ssrf-hunter', 'harmless-prober'],
        example: {
            status: 'suspected',
            tone: 'warn',
            severity: 'high 7.5',
            cls: 'IDOR',
            where: 'orders.py:61',
            route: 'GET /orders/{id}',
            notes: [
                { who: 'why', text: 'owner check reads order.user_id after the SELECT, not in it' },
            ],
        },
    },
    {
        n: 3,
        slug: 'reflect',
        verb: 'Reflect',
        question: "Why didn't it?",
        vignette: 'stare',
        vignetteNote: 'A dead end is written down, not thrown away.',
        plate: 'fyt',
        plateCaption:
            'Jan Fyt, *Landscape with Greyhound and Rifle*, 1642. The hound stops and turns its head.',
        body: [
            'When a hypothesis fails, the agent has to say *why*: "the ORM binds this parameter", "the middleware rejects non-owners". The reason is kept for the run, so the next round never sniffs the same bush twice.',
            'This is where the interesting findings start. The guard that holds on /users is *often missing on /export* — and only something that wrote the guard down goes looking for its absence.',
        ],
        agents: ['lead-strategist', 'injection-warden', 'severity-scorer'],
        example: {
            status: 'rejected',
            tone: 'dim',
            severity: 'medium',
            cls: 'SQLi',
            where: 'users.py:48',
            route: 'GET /api/users?q=',
            notes: [
                {
                    who: 'why',
                    text: 'q reaches execute() as a bound parameter via session.scalars',
                },
                { who: 'next', text: 'look for raw SQL near the same model: export.py' },
            ],
        },
    },
    {
        n: 4,
        slug: 'pivot',
        verb: 'Pivot',
        question: 'Where next?',
        vignette: 'chase',
        vignetteNote: 'Then it runs somewhere new.',
        plate: 'dasveldt',
        plateCaption:
            'Jan Dasveldt, *Hazewindhonden*, c. 1800. One rests and watches; the other is already off somewhere new.',
        body: [
            'The lead-strategist reads every reflection and opens a new angle: a sibling route, a raw-SQL path, a race between two requests, a business rule nobody wrote a test for.',
            'The loop runs until the *round and cost budget* is spent — never forever. A stopped run is not a wasted one: it returns *PARTIAL* with its reason, and everything found so far is written.',
        ],
        agents: [
            'lead-strategist',
            'business-logic-adversary',
            'race-condition-theorist',
            'budget-quartermaster',
        ],
        example: {
            status: 'confirmed',
            tone: 'bad',
            severity: 'critical 9.1',
            cls: 'SQLi',
            where: 'export.py:112',
            route: 'GET /api/export?sort=',
            notes: [
                { who: 'red', text: 'sort=(CASE WHEN 1=1 THEN pg_sleep(2) END) → +2.04 s, 5 of 5' },
                { who: 'blue', text: 'no allowlist, no bind on the raw path; could not refute' },
                { who: 'arbiter', text: 'confirmed · confidence high' },
            ],
        },
    },
];
