const test = require('node:test');
const assert = require('node:assert/strict');

function normalize(value) {
  return value.trim().replace(/\s+/g, ' ');
}

test('normalizes spacing', () => {
  assert.equal(normalize('  blue   sky  '), 'blue sky');
});
