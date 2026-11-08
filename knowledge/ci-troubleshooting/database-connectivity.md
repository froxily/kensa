# Database connectivity in CI

## Symptoms
- `Connection refused` or `ECONNREFUSED` on 127.0.0.1 or localhost with ports 5432 (PostgreSQL), 3306 (MySQL), 6379 (Redis) or 27017 (MongoDB).
- `could not connect to server`, `Is the server running on that host and accepting TCP/IP connections?`
- `password authentication failed`, `role "x" does not exist`, `database "x" does not exist`.
- JDBC `Communications link failure`; ORMs that time out while acquiring a connection.
- Many tests failing or erroring at once in setup fixtures: a classic symptom of the database rather than the tests.

## Where to look
- The job's `services:` block: is a database service defined at all? Are its ports mapped (`ports: - 5432:5432`)?
- The health check options (`--health-cmd pg_isready ...`): without them, tests may start before the database accepts connections.
- Host names: inside a container job the service is reached by its service name; on the runner host it is `localhost` with mapped ports.
- Credentials and database name used by the tests compared with the service's environment (`POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`).

## Common causes
- The `services:` block is missing or was removed.
- No port mapping, or the wrong host name for the job type.
- The tests start before the database is ready.
- Mismatched credentials or database names, or migrations not run before tests.

## Safe fixes
- Define the service with a health check and port mapping, and point the tests at it through environment variables.
