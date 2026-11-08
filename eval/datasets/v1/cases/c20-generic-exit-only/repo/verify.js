const fs = require('node:fs');
const path = require('node:path');

const target = process.env.BUNDLE_PATH || path.join('dist', 'bundle.json');
try {
  const bundle = JSON.parse(fs.readFileSync(target, 'utf8'));
  if (!Array.isArray(bundle.entries)) throw new Error('entries must be an array');
  console.log(`Validated ${bundle.entries.length} entries`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
