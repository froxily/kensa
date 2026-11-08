const { receipt } = require('./receipt');

test('formats a customer total', () => {
  expect(receipt(1299, 'USD')).toContain('12.99');
});

test('puts the currency before the amount without a gap', () => {
  expect(receipt(500, 'EUR')).toBe('EUR5.00');
});

// Currency codes are supplied by the caller.
