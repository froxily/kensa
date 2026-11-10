const { Client } = require('pg');

async function databaseName() {
  const client = new Client();
  await client.connect();
  try {
    const result = await client.query('SELECT current_database() AS name');
    return result.rows[0].name;
  } finally {
    await client.end();
  }
}
module.exports = { databaseName };
