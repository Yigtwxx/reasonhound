/* Loads a plate's `dense` variant the first time a pointer rests on it.

   The dense print is only ever seen under a hovering pointer, yet it used to be
   fetched for every plate the reader scrolled past -- about half of the page's
   image bytes, and all of it wasted on a touch screen. It now carries its sources
   in `data-src`/`data-srcset` (Halftone.astro) and gets them here, on the first
   hover; `has-dense` turns the cross-fade on once it has loaded, so a slow
   network never fades in an empty frame. */

export function initHalftoneHover(): void {
    if (!window.matchMedia('(hover: hover)').matches) return;
    document.addEventListener(
        'pointerover',
        (event) => {
            const frame = (event.target as Element | null)?.closest?.('.halftone--hover');
            if (!frame || frame.classList.contains('has-dense')) return;
            const dense = frame.querySelector<HTMLImageElement>('.halftone__img--dense');
            if (!dense || dense.getAttribute('srcset')) return;
            dense.addEventListener('load', () => frame.classList.add('has-dense'), {
                once: true,
            });
            dense.srcset = dense.dataset.srcset ?? '';
            dense.src = dense.dataset.src ?? '';
        },
        { passive: true },
    );
}
