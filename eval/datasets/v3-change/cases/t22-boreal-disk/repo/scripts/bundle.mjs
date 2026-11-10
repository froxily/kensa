import { mkdir, writeFile } from 'node:fs/promises';

await mkdir('dist', { recursive: true });
const records = Array.from({ length: 250000 }, (_, index) => ({
  index,
  label: `atlas-tile-${index}`,
}));
await writeFile('dist/atlas.json', JSON.stringify(records));
console.log(`Wrote ${records.length} records to dist/atlas.json`);
