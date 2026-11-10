const test = require('node:test');
const assert = require('node:assert/strict');
const { region } = require('../src/settings');

test('dispatch region is normalized', () => {
  assert.equal(region.toLowerCase(), region);
});
