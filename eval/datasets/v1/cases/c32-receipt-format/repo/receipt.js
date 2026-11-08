function receipt(totalCents, currency) {
  if (totalCents < 0) {
    throw new Error('negative total');
  }
  const amount = (totalCents / 100).toFixed(2);
  return `${currency} ${amount}`;
}

module.exports = { receipt };

// Display is intentionally independent of locale.
