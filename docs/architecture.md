# Architecture

## Services

| Service | Role | Port |
|---|---|---|
| `postgres` | Conversations, messages, documents, artifacts, agent steps | 5433 on the host, 5432 inside the network |
| `api` | FastAPI; holds all agent logic | 8000 |
| `ui` | Streamlit; speaks HTTP to `api` only | 8501 |
| `python-vm` | Sandbox that runs the agent's code — **outside this compose project** | 8081 |

The API reaches python-vm at `SANDBOX_BASE_URL`, which defaults to
`http://host.docker.internal:8081`. The compose file adds
`extra_hosts: host.docker.internal:host-gateway` so that resolves on Linux too.

Uploaded files and generated markdown live on the `./data` volume mounted into
`api`. There is no object storage at this stage.

## Code layout

```
api/
  app/
    api/            HTTP routes and Pydantic schemas
      documents.py     upload, list, status
      conversations.py create, list, ask, reset sandbox, delete
      health.py
      schemas.py
    core/           everything that is not HTTP
      llm/             LLMClient protocol + OpenAI-compatible adapter
      parsing/         Parser protocol + LlamaParse REST client + background job
      sandbox/         SandboxClient protocol + HTTP client + SessionResolver
      agent/           CodeActAgent + prompt builders
      chat_service.py  ties history, sandbox session and agent into one turn
    db/             Base, models, session factory
    dependencies.py the single place Settings meets the real clients
    config.py       Settings
  alembic/          migrations
  tests/
ui/
  app.py          Streamlit page
  api_client.py   HTTP client — the UI's only link to the backend
  tests/
```

## The three boundaries

Three `Protocol` classes carry the design's weight. Each has one real
implementation, each is faked in tests, and each can be swapped without the
agent noticing.

| Protocol | Real implementation | Faked in tests by |
|---|---|---|
| `LLMClient` | `OpenAICompatibleClient` | `FakeLLMClient` |
| `Parser` | `LlamaParseParser` | `FakeParser` (defined inline in the document tests) |
| `SandboxClient` | `HttpSandboxClient` | `FakeSandboxClient` |

`CodeActAgent` goes one step further: it does not even take a `SandboxClient`,
only a `Callable[[str], ExecutionResult]`. That is why the agent tests run
against a plain Python function with no HTTP or database anywhere in sight.

Everything is wired together in `api/app/dependencies.py`. Changing LLM
provider means changing environment variables; changing parser or sandbox
means writing one class and one line in that file.

## Layer rules

- `core/` never imports from `api/` — the agent does not know HTTP exists.
- `ui/` never imports from `api/app` — it only speaks the HTTP contract.
- Routes hold no business logic; they load a row, call a service, and map
  exceptions onto status codes.

## Request flows

### Upload

```
POST /documents
  └─ store file under data/uploads/{id}/
  └─ insert Document(parse_status="pending")
  └─ queue background task ──▶ returns 201 immediately
                              │
                              ├─ parse_status = "parsing"
                              ├─ LlamaParse: upload → poll → fetch markdown
                              ├─ write data/artifacts/{id}.md
                              ├─ insert DocumentArtifact
                              └─ parse_status = "ready" | "failed"
```

Parsing runs in the background because LlamaParse can take minutes on a large
document. The UI polls `GET /documents/{id}` until the status settles.

FastAPI's `BackgroundTasks` is enough here — no Celery, no Redis. The job takes
a `session_factory` argument rather than a session, precisely so that swapping
in a real queue later is a local change.

### One chat turn

```
POST /conversations/{id}/messages
  └─ read markdown artifact
  └─ snapshot history  ← BEFORE storing the new question
  └─ store + commit the user message
  └─ ensure sandbox session (create + upload markdown if missing)
  └─ CodeAct loop, up to AGENT_MAX_STEPS:
       LLM → code block? → run in sandbox → observation → LLM → ...
  └─ store assistant message + one agent_steps row per executed step
```

The ordering is not incidental; see [agent.md](agent.md).

## What is deliberately absent

Authentication and multi-user support. Vector retrieval. Multiple documents in
one conversation. SSE streaming. Token cost accounting. Report export.

The seams for these exist, but nothing was built for them.
