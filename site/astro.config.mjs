// @ts-check
import { defineConfig } from 'astro/config';
import sitemap from '@astrojs/sitemap';

// `site` is required by the sitemap integration and for canonical / OG URLs: the
// Vercel production address. `base` is the sub-path the page lives at; if the page
// ever moves under a hub site, set both together and every asset path follows
// (see src/lib/base.ts).
export default defineConfig({
    site: 'https://reasonhound-yigtwx.vercel.app',
    base: '/',
    output: 'static',
    integrations: [sitemap({ filter: (page) => !/\/social\/?$/.test(page) })],
    build: { inlineStylesheets: 'auto' },
});
