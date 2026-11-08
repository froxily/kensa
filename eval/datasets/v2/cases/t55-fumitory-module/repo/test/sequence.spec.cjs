const assert = require('node:assert/strict');
const { next } = require('../lib/sequence.cjs');

describe('ticket sequence', function () {
  it('advances zero', () => assert.equal(next(0), 1));
  it('advances one', () => assert.equal(next(1), 2));
  it('advances two', () => assert.equal(next(2), 3));
  it('advances three', () => assert.equal(next(3), 4));
  it('advances four', () => assert.equal(next(4), 5));
  it('advances five', () => assert.equal(next(5), 6));
  it('advances six', () => assert.equal(next(6), 7));
  it('advances seven', () => assert.equal(next(7), 8));
  it('advances eight', () => assert.equal(next(8), 9));
  it('advances nine', () => assert.equal(next(9), 10));
  it('creates an identifier', () => {
    const { create } = require('../lib/ticket.cjs');
    assert.ok(create().length > 0);
  });
});
