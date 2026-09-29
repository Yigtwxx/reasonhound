/* Writes the favicon set from one drawing: a paw print in paper on an ember
   square with rounded, transparent corners (Safari draws a light hairline around
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
<path d="M32 30c-7 0-14 8.5-14 15 0 4.5 3.6 6.5 7.5 6.5 2.8 0 4.4-1.4 6.5-1.4s3.7 1.4 6.5 1.4c3.9 0 7.5-2 7.5-6.5 0-6.5-7-15-14-15z"/>
<ellipse cx="15" cy="27" rx="4.6" ry="6" transform="rotate(-24 15 27)"/>
<ellipse cx="25" cy="16.5" rx="4.8" ry="6.6" transform="rotate(-8 25 16.5)"/>
<ellipse cx="39" cy="16.5" rx="4.8" ry="6.6" transform="rotate(8 39 16.5)"/>
<ellipse cx="49" cy="27" rx="4.6" ry="6" transform="rotate(24 49 27)"/>
</g>
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
