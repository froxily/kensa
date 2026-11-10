export function mean(values: number[]): number {
  const total = values.reduce((sum, value) => sum + value, 0);
  return total / values.length;
}
