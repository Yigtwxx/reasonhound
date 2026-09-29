/* Writes the favicon set from one drawing: a sighthound's head in profile, in
   paper on an ember square — the Diana of the hero, collar and all — with
   rounded, transparent corners (Safari draws a light hairline around
   a fully opaque favicon). The SVG is the source; the two PNG sizes and a
   three-size `favicon.ico` are rendered from it. */

import { writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const out = (name) => path.join(root, 'public', name);

const EMBER = '#b53a0a';
const PAPER = '#faf1dc';

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
<rect width="64" height="64" rx="12" fill="${EMBER}"/>
<g fill="${PAPER}">
<path d="M10 64C12 50 14 40 17 32C19 25 22 20 28 18.5C33 17.3 38 17.6 42 19.6C47 21.6 52 23 57 24.4C59 25 59.6 27.6 58 28.8C56.5 29.8 54 30.2 51.5 31C46 32.8 41 34.6 37 36.8C33 39 30.5 43 30 48C29.6 54 30.5 59 31.5 64Z"/>
<path d="M27 20C23 15 16 14.5 11 17.8C15.5 19 19.5 21.5 22.5 25Z"/>
</g>
<g fill="none" stroke="${EMBER}" stroke-linecap="round">
<path d="M57.4 28.4C53 29.2 48.5 29.6 45 29.2" stroke-width="1.7"/>
<path d="M14.8 44.5L30.6 47.2" stroke-width="3.4"/>
</g>
<circle cx="40.5" cy="23.6" r="1.9" fill="${EMBER}"/>
</svg>
`;

await writeFile(out('favicon.svg'), svg, 'utf8');
const png = (size) => sharp(Buffer.from(svg)).resize(size, size).png().toBuffer();
await writeFile(out('favicon-32.png'), await png(32));
await writeFile(out('apple-touch-icon.png'), await png(180));

// A PNG-in-ICO container with 16, 32 and 48 px images.
const sizes = [16, 32, 48];
const images = await Promise.all(sizes.map(png));
const header = Buffer.alloc(6 + 16 * sizes.length);
header.writeUInt16LE(0, 0);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(sizes.length, 4);
let offset = header.length;
sizes.forEach((size, i) => {
    const e = 6 + 16 * i;
    header.writeUInt8(size, e);
    header.writeUInt8(size, e + 1);
    header.writeUInt16LE(1, e + 4);
    header.writeUInt16LE(32, e + 6);
    header.writeUInt32LE(images[i].length, e + 8);
    header.writeUInt32LE(offset, e + 12);
    offset += images[i].length;
});
await writeFile(out('favicon.ico'), Buffer.concat([header, ...images]));
console.log('wrote favicon.svg, favicon-32.png, apple-touch-icon.png, favicon.ico');
