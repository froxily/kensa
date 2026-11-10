'use strict';

const region = process.env.IMPALA_MANIFEST_REGION;
if (!region) {
  console.error('IMPALA_MANIFEST_REGION is required');
  process.exit(1);
}
console.log(`Manifest region: ${region}`);
