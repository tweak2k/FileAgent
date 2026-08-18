# Database

Postgres 17, accessed through SQLAlchemy 2.x with Alembic migrations. Models
live in `api/app/db/models.py`.

## Tables

```
documents ──┬──< document_artifacts
            │
            └──< conversations ──< messages ──< agent_steps
```

Every arrow is `ON DELETE CASCADE` at the database level and
`cascade="all, delete-orphan"` in the ORM: deleting a document takes its
artifacts and conversations with it.

### `documents`

An uploaded file and the state of its conversion.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `filename` | varchar(512) | Normalised with `Path(...).name` — never a path |
| `mime_type` | varchar(128) | As reported by the upload |
| `source_path` | varchar(1024) | `{DATA_DIR}/uploads/{id}/{filename}` |
| `size_bytes` | int | |
| `parse_status` | varchar(32) | `pending` → `parsing` → `ready` \| `failed` |
| `parse_error` | text, null | Set when `failed`, truncated at 2000 chars |
| `created_at` | timestamptz | |

`parse_status` has no CHECK constraint. Only `parse_document` writes it, and
that value never comes from user input.

### `document_artifacts`

Parser output, one row per conversion.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `document_id` | FK → documents | CASCADE |
| `kind` | varchar(32) | Currently only `markdown` |
| `content_path` | varchar(1024) | `{DATA_DIR}/artifacts/{document_id}.md` |
| `char_count` | int | Length of the markdown |
| `parser_name` | varchar(64) | e.g. `llamaparse` |
| `created_at` | timestamptz | |

A separate table rather than columns on `documents`, so a future artifact kind
— an outline, a chunk index — needs no schema change. `read_markdown` picks the
highest `id` among the `markdown` rows, so re-parsing a document is additive.

### `conversations`

A multi-turn session about one document.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `document_id` | FK → documents | CASCADE |
| `title` | varchar(512) | Defaults to `Hỏi đáp — {filename}` |
| `sandbox_session_id` | varchar(128), null | Cache, not the source of truth |
| `sandbox_session_created_at` | timestamptz, null | |
| `created_at` | timestamptz | |

`sandbox_session_id` may point at a session python-vm has already reaped. That
is expected — see [agent.md](agent.md).

### `messages`

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `conversation_id` | FK → conversations | CASCADE |
| `role` | varchar(16) | `user` or `assistant` |
| `content` | text | |
| `created_at` | timestamptz | |

**Ordering is `(created_at, id)`, and the `id` is not decorative.** Postgres
`now()` returns the transaction timestamp, so several messages written in one
transaction share a `created_at` down to the microsecond. Without the `id`
tie-break the history could come back scrambled, which would corrupt the
prompt.

### `agent_steps`

One row per code execution while answering a message.

| Column | Type | Notes |
|---|---|---|
| `id` | int, PK | |
| `message_id` | FK → messages | CASCADE |
| `step_index` | int | 0-based, ordered |
| `code` | text | Exactly what ran |
| `stdout` / `stderr` | text | As returned by the sandbox |
| `status` | varchar(32) | From python-vm: `completed`, `failed`, `timeout` |
| `duration_ms` | int | |

This table is what makes a demo convincing: it shows the code the agent
actually ran. It is also written for failed turns, attached to the assistant
message that records the failure.

## Migrations

Alembic config lives at `api/alembic.ini`, environment at `api/alembic/env.py`,
which reads the URL from `Settings` and imports the models so autogenerate can
see the tables.

```bash
cd api
DATABASE_URL="postgresql+psycopg://app:app@localhost:5433/file_understanding" \
  ~/miniconda3/envs/minhln/bin/alembic revision --autogenerate -m "describe the change"

DATABASE_URL="..." ~/miniconda3/envs/minhln/bin/alembic upgrade head
```

Always read the generated migration before applying it — autogenerate misses
things like server defaults and index renames.

In containers, `api/entrypoint.sh` runs `alembic upgrade head` before starting
uvicorn, and `set -e` means a failed migration stops the container rather than
serving against a stale schema.

## Databases and test isolation

Compose creates two databases: `file_understanding` for the application and
`file_understanding_test` for the suite, via
`postgres/initdb/01-create-test-db.sql`. That init script only runs when the
data volume is empty — on an existing volume, create it by hand:

```bash
docker compose exec -T postgres createdb -U app file_understanding_test
```

Tests do not use Alembic. `api/tests/conftest.py` creates the schema with
`Base.metadata.create_all`, opens an outer transaction per test and rolls it
back afterwards. The session joins that transaction with
`join_transaction_mode="create_savepoint"`, which is what allows code under
test — `ChatService`, `parse_document` — to call `commit()` without destroying
the isolation: those commits land on a savepoint.
