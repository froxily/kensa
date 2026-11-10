export function endpoint() {
  const value = process.env.HARBOR_ENDPOINT;
  if (!value) throw new Error('HARBOR_ENDPOINT is required');
  return value;
}
