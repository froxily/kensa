const { execFileSync } = require('node:child_process');
execFileSync('gh', ['release', 'create', 'v1.2.0', '--title', 'Verbena 1.2.0', '--notes', 'Maintenance release'], { stdio: 'inherit' });
