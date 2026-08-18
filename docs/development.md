# Development

## Prerequisites

- Docker and Docker Compose
- The conda environment `minhln` at `/Users/macpro24/miniconda3/envs/minhln`
  (Python 3.14) — this repo does not create virtualenvs
- **python-vm running on port 8081.** It lives in a separate repository and is
  not part of this compose project. Without it, chat turns return 503.
- A LlamaParse key and a key for an OpenAI-compatible LLM provider

## Running the stack

```bash
cp .env.example .env          # then fill in the two keys
docker compose up --build
```

- UI: http://localhost:8501
- API docs: http://localhost:8000/docs
- Postgres: `localhost:5433`

`api` waits for Postgres to report healthy, runs `alembic upgrade head`, then
starts uvicorn. `ui` waits for `api` to be healthy.

## Running tests

Python dependencies go into the `minhln` environment:

```bash
~/miniconda3/envs/minhln/bin/pip install -e ".[dev,ui]"
```

Postgres must be up, because the tests use a real database:

```bash
docker compose up -d postgres
```

From the repository root:

```bash
# fast suite (62 tests)
~/miniconda3/envs/minhln/bin/python -m pytest -m "not integration" -q

# smoke tests — needs the full stack and python-vm running
~/miniconda3/envs/minhln/bin/python -m pytest -m integration -q
```

If the fast suite fails at the `engine` fixture with `database
"file_understanding_test" does not exist`, the compose volume predates the init
script:

```bash
docker compose exec -T postgres createdb -U app file_understanding_test
```

## Configuration

Read by `api/app/config.py` through pydantic-settings. Precedence: init
arguments > environment variables > `.env` > defaults.

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://app:app@localhost:5433/file_understanding` | Compose overrides this to `postgres:5432` |
| `LLM_BASE_URL` | `https://openrouter.ai/api/v1` | Any OpenAI-compatible endpoint |
| `LLM_API_KEY` | empty | Provider key |
| `LLM_MODEL` | `anthropic/claude-sonnet-4.5` | Model id as the provider names it |
| `LLM_MAX_TOKENS` | 4096 | Cap per completion |
| `LLAMA_CLOUD_API_KEY` | empty | LlamaParse key |
| `SANDBOX_BASE_URL` | `http://host.docker.internal:8081` | Use `http://localhost:8081` outside containers |
| `SANDBOX_API_KEY` | `dev-secret` | Must match python-vm's `PYTHON_VM_API_KEY` |
| `SANDBOX_TIMEOUT_SECONDS` | 30 | Per code execution |
| `AGENT_MAX_STEPS` | 8 | Code executions per turn |
| `DATA_DIR` | `/data` | Uploads and artifacts; mounted from `./data` |

Note for test authors: anything asserting on **defaults** must construct
`Settings(_env_file=None)`, otherwise a local `.env` wins and the test fails
for reasons unrelated to the change being made.

## Swapping a provider

### A different LLM

Nothing to write — it is configuration:

```bash
# Cerebras
LLM_BASE_URL=https://api.cerebras.ai/v1
LLM_MODEL=llama-3.3-70b

# a local vLLM
LLM_BASE_URL=http://host.docker.internal:8000/v1
LLM_MODEL=your-model
```

A provider that is *not* OpenAI-compatible means writing a class with one
method, `complete(messages) -> str`, and returning it from `get_llm_client` in
`api/app/dependencies.py`. `CodeActAgent` is untouched either way.

### A different parser

Implement `Parser` (`to_markdown(path, mime_type) -> ParseResult`), raise
`ParserError` on any failure, and return it from `get_parser`. Docling or
MarkItDown would slot in here as a local alternative to LlamaParse.

### A different sandbox

Implement `SandboxClient`: `create_session`, `execute`, `close_session`. Map
"session is gone" onto `SandboxSessionNotFound` — `SessionResolver` relies on
that exception to re-attach — and "out of capacity" onto
`SandboxCapacityError`. Then return it from `get_sandbox_client`.

## Conventions

- Comments and docstrings in **English**, on every module and function.
- User-facing strings — error messages, UI labels, LLM prompts — stay in
  **Vietnamese**. They are runtime data for a Vietnamese-speaking audience, not
  documentation.
- TDD: the failing test comes first.
- Update `docs/` in the same change as the code. See `CLAUDE.md`.
- Commit messages in Vietnamese with a `feat:` / `fix:` / `test:` / `chore:`
  prefix, matching the existing history.

## Where things are

| Looking for | File |
|---|---|
| The agent loop | `api/app/core/agent/codeact.py` |
| Prompts | `api/app/core/agent/prompts.py` |
| One chat turn end to end | `api/app/core/chat_service.py` |
| Sandbox session lifecycle | `api/app/core/sandbox/resolver.py` |
| Background parsing | `api/app/core/parsing/pipeline.py` |
| Provider wiring | `api/app/dependencies.py` |
| Test fakes | `api/tests/fakes.py` |
| The multi-turn guarantees | `api/tests/test_multi_turn.py` |
