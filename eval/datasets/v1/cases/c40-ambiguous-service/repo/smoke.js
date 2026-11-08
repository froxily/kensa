const { request } = require('undici');

async function main() {
  const response = await request(process.env.SERVICE_URL);
  if (response.statusCode !== 200) {
    throw new Error('service check failed');
  }
  await response.body.dump();
}
main().catch(() => { console.error('service check failed'); process.exit(1); });
