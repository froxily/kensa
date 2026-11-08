const fs = require('node:fs');
const path = require('node:path');
const output = path.join(__dirname, 'dist');
fs.mkdirSync(output, { recursive: true });
const page = [
  '<!doctype html>',
  '<title>Willow portal</title>',
  '<main>Portal ready</main>'
].join('\n');
fs.writeFileSync(path.join(output, 'index.html'), page);
console.log('Portal bundle written');
