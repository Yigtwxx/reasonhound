/* Types each file reference ("File 04", "Exhibit A") onto the page as its
   section comes into view, the way a clerk labels a folder: uneven keystrokes
   behind a block caret that blinks out once the label is done. Screen readers
   get the whole label from a hidden copy; the typed one is aria-hidden. Without
   the script, or with less motion asked for, the label is simply there. */

const KEY_MS = [38, 92] as const; // a typist's rhythm, not a metronome
const CARET_LINGER_MS = 900;

export function initTypedExhibits(): void {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if (!('IntersectionObserver' in window)) return;
    const labels = Array.from(document.querySelectorAll<HTMLElement>('.exhibit'));
    if (labels.length === 0) return;

    const typed = new Map<HTMLElement, HTMLElement>();
    for (const label of labels) {
        const text = label.textContent?.trim() ?? '';
        if (!text) continue;
        const spoken = document.createElement('span');
        spoken.className = 'visually-hidden';
        spoken.textContent = text;
        const shown = document.createElement('span');
        shown.className = 'exhibit__typed';
        shown.setAttribute('aria-hidden', 'true');
        shown.dataset.text = text;
        label.replaceChildren(spoken, shown);
        typed.set(label, shown);
    }

    const type = (shown: HTMLElement): void => {
        const text = shown.dataset.text ?? '';
        shown.classList.add('is-typing');
        let i = 0;
        const next = (): void => {
            i += 1;
            shown.textContent = text.slice(0, i);
            if (i < text.length) {
                window.setTimeout(next, KEY_MS[0] + Math.random() * (KEY_MS[1] - KEY_MS[0]));
            } else {
                window.setTimeout(() => shown.classList.remove('is-typing'), CARET_LINGER_MS);
            }
        };
        next();
    };

    const observer = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                const label = entry.target as HTMLElement;
                const shown = typed.get(label);
                if (shown) type(shown);
                observer.unobserve(label);
            }
        },
        { threshold: 1, rootMargin: '0px 0px -12% 0px' },
    );
    for (const label of typed.keys()) observer.observe(label);
}
