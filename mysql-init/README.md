SQL scripts placed here are executed by MySQL on first container startup (alphabetical order).

The database schema is managed by Alembic migrations — run `alembic upgrade head` inside the backend container after the stack is up. This directory is reserved for any seed data or one-time setup scripts that need to run before Alembic.
