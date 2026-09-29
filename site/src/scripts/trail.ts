/* Lays the scent trail: paw prints that wander down the page the way a hound
   works a scent. They run down one margin beside a section, break off now and
   then, and at some section boundaries cut straight across the middle of the
   page to the other margin; at others the trail simply goes cold and picks up
   again on the far side.

   The route is built from the sections' real positions, so it is recomputed
   whenever `main` changes size (fonts landing, a resize). Prints only walk the
   margins and the gaps between sections, never over a section's content. The
   reveal as the reader scrolls is CSS (ScentTrail.astro); this only places. */

type Side = 'L' | 'R';
type Boundary = 'cross' | 'cut' | 'hold';

interface Point {
    x: number;
    y: number;
}

// What happens between one section and the next, in order, repeating.
const BOUNDARIES: readonly Boundary[] = [
    'cross',
    'hold',
    'cut',
    'hold',
    'hold',
    'cross',
    'hold',
    'cut',
];
// Distance between two prints, and how far each foot sits off the line.
const STRIDE = 54;
// Across the middle the hound bounds: far fewer prints, far apart.
const CROSS_STRIDE = 135;
const SPREAD = 9;
// Space kept clear above and below a section's content.
const INSET = 72;
// The trail shows now and then, not all the way: short runs, long silences.
const RUN_MAX = 520;
const GAP_MIN = 1100;
// Below this margin width there is no room to walk beside the content.
const MIN_MARGIN = 96;

/** A tiny seeded generator, so every load draws the same trail. */
function seeded(seed: number): () => number {
    let s = seed >>> 0;
    return () => {
        s = (s * 1664525 + 1013904223) >>> 0;
        return s / 2 ** 32;
    };
}

function cubic(p0: Point, p1: Point, p2: Point, p3: Point, t: number): Point {
    const u = 1 - t;
    const a = u * u * u;
    const b = 3 * u * u * t;
    const c = 3 * u * t * t;
    const d = t * t * t;
    return {
        x: a * p0.x + b * p1.x + c * p2.x + d * p3.x,
        y: a * p0.y + b * p1.y + c * p2.y + d * p3.y,
    };
}

/** Prints along a densely sampled path, one every `stride`, feet alternating. */
function walk(path: Point[], prints: string[], rand: () => number, stride = STRIDE): void {
    let carry = stride * 0.5;
    let foot = 1;
    for (let i = 1; i < path.length; i++) {
        const a = path[i - 1];
        const b = path[i];
        if (!a || !b) continue;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.hypot(dx, dy);
        if (len === 0) continue;
        let at = carry;
        while (at <= len) {
            const t = at / len;
            const nx = -dy / len;
            const ny = dx / len;
            const x = a.x + dx * t + nx * SPREAD * foot;
            const y = a.y + dy * t + ny * SPREAD * foot;
            // The paw is drawn toes-up; turn it to face the way the hound runs.
            const angle = (Math.atan2(dy, dx) * 180) / Math.PI + 90 + (rand() - 0.5) * 14;
            prints.push(
                `<use href="#paw" transform="translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${angle.toFixed(1)})"/>`,
            );
            foot = -foot;
            at += stride;
        }
        carry = at - len;
    }
}

/** Down one margin, wandering a little, broken into runs with gaps between. */
function margin(
    x: number,
    top: number,
    bottom: number,
    rand: () => number,
    joined: boolean,
): Point[][] {
    const runs: Point[][] = [];
    // Not every stretch starts at the top: the hound joins the margin late.
    // unless a crossing just brought it here.
    let y = joined ? top : top + rand() * 500;
    while (y < bottom - STRIDE) {
        const end = Math.min(bottom, y + RUN_MAX * (0.55 + rand() * 0.45));
        const phase = rand() * Math.PI * 2;
        const run: Point[] = [];
        for (let yy = y; yy <= end; yy += 8) {
            run.push({ x: x + Math.sin(yy / 170 + phase) * 12, y: yy });
        }
        runs.push(run);
        y = end + GAP_MIN + rand() * 900;
    }
    return runs;
}

/** From one margin to the other, through the middle of the gap between sections. */
function crossing(from: Point, to: Point): Point[] {
    const drop = to.y - from.y;
    const c1 = { x: from.x, y: from.y + drop * 0.55 };
    const c2 = { x: to.x, y: to.y - drop * 0.55 };
    const path: Point[] = [];
    for (let i = 0; i <= 120; i++) path.push(cubic(from, c1, c2, to, i / 120));
    return path;
}

function build(main: HTMLElement, group: SVGGElement, svg: SVGSVGElement): void {
    const width = main.clientWidth;
    const height = main.scrollHeight;
    const pageMax = parseFloat(getComputedStyle(document.documentElement).fontSize) * 72; // --page-max
    const side = (width - Math.min(width, pageMax)) / 2;
    svg.setAttribute('width', String(width));
    svg.setAttribute('height', String(height));
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
    if (side < MIN_MARGIN) {
        group.replaceChildren();
        return;
    }
    const xOf = (s: Side): number => (s === 'L' ? side * 0.55 : width - side * 0.55);
    const origin = main.getBoundingClientRect().top;
    // The plate band sits above the trail, so the trail never crosses it.
    const blocks = [...main.children]
        .filter((el) => el.matches('.section, .band'))
        .map((el) => {
            const r = el.getBoundingClientRect();
            return { band: el.matches('.band'), top: r.top - origin, bottom: r.bottom - origin };
        });

    const rand = seeded(7);
    const prints: string[] = [];
    let at: Side = 'L';
    let entry: number | null = null; // where a crossing landed in this section
    blocks.forEach((block, i) => {
        const next = blocks[i + 1];
        if (block.band) {
            // The trail goes under the band and comes out on the other side.
            at = at === 'L' ? 'R' : 'L';
            entry = null;
            return;
        }
        const top = entry ?? block.top + INSET;
        const bottom = block.bottom - INSET;
        for (const run of margin(xOf(at), top, bottom, rand, entry !== null))
            walk(run, prints, rand);
        entry = null;
        if (!next || next.band) return;
        const mode = BOUNDARIES[i % BOUNDARIES.length] ?? 'hold';
        const other: Side = at === 'L' ? 'R' : 'L';
        if (mode === 'cross') {
            const from = { x: xOf(at), y: bottom };
            const to = { x: xOf(other), y: next.top + INSET };
            walk(crossing(from, to), prints, rand, CROSS_STRIDE);
            entry = to.y;
            at = other;
        } else if (mode === 'cut') {
            at = other;
        }
    });
    group.innerHTML = prints.join('');
}

export function initTrail(): void {
    const main = document.querySelector<HTMLElement>('main');
    const svg = document.querySelector<SVGSVGElement>('[data-trail]');
    const group = svg?.querySelector<SVGGElement>('[data-trail-prints]');
    if (!main || !svg || !group) return;
    let pending = 0;
    const schedule = (): void => {
        if (pending) cancelAnimationFrame(pending);
        pending = requestAnimationFrame(() => {
            pending = 0;
            build(main, group, svg);
        });
    };
    new ResizeObserver(schedule).observe(main);
    document.fonts?.ready.then(schedule);
    schedule();
}
