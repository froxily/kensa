const test = require('node:test');
const assert = require('node:assert/strict');
const mysql = require('mysql2/promise');

test('database responds', async () => {
  const connection = await mysql.createConnection({
    host: 'mysql', user: 'root', password: 'testpass',
    database: 'parcels', port: 3306
  });
  const [rows] = await connection.query('SELECT 1 AS ready');
  assert.equal(rows[0].ready, 1);
  await connection.end();
});
