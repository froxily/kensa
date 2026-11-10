import { describe, expect, it } from 'vitest';
import { mean } from '../src/mean';

describe('mean', () => {
  it('returns zero for no readings', () => {
    expect(mean([])).toBe(0);
  });

  it('returns a single reading', () => {
    expect(mean([7])).toBe(7);
  });
});
