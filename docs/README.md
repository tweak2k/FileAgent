# file-understanding — documentation

A framework for asking questions about an uploaded document. A file is
converted to markdown, then a CodeAct agent answers follow-up questions by
writing Python that reads the markdown inside a sandbox.

This is a demo framework, not a product: no authentication, no multi-user
support, no vector retrieval. What it does provide is a working end-to-end
skeleton with replaceable boundaries.

## Where to start

| Document | Read it when you want to |
|---|---|
| [architecture.md](architecture.md) | Understand how the pieces fit together |
| [agent.md](agent.md) | Understand the CodeAct loop and sandbox session lifecycle |
| [database.md](database.md) | Work with the schema or write a migration |
| [api.md](api.md) | Call the HTTP API, or change a route |
| [ui.md](ui.md) | Work on the Streamlit interface |
| [development.md](development.md) | Set up, run tests, or swap a provider |

## The system in one picture

```
                    ┌──────────────┐
   browser ────────▶│  ui          │  Streamlit, HTTP only
                    │  :8501       │
                    └──────┬───────┘
                           │ HTTP
                    ┌──────▼───────┐        ┌──────────────┐
                    │  api         │───────▶│  postgres    │
                    │  :8000       │        │  :5433       │
                    └──────┬───────┘        └──────────────┘
                           │
              ┌────────────┴────────────┐
              │ HTTP                    │ HTTP
      ┌───────▼────────┐       ┌────────▼─────────┐
      │  LlamaParse    │       │  python-vm       │
      │  (cloud)       │       │  :8081           │
      └────────────────┘       └──────────────────┘
        file → markdown          runs the agent's code

      ─── inside docker compose ───   ─── outside ───
```

`postgres`, `api` and `ui` are the three compose services. LlamaParse is a
cloud API. **python-vm runs outside this compose project** — it is a separate
repository, started independently on port 8081.

## The shape of one question

1. The user uploads a file. The API stores it, records `parse_status=pending`
   and returns immediately.
2. A background job sends the file to LlamaParse and writes the markdown to
   disk as a `document_artifacts` row. Status becomes `ready`.
3. The user opens a conversation and asks a question.
4. The API ensures a sandbox session exists with `document.md` uploaded into
   it, then runs the CodeAct loop: the LLM writes Python, the sandbox runs it,
   stdout comes back as the next observation.
5. When the LLM answers without code, that reply plus every executed step is
   written to the database and returned.

Turn 2 reuses the same sandbox session, so variables from turn 1 are still
there. See [agent.md](agent.md) for why that matters and what happens when the
session disappears.
