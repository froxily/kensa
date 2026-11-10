const test = require('node:test');
const assert = require('node:assert/strict');
const { label } = require('./src/label');

test('trims a label', () => assert.equal(label('  north  '), 'north'));
