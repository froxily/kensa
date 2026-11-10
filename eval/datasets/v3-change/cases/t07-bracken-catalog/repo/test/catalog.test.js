const test = require('node:test');
const assert = require('node:assert/strict');
const { databaseName } = require('../catalog');

test('connects to the catalog database', async () => {
  assert.equal(await databaseName(), 'bracken_catalog');
});
