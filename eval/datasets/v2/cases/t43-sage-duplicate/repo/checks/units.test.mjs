import { test } from 'node:test';
import assert from 'node:assert/strict';
import { centimeters } from '../lib/units.mjs';

test('whole unit', () => assert.equal(centimeters(1), 100));
test('zero unit', () => assert.equal(centimeters(0), 0));
test('half unit', () => assert.equal(centimeters(0.5), 50));
test('two units', () => assert.equal(centimeters(2), 200));
test('negative unit', () => assert.equal(centimeters(-1), -100));
test('quarter unit', () => assert.equal(centimeters(0.25), 25));
