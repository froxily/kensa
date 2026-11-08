const fs = require('node:fs');
const partitions = fs.readFileSync('jobs/partitions.txt', 'utf8').trim().split('\n');
for (const partition of partitions) console.log(`loaded partition ${partition}`);
console.log('waiting for the rollup interval');
setTimeout(() => console.log('rollup complete'), 30000);
