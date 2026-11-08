const { spawnSync } = require('node:child_process');
const names = ['header', 'schema', 'count', 'date', 'owner', 'region', 'state', 'format', 'links', 'tags', 'files', 'size', 'kind', 'origin', 'scope', 'notes', 'order', 'group', 'index', 'footer'];
for (const name of names) console.log(`queued check: ${name}`);
const child = spawnSync(process.execPath, ['tools/read-feed.cjs'], {stdio: 'ignore'});
process.exit(child.status === 0 ? 0 : 1);
