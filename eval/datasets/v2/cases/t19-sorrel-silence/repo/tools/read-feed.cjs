async function main() {
  const response = await fetch('https://feed.example.org/releases/current');
  if (!response.ok) throw new Error('feed response unsuccessful');
  const feed = JSON.parse(await response.text());
  if (!Array.isArray(feed.releases)) throw new Error('invalid releases');
}
main().catch(() => process.exit(1));
