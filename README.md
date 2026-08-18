# file-understanding

A framework for asking questions about an uploaded document: upload a file →
convert it to markdown with LlamaParse → ask follow-up questions answered by a
CodeAct agent that writes Python inside the `python-vm` sandbox.

A demo skeleton, not a product: no authentication, no multi-user support, no
vector retrieval.

## Requirements

- Docker and Docker Compose
- `python-vm` already running on port 8081 — a separate repository, **not** part
  of this compose project
- A LlamaParse key and a key for an OpenAI-compatible LLM provider
  (OpenRouter, Cerebras, ...)

## Running

```bash
cp .env.example .env
# fill in LLM_API_KEY and LLAMA_CLOUD_API_KEY
docker compose up --build
```

- UI: http://localhost:8501
- API docs: http://localhost:8000/docs

## Architecture at a glance

| Component | Role |
|---|---|
| `postgres` | Conversations, messages, documents, artifacts, agent steps |
| `api` | FastAPI; holds all agent logic |
| `ui` | Streamlit; speaks HTTP only |
| `python-vm` (outside compose) | Runs the agent's code, keeps state per session |

A sandbox session is a cache, not the source of truth: when python-vm reaps an
idle session, the system recreates it and re-uploads the markdown
transparently.

## Tests

```bash
~/miniconda3/envs/minhln/bin/python -m pytest -m "not integration" -q
```

Tests use a separate `file_understanding_test` database, created by
`postgres/initdb/01-create-test-db.sql` on the **first** `docker compose up` —
scripts in `docker-entrypoint-initdb.d/` only run while the `fu_pgdata` volume
is empty. On a volume that predates the script, create it once by hand:

```bash
docker compose exec -T postgres createdb -U app file_understanding_test
```

Smoke tests need the full stack plus python-vm:

```bash
~/miniconda3/envs/minhln/bin/python -m pytest -m integration -q
```

## Documentation

Full documentation lives in [docs/](docs/README.md):

| Document | Covers |
|---|---|
| [architecture.md](docs/architecture.md) | Services, code layout, the three replaceable boundaries |
| [agent.md](docs/agent.md) | The CodeAct loop, prompts, sandbox session lifecycle |
| [database.md](docs/database.md) | Schema, ordering rules, migrations, test isolation |
| [api.md](docs/api.md) | Every endpoint, with status codes |
| [ui.md](docs/ui.md) | Streamlit layout, parse polling, error handling |
| [development.md](docs/development.md) | Setup, tests, configuration, swapping providers |

Contributors — including Claude Code — should read [CLAUDE.md](CLAUDE.md)
first.
