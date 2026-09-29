/* Lands each stamp when it scrolls into view. Stamps that share a parent land
   one after another, a beat apart, like a clerk working down a form. The
   stylesheet only hides a stamp under `html.js` and with motion allowed, so
   without this script every stamp is already on the page. */

const BEAT_MS = 140;

export function initStamps(): void {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const stamps = Array.from(document.querySelectorAll<HTMLElement>('[data-stamp]'));
    if (stamps.length === 0) return;
    if (!('IntersectionObserver' in window)) {
        for (const s of stamps) s.classList.add('is-stamped');
        return;
    }
    const observer = new IntersectionObserver(
        (entries) => {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                const el = entry.target as HTMLElement;
                const siblings = el.parentElement?.querySelectorAll('[data-stamp]') ?? [];
                const index = Array.prototype.indexOf.call(siblings, el);
                el.style.setProperty('--stamp-delay', `${Math.max(0, index) * BEAT_MS}ms`);
                el.classList.add('is-stamped');
                observer.unobserve(el);
            }
        },
        { threshold: 0.6, rootMargin: '0px 0px -8% 0px' },
    );
    for (const s of stamps) observer.observe(s);
}
